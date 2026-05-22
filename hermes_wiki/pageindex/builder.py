from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..images import extract_pdf_page_markdown, load_pymupdf
from ..workspace import WorkspacePaths

from .config import PageIndexConfig, load_pageindex_config
from .prompts import document_description_prompt, node_summary_prompt, pageindex_generate_text_async
from .store import page_source_path, read_pageindex, write_pageindex
from .tree import (
    build_chunk_tree,
    build_tree_from_toc,
    compact_excerpt,
    estimate_tokens,
    flatten_nodes,
    page_text,
    render_tree,
    split_large_leaf_nodes,
)
from .types import PageIndexBuildResult, PageRecord


@dataclass(frozen=True)
class PdfExtractionResult:
    """PDF extraction payload before PageIndex structure and summaries are built."""

    pages: list[PageRecord]
    toc: list[list[Any]]
    image_count: int
    extractable_text: str


def extract_pdf_pages_and_toc(raw_path: Path, doc_name: str, paths: WorkspacePaths) -> PdfExtractionResult:
    """Extract text, images, and TOC entries from a PDF for PageIndex ingest."""
    pymupdf = load_pymupdf()
    pages: list[PageRecord] = []
    toc: list[list[Any]] = []
    image_counter = 0
    image_count = 0
    extractable_text_parts: list[str] = []
    images_dir = paths.wiki_dir / "sources" / "images" / doc_name

    with pymupdf.open(str(raw_path)) as document:
        try:
            toc = list(document.get_toc(simple=True) or [])
        except Exception:
            toc = []
        for index, page in enumerate(document):
            page_num = index + 1
            text_content = (page.get_text("text") or "").strip()
            if text_content:
                extractable_text_parts.append(text_content)

            page_markdown, image_counter, page_image_count = extract_pdf_page_markdown(
                page,
                doc_name,
                images_dir,
                page_num,
                image_counter,
            )
            image_count += page_image_count
            pages.append(PageRecord(page=page_num, content=(page_markdown or text_content).strip()))

    return PdfExtractionResult(
        pages=pages,
        toc=toc,
        image_count=image_count,
        extractable_text="\n\n".join(extractable_text_parts),
    )


def _build_initial_structure(pages: list[PageRecord], toc: list[list[Any]], config: PageIndexConfig) -> tuple[list[dict], str]:
    """Build the first PageIndex tree from PDF TOC metadata or page chunks."""
    page_count = len(pages)
    structure = build_tree_from_toc(toc, page_count)
    if structure:
        return (
            split_large_leaf_nodes(
                structure,
                pages,
                max_pages_per_node=config.max_pages_per_node,
                max_tokens_per_node=config.max_tokens_per_node,
            ),
            "pdf_toc",
        )
    return build_chunk_tree(page_count, max_pages_per_node=config.max_pages_per_node), "page_chunks"


async def _summary_for_node_async(
    llm: Any,
    node: dict,
    pages: list[PageRecord],
    model: str,
    provider: str | None,
    language: str,
    config: PageIndexConfig,
) -> str:
    """Create or compact a summary for one PageIndex tree node."""
    start = int(node.get("start_index", 1))
    end = int(node.get("end_index", start))
    text = page_text(pages, start, end)
    if not text.strip():
        return "No extractable text found in this page range."

    token_count = estimate_tokens(text)
    if token_count < config.summary_token_threshold:
        return compact_excerpt(text, max_chars=900)

    max_chars = max(2000, config.max_tokens_per_node * 4)
    prompt_text = text[:max_chars]
    return await pageindex_generate_text_async(
        llm,
        model,
        provider,
        node_summary_prompt(str(node.get("title", "Untitled")), start, end, prompt_text, language),
        purpose=f"wiki.pageindex.node.{node.get('node_id', start)}",
    )


async def build_pageindex_async(
    llm: Any,
    doc_name: str,
    raw_path: Path,
    paths: WorkspacePaths,
    model: str,
    provider: str | None,
    *,
    language: str,
) -> PageIndexBuildResult:
    """Build PageIndex state from a long PDF and return persisted payload data."""
    config = load_pageindex_config(paths.config_path)
    extraction = extract_pdf_pages_and_toc(raw_path, doc_name, paths)
    pages = extraction.pages
    toc = extraction.toc
    page_count = len(pages)
    if page_count == 0:
        raise RuntimeError("PageIndex build failed: PDF contains no pages.")
    if not extraction.extractable_text.strip():
        raise RuntimeError("PageIndex build failed: PDF has no extractable text. OCR is not supported yet.")

    # Step 1: derive a navigable document structure from the PDF TOC or page chunks.
    structure, structure_source = _build_initial_structure(pages, toc, config)

    # Step 2: summarize each PageIndex node using only the relevant page range.
    for node in flatten_nodes(structure):
        node["summary"] = await _summary_for_node_async(llm, node, pages, model, provider, language, config)

    # Step 3: summarize the full structure for the wiki summary page.
    rendered_tree = render_tree(structure)
    doc_description = await pageindex_generate_text_async(
        llm,
        model,
        provider,
        document_description_prompt(doc_name, rendered_tree, language),
        purpose=f"wiki.pageindex.description.{doc_name}",
    )
    audit = {
        "status": "completed",
        "raw_path": str(raw_path),
        "page_count": page_count,
        "toc_entries": len(toc),
        "structure_source": structure_source,
        "source_path": str(page_source_path(paths, doc_name)),
        "image_count": extraction.image_count,
        "model": model,
        "provider": provider,
        "config": vars(config),
    }
    return PageIndexBuildResult(
        doc_name=doc_name,
        page_count=page_count,
        doc_description=doc_description,
        structure=structure,
        pages=pages,
        audit=audit,
    )


async def build_or_load_pageindex_async(
    llm: Any,
    doc_name: str,
    raw_path: Path,
    paths: WorkspacePaths,
    model: str,
    provider: str | None,
    *,
    language: str,
) -> PageIndexBuildResult:
    """Load existing PageIndex state or build and persist it on first ingest."""
    try:
        document = read_pageindex(paths, doc_name)
    except FileNotFoundError:
        result = await build_pageindex_async(llm, doc_name, raw_path, paths, model, provider, language=language)
        write_pageindex(paths, result)
        return result

    return PageIndexBuildResult(
        doc_name=document.doc_name,
        page_count=document.page_count,
        doc_description=document.doc_description,
        structure=document.structure,
        pages=document.pages,
        audit={**document.audit, "status": "loaded"},
    )
