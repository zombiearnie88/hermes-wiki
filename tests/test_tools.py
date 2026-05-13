from __future__ import annotations

import json

import hermes_wiki.tools as plugin_tools
from hermes_wiki.pageindex.store import write_pageindex
from hermes_wiki.pageindex.types import PageIndexBuildResult, PageRecord
from hermes_wiki.workspace import init_workspace, workspace_paths


def test_wiki_init_returns_success_json(monkeypatch) -> None:
    domain = "AI safety evals for frontier LLMs"

    def fake_run_init(
        path: str,
        model: str,
        language: str,
        long_doc_threshold: int,
        *,
        provider: str | None = None,
        domain: str | None = None,
    ) -> str:
        assert path == "/tmp/wiki"
        assert model == "test/model"
        assert provider == "test-provider"
        assert language == "fr"
        assert long_doc_threshold == 42
        assert domain == "AI safety evals for frontier LLMs"
        return "Initialized Hermes wiki workspace at /tmp/wiki"

    monkeypatch.setattr(plugin_tools, "_run_init", fake_run_init)

    payload = json.loads(
        plugin_tools.wiki_init(
            {
                "path": "/tmp/wiki",
                "model": "test/model",
                "provider": "test-provider",
                "language": "fr",
                "long_doc_threshold": 42,
                "domain": domain,
            }
        )
    )

    assert payload["ok"] is True
    assert payload["action"] == "wiki_init"
    assert payload["path"] == "/tmp/wiki"
    assert payload["domain"] == domain
    assert "Initialized Hermes wiki workspace" in payload["output"]


def test_wiki_add_requires_path() -> None:
    payload = json.loads(plugin_tools.wiki_add({}))

    assert payload["ok"] is False
    assert payload["action"] == "wiki_add"
    assert payload["error"] == "Missing required argument: path"


def test_wiki_add_uses_workspace_config_without_model(monkeypatch) -> None:
    captured = {}

    def fake_run_add(
        path: str,
        workspace: str | None,
        model: str | None,
        language: str | None,
        provider: str | None,
    ) -> str:
        captured["path"] = path
        captured["workspace"] = workspace
        captured["model"] = model
        captured["language"] = language
        captured["provider"] = provider
        return "ok"

    monkeypatch.setattr(plugin_tools, "_run_add", fake_run_add)

    payload = json.loads(plugin_tools.wiki_add({"path": "/tmp/note.md"}))

    assert payload["ok"] is True
    assert payload["action"] == "wiki_add"
    assert captured == {
        "path": "/tmp/note.md",
        "workspace": None,
        "model": None,
        "language": None,
        "provider": None,
    }


def test_wiki_add_passes_overrides(monkeypatch) -> None:
    captured = {}

    def fake_run_add(
        path: str,
        workspace: str | None,
        model: str | None,
        language: str | None,
        provider: str | None,
    ) -> str:
        captured["path"] = path
        captured["workspace"] = workspace
        captured["model"] = model
        captured["language"] = language
        captured["provider"] = provider
        return "ok"

    monkeypatch.setattr(plugin_tools, "_run_add", fake_run_add)

    payload = json.loads(
        plugin_tools.wiki_add(
            {
                "path": "/tmp/note.md",
                "workspace": "/tmp/wiki",
                "model": "gpt-5.4-mini",
                "provider": "openai-codex",
                "language": "en",
            }
        )
    )

    assert payload["ok"] is True
    assert payload["action"] == "wiki_add"
    assert payload["model"] == "gpt-5.4-mini"
    assert payload["provider"] == "openai-codex"
    assert captured == {
        "path": "/tmp/note.md",
        "workspace": "/tmp/wiki",
        "model": "gpt-5.4-mini",
        "language": "en",
        "provider": "openai-codex",
    }


def test_wiki_status_classifies_failure_output(monkeypatch) -> None:
    monkeypatch.setattr(
        plugin_tools,
        "_run_status",
        lambda workspace: "Workspace path does not exist: /missing/workspace",
    )

    payload = json.loads(plugin_tools.wiki_status({"workspace": "/missing/workspace"}))

    assert payload["ok"] is False
    assert payload["action"] == "wiki_status"
    assert payload["workspace"] == "/missing/workspace"
    assert payload["error"] == "Workspace path does not exist: /missing/workspace"


def test_wiki_config_passes_overrides(monkeypatch) -> None:
    captured = {}

    def fake_run_config(
        workspace_override: str | None,
        *,
        model: str | None = None,
        provider: str | None = None,
        language: str | None = None,
        long_doc_threshold: int | None = None,
        concept_generation_concurrency: int | None = None,
    ) -> str:
        captured["workspace"] = workspace_override
        captured["model"] = model
        captured["provider"] = provider
        captured["language"] = language
        captured["long_doc_threshold"] = long_doc_threshold
        captured["concept_generation_concurrency"] = concept_generation_concurrency
        return "Updated workspace config."

    monkeypatch.setattr(plugin_tools, "_run_config", fake_run_config)

    payload = json.loads(
        plugin_tools.wiki_config(
            {
                "workspace": "/tmp/wiki",
                "model": "override/model",
                "provider": "override-provider",
                "language": "de",
                "long_doc_threshold": 7,
                "concept_generation_concurrency": 3,
            }
        )
    )

    assert payload["ok"] is True
    assert captured == {
        "workspace": "/tmp/wiki",
        "model": "override/model",
        "provider": "override-provider",
        "language": "de",
        "long_doc_threshold": 7,
        "concept_generation_concurrency": 3,
    }


def test_wiki_list_wraps_exceptions(monkeypatch) -> None:
    def fake_run_list(workspace_override: str | None) -> str:
        raise RuntimeError(f"cannot read {workspace_override}")

    monkeypatch.setattr(plugin_tools, "_run_list", fake_run_list)

    payload = json.loads(plugin_tools.wiki_list({"workspace": "/tmp/wiki"}))

    assert payload["ok"] is False
    assert payload["action"] == "wiki_list"
    assert payload["workspace"] == "/tmp/wiki"
    assert payload["error"] == "cannot read /tmp/wiki"


def test_wiki_deps_passes_install_group(monkeypatch) -> None:
    captured = {}

    def fake_run_deps(install: str | None = None) -> str:
        captured["install"] = install
        return "Installed dependency group 'core': json-repair"

    monkeypatch.setattr(plugin_tools, "_run_deps", fake_run_deps)

    payload = json.loads(plugin_tools.wiki_deps({"install": "core"}))

    assert payload["ok"] is True
    assert payload["action"] == "wiki_deps"
    assert payload["install"] == "core"
    assert captured["install"] == "core"


def test_wiki_deps_classifies_failure_output(monkeypatch) -> None:
    monkeypatch.setattr(
        plugin_tools,
        "_run_deps",
        lambda install: "ERROR dependency install failed: uv is unavailable",
    )

    payload = json.loads(plugin_tools.wiki_deps({"install": "all"}))

    assert payload["ok"] is False
    assert payload["action"] == "wiki_deps"
    assert payload["install"] == "all"
    assert payload["error"] == "ERROR dependency install failed: uv is unavailable"


def test_pageindex_tools_return_structure_and_guarded_pages(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    init_workspace(workspace, model="test/model", language="en", long_doc_threshold=2)
    paths = workspace_paths(workspace)
    write_pageindex(
        paths,
        PageIndexBuildResult(
            doc_name="paper",
            page_count=3,
            doc_description="Overview",
            structure=[{"title": "Intro", "node_id": "0001", "start_index": 1, "end_index": 3}],
            pages=[
                PageRecord(page=1, content="page one"),
                PageRecord(page=2, content="page two"),
                PageRecord(page=3, content="page three"),
            ],
        ),
    )

    structure_payload = json.loads(
        plugin_tools.get_document_structure({"doc_name": "paper", "workspace": str(workspace)})
    )
    content_payload = json.loads(
        plugin_tools.get_page_content({"doc_name": "paper", "pages": "1,3", "workspace": str(workspace)})
    )

    assert structure_payload["ok"] is True
    assert structure_payload["page_count"] == 3
    assert structure_payload["structure"][0]["title"] == "Intro"
    assert content_payload["ok"] is True
    assert content_payload["pages"] == [
        {"page": 1, "content": "page one"},
        {"page": 3, "content": "page three"},
    ]


def test_pageindex_tool_errors_are_structured(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    init_workspace(workspace, model="test/model", language="en", long_doc_threshold=2)

    missing_payload = json.loads(
        plugin_tools.get_document_structure({"doc_name": "missing", "workspace": str(workspace)})
    )
    invalid_payload = json.loads(
        plugin_tools.get_page_content({"doc_name": "missing", "pages": "bad", "workspace": str(workspace)})
    )

    assert missing_payload["ok"] is False
    assert missing_payload["action"] == "get_document_structure"
    assert "PageIndex document not found" in missing_payload["error"]
    assert invalid_payload["ok"] is False
