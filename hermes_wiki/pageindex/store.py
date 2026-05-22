from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..workspace import WorkspacePaths

from .tree import strip_text_fields
from .types import PageIndexBuildResult, PageIndexDocument, PageRecord


def pageindex_doc_dir(paths: WorkspacePaths, doc_name: str) -> Path:
    """Return the internal PageIndex metadata directory for a document."""
    root = paths.pageindex_dir.resolve()
    candidate = (root / doc_name).resolve()
    if not candidate.is_relative_to(root):
        raise ValueError(f"Invalid PageIndex document name: {doc_name}")
    return candidate


def page_source_path(paths: WorkspacePaths, doc_name: str) -> Path:
    """Return the user-visible page-source JSONL path for a PageIndex document."""
    root = (paths.wiki_dir / "sources").resolve()
    candidate = (root / f"{doc_name}.jsonl").resolve()
    if not candidate.is_relative_to(root):
        raise ValueError(f"Invalid PageIndex document name: {doc_name}")
    return candidate


def legacy_page_source_path(paths: WorkspacePaths, doc_name: str) -> Path:
    """Return the pre-migration internal PageIndex pages path, if present."""
    return pageindex_doc_dir(paths, doc_name) / "pages.jsonl"


def _page_record_to_json(record: PageRecord) -> str:
    """Serialize one page record as one JSONL line."""
    return json.dumps({"page": record.page, "content": record.content}, ensure_ascii=False)


def _read_page_records(path: Path) -> list[PageRecord]:
    """Read PageIndex page records from a JSONL source file."""
    pages: list[PageRecord] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip():
            continue
        record = json.loads(raw_line)
        pages.append(PageRecord(page=int(record["page"]), content=str(record.get("content", ""))))
    return pages


def write_page_source(paths: WorkspacePaths, doc_name: str, pages: list[PageRecord]) -> None:
    """Write PageIndex page content to `wiki/sources/{doc_name}.jsonl`."""
    source_path = page_source_path(paths, doc_name)
    source_path.parent.mkdir(parents=True, exist_ok=True)
    page_lines = [_page_record_to_json(record) for record in pages]
    source_path.write_text("\n".join(page_lines) + ("\n" if page_lines else ""), encoding="utf-8")


def read_page_source(paths: WorkspacePaths, doc_name: str) -> list[PageRecord]:
    """Read PageIndex page content, migrating legacy internal JSONL if needed."""
    source_path = page_source_path(paths, doc_name)
    if source_path.exists():
        return _read_page_records(source_path)

    legacy_path = legacy_page_source_path(paths, doc_name)
    if not legacy_path.exists():
        raise FileNotFoundError(f"PageIndex source not found: {source_path}")

    pages = _read_page_records(legacy_path)
    write_page_source(paths, doc_name, pages)
    return pages


def write_pageindex(paths: WorkspacePaths, result: PageIndexBuildResult) -> None:
    """Write PageIndex metadata and user-visible page source content."""
    doc_dir = pageindex_doc_dir(paths, result.doc_name)
    doc_dir.mkdir(parents=True, exist_ok=True)

    # Step 1: keep derived PageIndex structure in internal state.
    index_payload: dict[str, Any] = {
        "version": 1,
        "doc_name": result.doc_name,
        "doc_description": result.doc_description,
        "page_count": result.page_count,
        "structure": strip_text_fields(result.structure),
    }
    (doc_dir / "index.json").write_text(json.dumps(index_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # Step 2: expose page-level source material under wiki/sources/.
    write_page_source(paths, result.doc_name, result.pages)

    if result.audit:
        (doc_dir / "audit.json").write_text(json.dumps(result.audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def read_pageindex(paths: WorkspacePaths, doc_name: str, *, load_pages: bool = True) -> PageIndexDocument:
    """Read PageIndex metadata and, by default, its wiki source JSONL pages."""
    doc_dir = pageindex_doc_dir(paths, doc_name)
    index_path = doc_dir / "index.json"
    if not index_path.exists():
        raise FileNotFoundError(f"PageIndex document not found: {doc_name}")

    metadata = json.loads(index_path.read_text(encoding="utf-8"))
    pages = read_page_source(paths, doc_name) if load_pages else []

    audit_path = doc_dir / "audit.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8")) if audit_path.exists() else {}
    return PageIndexDocument(
        doc_name=str(metadata.get("doc_name", doc_name)),
        page_count=int(metadata.get("page_count", len(pages))),
        doc_description=str(metadata.get("doc_description", "")),
        structure=list(metadata.get("structure", [])),
        pages=pages,
        metadata=metadata,
        audit=audit,
    )
