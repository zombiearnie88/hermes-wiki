from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PageRecord:
    page: int
    content: str


@dataclass(frozen=True)
class PageIndexBuildResult:
    doc_name: str
    page_count: int
    doc_description: str
    structure: list[dict[str, Any]]
    pages: list[PageRecord]
    audit: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PageIndexDocument:
    doc_name: str
    page_count: int
    doc_description: str
    structure: list[dict[str, Any]]
    pages: list[PageRecord]
    metadata: dict[str, Any] = field(default_factory=dict)
    audit: dict[str, Any] = field(default_factory=dict)
