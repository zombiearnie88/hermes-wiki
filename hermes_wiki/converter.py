from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from hermes_wiki.config import load_config
from hermes_wiki.images import copy_relative_images, convert_pdf_with_images, extract_base64_images
from hermes_wiki.state import HashRegistry
from hermes_wiki.workspace import WorkspacePaths

SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".md",
    ".markdown",
    ".docx",
    ".pptx",
    ".xlsx",
    ".html",
    ".htm",
    ".txt",
    ".csv",
}


@dataclass
class ConvertResult:
    doc_name: str = ""
    raw_path: Path | None = None
    source_path: Path | None = None
    skipped: bool = False
    file_hash: str | None = None
    unsupported_long_doc: bool = False
    long_doc_page_count: int = 0


def _file_matches_hash(path: Path, file_hash: str) -> bool:
    if not path.exists() or not path.is_file():
        return False
    try:
        return HashRegistry.hash_file(path) == file_hash
    except OSError:
        return False


def _allocate_doc_name(src: Path, paths: WorkspacePaths, file_hash: str) -> tuple[str, Path]:
    base_name = src.stem
    suffix = src.suffix
    candidate_name = base_name
    counter = 2

    while True:
        raw_candidate = paths.raw_dir / f"{candidate_name}{suffix}"
        source_candidate = paths.wiki_dir / "sources" / f"{candidate_name}.md"
        summary_candidate = paths.wiki_dir / "summaries" / f"{candidate_name}.md"

        if raw_candidate.resolve() == src.resolve():
            if not source_candidate.exists() and not summary_candidate.exists():
                return candidate_name, raw_candidate

        if not raw_candidate.exists() and not source_candidate.exists() and not summary_candidate.exists():
            return candidate_name, raw_candidate

        if _file_matches_hash(raw_candidate, file_hash) and not source_candidate.exists() and not summary_candidate.exists():
            return candidate_name, raw_candidate

        candidate_name = f"{base_name}-{counter}"
        counter += 1


def _convert_with_markitdown(src: Path, doc_name: str, images_dir: Path) -> str:
    try:
        from markitdown import MarkItDown
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            f"MarkItDown is required to ingest {src.suffix} files. Install markitdown[all] in the runtime environment."
        ) from exc

    converter = MarkItDown()
    result = converter.convert(str(src))
    return extract_base64_images(result.text_content, doc_name, images_dir)


def get_pdf_page_count(path: Path) -> int:
    import pymupdf

    with pymupdf.open(str(path)) as document:
        return document.page_count


def convert_document(src: Path, paths: WorkspacePaths) -> ConvertResult:
    config = load_config(paths.config_path)
    long_doc_threshold = int(config.get("long_doc_threshold", 20))
    registry = HashRegistry(paths.hashes_path)

    file_hash = HashRegistry.hash_file(src)
    if registry.is_known(file_hash):
        return ConvertResult(skipped=True)

    paths.raw_dir.mkdir(parents=True, exist_ok=True)
    doc_name, raw_dest = _allocate_doc_name(src, paths, file_hash)
    if raw_dest.resolve() != src.resolve():
        shutil.copy2(src, raw_dest)

    if src.suffix.lower() == ".pdf":
        page_count = get_pdf_page_count(src)
        if page_count >= long_doc_threshold:
            return ConvertResult(
                doc_name=doc_name,
                raw_path=raw_dest,
                file_hash=file_hash,
                unsupported_long_doc=True,
                long_doc_page_count=page_count,
            )

    sources_dir = paths.wiki_dir / "sources"
    sources_dir.mkdir(parents=True, exist_ok=True)
    images_dir = paths.wiki_dir / "sources" / "images" / doc_name
    images_dir.mkdir(parents=True, exist_ok=True)

    if src.suffix.lower() in {".md", ".markdown"}:
        markdown = src.read_text(encoding="utf-8")
        markdown = copy_relative_images(markdown, src.parent, doc_name, images_dir)
    elif src.suffix.lower() in {".txt", ".csv"}:
        markdown = src.read_text(encoding="utf-8")
    elif src.suffix.lower() == ".pdf":
        markdown = convert_pdf_with_images(src, doc_name, images_dir)
    else:
        markdown = _convert_with_markitdown(src, doc_name, images_dir)

    dest_md = sources_dir / f"{doc_name}.md"
    dest_md.write_text(markdown, encoding="utf-8")
    return ConvertResult(doc_name=doc_name, raw_path=raw_dest, source_path=dest_md, file_hash=file_hash)
