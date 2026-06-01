from __future__ import annotations

from pathlib import Path

from hermes_wiki.schema import build_agents_md
from hermes_wiki.schema import get_agents_md


def test_get_agents_md_reads_workspace_root_not_wiki_dir(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    wiki_dir = workspace / "wiki"
    wiki_dir.mkdir(parents=True)
    (workspace / "AGENTS.md").write_text("ROOT AGENTS", encoding="utf-8")
    (wiki_dir / "AGENTS.md").write_text("WIKI AGENTS", encoding="utf-8")

    assert get_agents_md(wiki_dir) == "ROOT AGENTS"


def test_build_agents_md_uses_pageindex_structure_first_and_runtime_agnostic_image_guidance() -> None:
    agents_md = build_agents_md()

    assert "inspect the document structure" in agents_md
    assert "In environments" in agents_md
    assert "that expose Hermes Wiki retrieval tools" in agents_md
    assert "get_document_structure(doc_name)" in agents_md
    assert "get_page_content(doc_name, pages)" in agents_md
    assert "If the current agent environment exposes an image-viewing tool" in agents_md
    assert "current Hermes runtime" not in agents_md
