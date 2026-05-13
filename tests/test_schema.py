from __future__ import annotations

from pathlib import Path

from hermes_wiki.schema import get_agents_md


def test_get_agents_md_reads_workspace_root_not_wiki_dir(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    wiki_dir = workspace / "wiki"
    wiki_dir.mkdir(parents=True)
    (workspace / "AGENTS.md").write_text("ROOT AGENTS", encoding="utf-8")
    (wiki_dir / "AGENTS.md").write_text("WIKI AGENTS", encoding="utf-8")

    assert get_agents_md(wiki_dir) == "ROOT AGENTS"
