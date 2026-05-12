from __future__ import annotations

import copy
import re
from typing import Any

from .types import PageRecord


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // 4)


def compact_excerpt(text: str, *, max_chars: int = 900) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 3].rstrip() + "..."


def page_text(pages: list[PageRecord], start_page: int, end_page: int) -> str:
    selected = [record.content for record in pages if start_page <= record.page <= end_page]
    return "\n\n".join(part for part in selected if part)


def flatten_nodes(structure: list[dict[str, Any]]) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []

    def visit(items: list[dict[str, Any]]) -> None:
        for item in items:
            nodes.append(item)
            children = item.get("nodes")
            if isinstance(children, list):
                visit(children)

    visit(structure)
    return nodes


def assign_node_ids(structure: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counter = 1

    def visit(items: list[dict[str, Any]]) -> None:
        nonlocal counter
        for item in items:
            item["node_id"] = str(counter).zfill(4)
            counter += 1
            children = item.get("nodes")
            if isinstance(children, list):
                visit(children)
            if not item.get("nodes"):
                item.pop("nodes", None)

    visit(structure)
    return structure


def strip_text_fields(data: Any) -> Any:
    if isinstance(data, dict):
        return {key: strip_text_fields(value) for key, value in data.items() if key != "text"}
    if isinstance(data, list):
        return [strip_text_fields(item) for item in data]
    return data


def _range_label(node: dict[str, Any]) -> str:
    start = int(node.get("start_index", 0) or 0)
    end = int(node.get("end_index", start) or start)
    return str(start) if start == end else f"{start}-{end}"


def render_tree(structure: list[dict[str, Any]], *, include_summaries: bool = True) -> str:
    lines: list[str] = []

    def visit(items: list[dict[str, Any]], depth: int) -> None:
        for item in items:
            indent = "  " * depth
            title = item.get("title", "Untitled")
            node_id = item.get("node_id", "????")
            line = f"{indent}- [{_range_label(item)}] ({node_id}) {title}"
            summary = str(item.get("summary", "")).strip()
            if include_summaries and summary:
                line += f": {compact_excerpt(summary, max_chars=220)}"
            lines.append(line)
            children = item.get("nodes")
            if isinstance(children, list):
                visit(children, depth + 1)

    visit(structure, 0)
    return "\n".join(lines)


def build_chunk_tree(page_count: int, *, max_pages_per_node: int) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    start = 1
    while start <= page_count:
        end = min(page_count, start + max_pages_per_node - 1)
        title = f"Pages {start}-{end}" if start != end else f"Page {start}"
        nodes.append({"title": title, "start_index": start, "end_index": end})
        start = end + 1
    return assign_node_ids(nodes)


def build_tree_from_toc(toc: list[list[Any]], page_count: int) -> list[dict[str, Any]]:
    flat: list[dict[str, Any]] = []
    for raw in toc:
        if len(raw) < 3:
            continue
        try:
            level = int(raw[0])
            title = str(raw[1]).strip() or "Untitled"
            page = int(raw[2])
        except (TypeError, ValueError):
            continue
        if level <= 0 or page < 1 or page > page_count:
            continue
        flat.append({"level": level, "title": title, "start_index": page})

    if not flat:
        return []

    for index, item in enumerate(flat):
        end_page = page_count
        for later in flat[index + 1 :]:
            if later["level"] <= item["level"]:
                next_page = int(later["start_index"])
                end_page = max(int(item["start_index"]), next_page - 1)
                break
        item["end_index"] = min(page_count, end_page)

    root_nodes: list[dict[str, Any]] = []
    stack: list[tuple[int, dict[str, Any]]] = []
    for item in flat:
        level = int(item.pop("level"))
        node = dict(item)
        while stack and stack[-1][0] >= level:
            stack.pop()
        if stack:
            stack[-1][1].setdefault("nodes", []).append(node)
        else:
            root_nodes.append(node)
        stack.append((level, node))

    return assign_node_ids(root_nodes)


def split_large_leaf_nodes(
    structure: list[dict[str, Any]],
    pages: list[PageRecord],
    *,
    max_pages_per_node: int,
    max_tokens_per_node: int,
) -> list[dict[str, Any]]:
    def split_node(node: dict[str, Any]) -> None:
        children = node.get("nodes")
        if isinstance(children, list) and children:
            for child in children:
                split_node(child)
            return

        start = int(node.get("start_index", 1))
        end = int(node.get("end_index", start))
        token_count = estimate_tokens(page_text(pages, start, end))
        if end - start + 1 <= max_pages_per_node and token_count <= max_tokens_per_node:
            return

        chunks: list[dict[str, Any]] = []
        chunk_start = start
        part = 1
        while chunk_start <= end:
            chunk_end = min(end, chunk_start + max_pages_per_node - 1)
            chunks.append(
                {
                    "title": f"{node.get('title', 'Section')} Part {part}",
                    "start_index": chunk_start,
                    "end_index": chunk_end,
                }
            )
            chunk_start = chunk_end + 1
            part += 1
        node["nodes"] = chunks

    result = copy.deepcopy(structure)
    for root in result:
        split_node(root)
    return assign_node_ids(result)
