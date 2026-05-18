from __future__ import annotations

import json
from pathlib import Path

import pytest

from hermes_wiki.pageindex.retrieve import PageRangeError, get_document_structure, get_page_content, parse_page_range
from hermes_wiki.pageindex.store import read_pageindex, write_pageindex
from hermes_wiki.pageindex.tree import render_tree, strip_text_fields
from hermes_wiki.pageindex.types import PageIndexBuildResult, PageRecord
from hermes_wiki.workspace import init_workspace, workspace_paths


def _sample_result() -> PageIndexBuildResult:
    return PageIndexBuildResult(
        doc_name="paper",
        page_count=3,
        doc_description="Paper overview",
        structure=[
            {
                "title": "Intro",
                "node_id": "0001",
                "start_index": 1,
                "end_index": 2,
                "summary": "Intro summary",
                "text": "full text must not render",
            },
            {
                "title": "Results",
                "node_id": "0002",
                "start_index": 3,
                "end_index": 3,
                "summary": "Results summary",
            },
        ],
        pages=[
            PageRecord(page=1, content="page one"),
            PageRecord(page=2, content="page two"),
            PageRecord(page=3, content="page three"),
        ],
        audit={"status": "completed"},
    )


def test_parse_page_range_accepts_supported_forms() -> None:
    assert parse_page_range("5", page_count=10, max_pages=8) == [5]
    assert parse_page_range("5-7", page_count=10, max_pages=8) == [5, 6, 7]
    assert parse_page_range("3,8", page_count=10, max_pages=8) == [3, 8]


@pytest.mark.parametrize("pages", ["", "7-5", "x", "0", "11", "1-9"])
def test_parse_page_range_rejects_invalid_requests(pages: str) -> None:
    with pytest.raises(PageRangeError):
        parse_page_range(pages, page_count=10, max_pages=8)


def test_pageindex_store_writes_and_reloads(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    init_workspace(workspace, model="test/model", language="en", long_doc_threshold=2)
    paths = workspace_paths(workspace)

    write_pageindex(paths, _sample_result())
    loaded = read_pageindex(paths, "paper")

    assert loaded.doc_name == "paper"
    assert loaded.page_count == 3
    assert loaded.pages[1].content == "page two"
    assert loaded.audit["status"] == "completed"
    assert "text" not in json.dumps(loaded.structure)


def test_retrieve_helpers_return_structure_and_selected_pages(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    init_workspace(workspace, model="test/model", language="en", long_doc_threshold=2)
    paths = workspace_paths(workspace)
    write_pageindex(paths, _sample_result())

    structure = get_document_structure(paths, "paper")
    content = get_page_content(paths, "paper", "1,3", max_pages=8)

    assert structure["page_count"] == 3
    assert structure["structure"][0]["title"] == "Intro"
    assert content["pages"] == [
        {"page": 1, "content": "page one"},
        {"page": 3, "content": "page three"},
    ]


def test_tree_rendering_includes_metadata_but_omits_text() -> None:
    structure = strip_text_fields(_sample_result().structure)
    rendered = render_tree(structure)

    assert "[1-2] (0001) Intro: Intro summary" in rendered
    assert "[3] (0002) Results: Results summary" in rendered
    assert "full text must not render" not in rendered


def test_tree_rendering_preserves_full_summary_text() -> None:
    long_summary = ("Detailed section summary. " * 20) + "tail marker"
    rendered = render_tree(
        [
            {
                "title": "Long",
                "node_id": "0001",
                "start_index": 1,
                "end_index": 1,
                "summary": long_summary,
            }
        ]
    )

    assert f"[1] (0001) Long: {long_summary}" in rendered
    assert "tail marker" in rendered
