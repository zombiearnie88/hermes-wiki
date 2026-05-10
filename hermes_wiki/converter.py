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
    raw_path: Path | None = None
    source_path: Path | None = None
    skipped: bool = False
    file_hash: str | None = None
    unsupported_long_doc: bool = False
    long_doc_page_count: int = 0


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
    raw_dest = paths.raw_dir / src.name
    if raw_dest.resolve() != src.resolve():
        shutil.copy2(src, raw_dest)

    if src.suffix.lower() == ".pdf":
        page_count = get_pdf_page_count(src)
        if page_count >= long_doc_threshold:
            return ConvertResult(
                raw_path=raw_dest,
                file_hash=file_hash,
                unsupported_long_doc=True,
                long_doc_page_count=page_count,
            )

    sources_dir = paths.wiki_dir / "sources"
    sources_dir.mkdir(parents=True, exist_ok=True)
    images_dir = paths.wiki_dir / "sources" / "images" / src.stem
    images_dir.mkdir(parents=True, exist_ok=True)
    doc_name = src.stem

    if src.suffix.lower() == ".md":
        markdown = src.read_text(encoding="utf-8")
        markdown = copy_relative_images(markdown, src.parent, doc_name, images_dir)
    elif src.suffix.lower() == ".pdf":
        markdown = convert_pdf_with_images(src, doc_name, images_dir)
    else:
        from markitdown import MarkItDown

        converter = MarkItDown()
        result = converter.convert(str(src))
        markdown = extract_base64_images(result.text_content, doc_name, images_dir)

    dest_md = sources_dir / f"{doc_name}.md"
    dest_md.write_text(markdown, encoding="utf-8")
    return ConvertResult(raw_path=raw_dest, source_path=dest_md, file_hash=file_hash)
