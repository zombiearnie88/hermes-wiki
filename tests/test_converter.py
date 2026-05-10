from __future__ import annotations

import sys
import types
from pathlib import Path

from hermes_wiki.converter import convert_document
from hermes_wiki.workspace import init_workspace, workspace_paths


def test_convert_markdown_extension_uses_native_markdown_path(tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace"
    init_workspace(workspace_root, model="test/model", language="en", long_doc_threshold=20)
    paths = workspace_paths(workspace_root)

    source = tmp_path / "article.markdown"
    source.write_text("# Title\n\nBody text.\n", encoding="utf-8")

    result = convert_document(source, paths)

    assert result.doc_name == "article"
    assert result.source_path == workspace_root / "wiki" / "sources" / "article.md"
    assert result.source_path.read_text(encoding="utf-8") == "# Title\n\nBody text.\n"


def test_convert_txt_extension_reads_plain_text_without_markitdown(tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace"
    init_workspace(workspace_root, model="test/model", language="en", long_doc_threshold=20)
    paths = workspace_paths(workspace_root)

    source = tmp_path / "notes.txt"
    source.write_text("plain text body\n", encoding="utf-8")

    result = convert_document(source, paths)

    assert result.doc_name == "notes"
    assert result.source_path == workspace_root / "wiki" / "sources" / "notes.md"
    assert result.source_path.read_text(encoding="utf-8") == "plain text body\n"


def test_convert_html_uses_markitdown_adapter(tmp_path: Path, monkeypatch) -> None:
    workspace_root = tmp_path / "workspace"
    init_workspace(workspace_root, model="test/model", language="en", long_doc_threshold=20)
    paths = workspace_paths(workspace_root)

    source = tmp_path / "page.html"
    source.write_text("<h1>Hello</h1>", encoding="utf-8")

    class FakeResult:
        text_content = "# Converted\n"

    class FakeMarkItDown:
        def convert(self, path: str):
            assert path.endswith("page.html")
            return FakeResult()

    fake_module = types.SimpleNamespace(MarkItDown=FakeMarkItDown)
    monkeypatch.setitem(sys.modules, "markitdown", fake_module)

    result = convert_document(source, paths)

    assert result.doc_name == "page"
    assert result.source_path.read_text(encoding="utf-8") == "# Converted\n"
