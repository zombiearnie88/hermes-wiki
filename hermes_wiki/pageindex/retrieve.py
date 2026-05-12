from __future__ import annotations

from ..workspace import WorkspacePaths

from .store import read_pageindex


class PageRangeError(ValueError):
    pass


def parse_page_range(pages: str, *, page_count: int, max_pages: int) -> list[int]:
    if not isinstance(pages, str) or not pages.strip():
        raise PageRangeError('Invalid pages format. Use "5", "5-7", or "3,8".')

    selected: set[int] = set()
    for raw_part in pages.split(","):
        part = raw_part.strip()
        if not part:
            raise PageRangeError(f"Invalid empty page selector in {pages!r}.")
        if "-" in part:
            bounds = [value.strip() for value in part.split("-", 1)]
            if len(bounds) != 2 or not bounds[0].isdigit() or not bounds[1].isdigit():
                raise PageRangeError(f"Invalid page range: {part!r}.")
            start = int(bounds[0])
            end = int(bounds[1])
            if start > end:
                raise PageRangeError(f"Invalid page range {part!r}: start must be <= end.")
            selected.update(range(start, end + 1))
        else:
            if not part.isdigit():
                raise PageRangeError(f"Invalid page number: {part!r}.")
            selected.add(int(part))

    if not selected:
        raise PageRangeError("No pages selected.")
    if min(selected) < 1 or max(selected) > page_count:
        raise PageRangeError(f"Page selection must be within 1-{page_count}.")
    if len(selected) > max_pages:
        raise PageRangeError(f"Page selection exceeds the maximum of {max_pages} pages per call.")
    return sorted(selected)


def get_document_structure(paths: WorkspacePaths, doc_name: str) -> dict:
    document = read_pageindex(paths, doc_name)
    return {
        "doc_name": document.doc_name,
        "doc_description": document.doc_description,
        "page_count": document.page_count,
        "structure": document.structure,
    }


def get_page_content(paths: WorkspacePaths, doc_name: str, pages: str, *, max_pages: int) -> dict:
    document = read_pageindex(paths, doc_name)
    selected = parse_page_range(pages, page_count=document.page_count, max_pages=max_pages)
    page_map = {record.page: record.content for record in document.pages}
    return {
        "doc_name": document.doc_name,
        "page_count": document.page_count,
        "pages": [
            {"page": page, "content": page_map.get(page, "")}
            for page in selected
        ],
    }
