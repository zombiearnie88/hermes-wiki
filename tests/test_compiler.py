from __future__ import annotations

import json
from pathlib import Path

import hermes_wiki.compiler as compiler
from hermes_wiki.pageindex.types import PageIndexBuildResult, PageRecord
from hermes_wiki.runtime import GenerationResult, HermesRuntimeError
from hermes_wiki.workspace import init_workspace, workspace_paths


def test_compile_short_doc_writes_summary_concept_and_index(tmp_path: Path, monkeypatch) -> None:
    workspace_root = tmp_path / "workspace"
    init_workspace(workspace_root, model="test/model", language="en", long_doc_threshold=20)
    paths = workspace_paths(workspace_root)

    source_path = paths.wiki_dir / "sources" / "doc.md"
    source_path.write_text("Example source text", encoding="utf-8")
    paths.schema_path.write_text("CUSTOM COMPILER SCHEMA", encoding="utf-8")
    (paths.wiki_dir / "AGENTS.md").write_text("WRONG AGENT FILE", encoding="utf-8")

    replies = iter(
        [
            json.dumps({"brief": "Short brief", "content": "# Summary\nBody"}),
            json.dumps(
                {
                    "create": [{"name": "attention", "title": "Attention"}],
                    "update": [],
                    "related": [],
                }
            ),
            json.dumps(
                {
                    "brief": "Concept brief",
                    "content": "# Attention\nConcept body with [[summaries/doc]]",
                }
            ),
        ]
    )

    calls = []

    def fake_generate_conversation(
        model: str,
        provider: str | None,
        user_message: str,
        *,
        system_message: str | None = None,
        conversation_history: list[dict] | None = None,
        task_id: str | None = None,
    ) -> GenerationResult:
        calls.append(
            {
                "model": model,
                "provider": provider,
                "user_message": user_message,
                "system_message": system_message,
                "conversation_history": conversation_history,
                "task_id": task_id,
            }
        )
        return GenerationResult(final_response=next(replies), messages=[])

    monkeypatch.setattr(compiler, "_generate_conversation", fake_generate_conversation)
    monkeypatch.setattr(compiler, "_parse_json", lambda text: json.loads(text))

    result = compiler.compile_short_doc("doc", source_path, paths, "test/model", "test-provider")

    summary_text = (workspace_root / "wiki" / "summaries" / "doc.md").read_text(encoding="utf-8")
    concept_text = (workspace_root / "wiki" / "concepts" / "attention.md").read_text(encoding="utf-8")
    index_text = (workspace_root / "wiki" / "index.md").read_text(encoding="utf-8")

    assert result.doc_brief == "Short brief"
    assert result.created_concepts == 1
    assert "# Summary" in summary_text
    assert "[[concepts/attention]]" in summary_text
    assert "Concept body" in concept_text
    assert "[[summaries/doc]]" in concept_text
    assert "[[summaries/doc]] (short) - Short brief" in index_text
    assert "[[concepts/attention]] - Concept brief" in index_text
    assert len(calls) == 3
    assert calls[0]["system_message"] is not None
    assert "CUSTOM COMPILER SCHEMA" in calls[0]["system_message"]
    assert "WRONG AGENT FILE" not in calls[0]["system_message"]
    assert calls[0]["conversation_history"] is None
    assert "Full text:\nExample source text" in calls[0]["user_message"]

    base_history = calls[1]["conversation_history"]
    assert base_history == [
        {"role": "system", "content": calls[0]["system_message"]},
        {"role": "user", "content": calls[0]["user_message"]},
        {"role": "assistant", "content": "# Summary\nBody"},
    ]
    assert calls[2]["conversation_history"] is base_history
    assert "Based on the summary above" in calls[1]["user_message"]
    assert "Existing concept pages" in calls[1]["user_message"]
    assert "Document summary:" not in calls[1]["user_message"]
    assert "# Summary\nBody" not in calls[1]["user_message"]
    assert "# Summary\nBody" not in calls[2]["user_message"]


def test_compile_short_doc_updates_existing_concept_sources(tmp_path: Path, monkeypatch) -> None:
    workspace_root = tmp_path / "workspace"
    init_workspace(workspace_root, model="test/model", language="en", long_doc_threshold=20)
    paths = workspace_paths(workspace_root)

    source_path = paths.wiki_dir / "sources" / "doc.md"
    source_path.write_text("Example source text", encoding="utf-8")
    concept_path = workspace_root / "wiki" / "concepts" / "attention.md"
    concept_path.write_text(
        "---\nsources: [summaries/older.md]\nbrief: Existing brief\n---\n\n# Attention\nOld body\n",
        encoding="utf-8",
    )

    replies = iter(
        [
            json.dumps({"brief": "Short brief", "content": "# Summary\nBody"}),
            json.dumps(
                {
                    "create": [],
                    "update": [{"name": "attention", "title": "Attention"}],
                    "related": [],
                }
            ),
            json.dumps(
                {
                    "brief": "Updated brief",
                    "content": "# Attention\nUpdated body with [[summaries/doc]]",
                }
            ),
        ]
    )

    calls = []

    def fake_generate_conversation(
        model: str,
        provider: str | None,
        user_message: str,
        *,
        system_message: str | None = None,
        conversation_history: list[dict] | None = None,
        task_id: str | None = None,
    ) -> GenerationResult:
        calls.append(
            {
                "model": model,
                "provider": provider,
                "user_message": user_message,
                "system_message": system_message,
                "conversation_history": conversation_history,
                "task_id": task_id,
            }
        )
        return GenerationResult(final_response=next(replies), messages=[])

    monkeypatch.setattr(compiler, "_generate_conversation", fake_generate_conversation)
    monkeypatch.setattr(compiler, "_parse_json", lambda text: json.loads(text))

    result = compiler.compile_short_doc("doc", source_path, paths, "test/model", "test-provider")
    updated_text = concept_path.read_text(encoding="utf-8")

    assert result.updated_concepts == 1
    assert "sources: [summaries/doc.md, summaries/older.md]" in updated_text
    assert "brief: Updated brief" in updated_text
    assert "Updated body" in updated_text
    assert len(calls) == 3
    base_history = calls[1]["conversation_history"]
    assert base_history is not None
    assert base_history[1]["content"] == calls[0]["user_message"]
    assert base_history[2] == {"role": "assistant", "content": "# Summary\nBody"}
    assert calls[2]["conversation_history"] is base_history
    assert "# Summary\nBody" not in calls[2]["user_message"]
    assert "Document summary:" not in calls[2]["user_message"]
    assert "Old body" in calls[2]["user_message"]


def test_generate_conversation_propagates_runtime_error(monkeypatch) -> None:
    def fake_generate_conversation(
        model: str,
        provider: str | None,
        user_message: str,
        *,
        system_message: str | None = None,
        conversation_history: list[dict] | None = None,
        task_id: str | None = None,
    ) -> GenerationResult:
        raise HermesRuntimeError("runtime unavailable")

    monkeypatch.setattr(compiler, "generate_conversation", fake_generate_conversation)

    try:
        compiler._generate_conversation("test/model", "test-provider", "user", system_message="system")
    except HermesRuntimeError as exc:
        assert str(exc) == "runtime unavailable"
    else:
        raise AssertionError("Expected HermesRuntimeError")


def test_parse_json_reports_missing_json_repair(monkeypatch) -> None:
    real_import = __import__

    def fake_import(name, *args, **kwargs):
        if name == "json_repair":
            raise ModuleNotFoundError("No module named 'json_repair'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)

    try:
        compiler._parse_json('{"ok": true}')
    except RuntimeError as exc:
        assert "json-repair is required" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError")


def test_compile_pageindex_doc_writes_summary_concepts_and_index(tmp_path: Path, monkeypatch) -> None:
    workspace_root = tmp_path / "workspace"
    init_workspace(workspace_root, model="test/model", language="en", long_doc_threshold=2)
    paths = workspace_paths(workspace_root)
    raw_path = paths.raw_dir / "long.pdf"
    raw_path.write_bytes(b"pdf")

    def fake_build_or_load_pageindex(doc_name, raw_path_arg, paths_arg, model, provider, *, language):
        assert doc_name == "long"
        assert raw_path_arg == raw_path
        assert paths_arg == paths
        assert model == "test/model"
        assert provider == "test-provider"
        assert language == "en"
        return PageIndexBuildResult(
            doc_name="long",
            page_count=30,
            doc_description="Long document overview",
            structure=[
                {
                    "title": "Section One",
                    "node_id": "0001",
                    "start_index": 1,
                    "end_index": 10,
                    "summary": "Section summary",
                }
            ],
            pages=[PageRecord(page=1, content="full page text that must not enter the summary")],
        )

    replies = iter(
        [
            json.dumps(
                {
                    "create": [{"name": "long-concept", "title": "Long Concept"}],
                    "update": [],
                    "related": [],
                }
            ),
            json.dumps(
                {
                    "brief": "Long concept brief",
                    "content": "# Long Concept\nConcept body with [[summaries/long]]",
                }
            ),
        ]
    )

    calls = []

    def fake_generate_conversation(
        model: str,
        provider: str | None,
        user_message: str,
        *,
        system_message: str | None = None,
        conversation_history: list[dict] | None = None,
        task_id: str | None = None,
    ) -> GenerationResult:
        calls.append(
            {
                "user_message": user_message,
                "system_message": system_message,
                "conversation_history": conversation_history,
                "task_id": task_id,
            }
        )
        return GenerationResult(final_response=next(replies), messages=[])

    monkeypatch.setattr(compiler, "build_or_load_pageindex", fake_build_or_load_pageindex)
    monkeypatch.setattr(compiler, "_generate_conversation", fake_generate_conversation)
    monkeypatch.setattr(compiler, "_parse_json", lambda text: json.loads(text))

    result = compiler.compile_pageindex_doc("long", raw_path, paths, "test/model", "test-provider")

    summary_text = (paths.wiki_dir / "summaries" / "long.md").read_text(encoding="utf-8")
    index_text = paths.index_path.read_text(encoding="utf-8")
    concept_text = (paths.wiki_dir / "concepts" / "long-concept.md").read_text(encoding="utf-8")

    assert result.created_concepts == 1
    assert "doc_type: pageindex" in summary_text
    assert "pageindex_id: long" in summary_text
    assert "full_text: pageindex/long" in summary_text
    assert "page_count: 30" in summary_text
    assert "[1-10] (0001) Section One: Section summary" in summary_text
    assert "full page text that must not enter the summary" not in summary_text
    assert 'get_document_structure("long")' in summary_text
    assert "[[summaries/long]] (pageindex) - Long document overview" in index_text
    assert "Concept body" in concept_text
    assert len(calls) == 2
    assert calls[0]["conversation_history"][2]["content"].startswith("# Summary\n\nLong document overview")
