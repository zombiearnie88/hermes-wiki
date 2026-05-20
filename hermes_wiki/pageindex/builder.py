from __future__ import annotations

from pathlib import Path
from typing import Any

from ..images import load_pymupdf
from ..workspace import WorkspacePaths

from .config import PageIndexConfig, load_pageindex_config
from .prompts import document_description_prompt, node_summary_prompt, pageindex_generate_text_async
from .store import read_pageindex, write_pageindex
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


def extract_pdf_pages_and_toc(raw_path: Path) -> tuple[list[PageRecord], list[list[Any]]]:
    pymupdf = load_pymupdf()
    pages: list[PageRecord] = []
    toc: list[list[Any]] = []

    with pymupdf.open(str(raw_path)) as document:
        try:
            toc = list(document.get_toc(simple=True) or [])
        except Exception:
            toc = []
        for index, page in enumerate(document):
            pages.append(PageRecord(page=index + 1, content=(page.get_text("text") or "").strip()))

    return pages, toc


def _build_initial_structure(pages: list[PageRecord], toc: list[list[Any]], config: PageIndexConfig) -> tuple[list[dict], str]:
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
    config = load_pageindex_config(paths.config_path)
    pages, toc = extract_pdf_pages_and_toc(raw_path)
    page_count = len(pages)
    if page_count == 0:
        raise RuntimeError("PageIndex build failed: PDF contains no pages.")
    if not "".join(record.content for record in pages).strip():
        raise RuntimeError("PageIndex build failed: PDF has no extractable text. OCR is not supported yet.")

    structure, structure_source = _build_initial_structure(pages, toc, config)
    for node in flatten_nodes(structure):
        node["summary"] = await _summary_for_node_async(llm, node, pages, model, provider, language, config)

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
