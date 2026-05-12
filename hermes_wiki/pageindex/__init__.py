from __future__ import annotations

from .builder import build_or_load_pageindex
from .retrieve import get_document_structure, get_page_content, parse_page_range
from .store import read_pageindex, write_pageindex
from .types import PageIndexBuildResult, PageIndexDocument, PageRecord

__all__ = [
    "PageIndexBuildResult",
    "PageIndexDocument",
    "PageRecord",
    "build_or_load_pageindex",
    "get_document_structure",
    "get_page_content",
    "parse_page_range",
    "read_pageindex",
    "write_pageindex",
]
