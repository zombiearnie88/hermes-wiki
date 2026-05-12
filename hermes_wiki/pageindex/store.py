from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..workspace import WorkspacePaths

from .tree import strip_text_fields
from .types import PageIndexBuildResult, PageIndexDocument, PageRecord


def pageindex_doc_dir(paths: WorkspacePaths, doc_name: str) -> Path:
    root = paths.pageindex_dir.resolve()
    candidate = (root / doc_name).resolve()
    if not candidate.is_relative_to(root):
        raise ValueError(f"Invalid PageIndex document name: {doc_name}")
    return candidate


def write_pageindex(paths: WorkspacePaths, result: PageIndexBuildResult) -> None:
    doc_dir = pageindex_doc_dir(paths, result.doc_name)
    doc_dir.mkdir(parents=True, exist_ok=True)

    index_payload: dict[str, Any] = {
        "version": 1,
        "doc_name": result.doc_name,
        "doc_description": result.doc_description,
        "page_count": result.page_count,
        "structure": strip_text_fields(result.structure),
    }
    (doc_dir / "index.json").write_text(json.dumps(index_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    page_lines = [
        json.dumps({"page": record.page, "content": record.content}, ensure_ascii=False)
        for record in result.pages
    ]
    (doc_dir / "pages.jsonl").write_text("\n".join(page_lines) + ("\n" if page_lines else ""), encoding="utf-8")

    if result.audit:
        (doc_dir / "audit.json").write_text(json.dumps(result.audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def read_pageindex(paths: WorkspacePaths, doc_name: str) -> PageIndexDocument:
    doc_dir = pageindex_doc_dir(paths, doc_name)
    index_path = doc_dir / "index.json"
    pages_path = doc_dir / "pages.jsonl"
    if not index_path.exists() or not pages_path.exists():
        raise FileNotFoundError(f"PageIndex document not found: {doc_name}")

    metadata = json.loads(index_path.read_text(encoding="utf-8"))
    pages: list[PageRecord] = []
    for raw_line in pages_path.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip():
            continue
        record = json.loads(raw_line)
        pages.append(PageRecord(page=int(record["page"]), content=str(record.get("content", ""))))

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
