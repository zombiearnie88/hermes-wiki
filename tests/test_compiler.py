from __future__ import annotations

import json
from pathlib import Path

import hermes_wiki.compiler as compiler
from hermes_wiki.runtime import HermesRuntimeError
from hermes_wiki.workspace import init_workspace, workspace_paths


def test_compile_short_doc_writes_summary_concept_and_index(tmp_path: Path, monkeypatch) -> None:
    workspace_root = tmp_path / "workspace"
    init_workspace(workspace_root, model="test/model", language="en", long_doc_threshold=20)
    paths = workspace_paths(workspace_root)

    source_path = paths.wiki_dir / "sources" / "doc.md"
    source_path.write_text("Example source text", encoding="utf-8")

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

    monkeypatch.setattr(compiler, "_generate_text", lambda model, system_prompt, user_prompt: next(replies))
    monkeypatch.setattr(compiler, "_parse_json", lambda text: json.loads(text))

    result = compiler.compile_short_doc("doc", source_path, paths, "test/model")

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

    monkeypatch.setattr(compiler, "_generate_text", lambda model, system_prompt, user_prompt: next(replies))
    monkeypatch.setattr(compiler, "_parse_json", lambda text: json.loads(text))

    result = compiler.compile_short_doc("doc", source_path, paths, "test/model")
    updated_text = concept_path.read_text(encoding="utf-8")

    assert result.updated_concepts == 1
    assert "sources: [summaries/doc.md, summaries/older.md]" in updated_text
    assert "brief: Updated brief" in updated_text
    assert "Updated body" in updated_text


def test_generate_text_propagates_runtime_error(monkeypatch) -> None:
    def fake_generate_text(model: str, system_prompt: str, user_prompt: str) -> str:
        raise HermesRuntimeError("runtime unavailable")

    monkeypatch.setattr(compiler, "generate_text", fake_generate_text)

    try:
        compiler._generate_text("test/model", "system", "user")
    except HermesRuntimeError as exc:
        assert str(exc) == "runtime unavailable"
    else:
        raise AssertionError("Expected HermesRuntimeError")
