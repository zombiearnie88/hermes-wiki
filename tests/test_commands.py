from __future__ import annotations

from pathlib import Path

from hermes_wiki import commands
from hermes_wiki.compiler import CompileResult


def _stub_compile(doc_name, source_path, paths, model):
    summary_path = paths.wiki_dir / "summaries" / f"{doc_name}.md"
    summary_path.write_text(
        "---\ndoc_type: short\nfull_text: sources/{0}.md\n---\n\n# Summary\n".format(doc_name),
        encoding="utf-8",
    )
    return CompileResult(doc_brief="brief", created_concepts=1, updated_concepts=0, related_concepts=0)


def test_run_init_and_status_round_trip(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"

    init_output = commands._run_init(str(workspace), "test/model", "fr", 12)
    status_output = commands._run_status(str(workspace))

    assert "Initialized Hermes wiki workspace" in init_output
    assert (workspace / "raw").is_dir()
    assert (workspace / "wiki" / "summaries").is_dir()
    assert (workspace / ".hermeskb" / "config.yaml").is_file()
    assert "Workspace: " in status_output
    assert "Model: test/model" in status_output
    assert "Language: fr" in status_output
    assert "Long-doc threshold: 12" in status_output


def test_run_add_accepts_nested_workspace_override(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    source = tmp_path / "note.md"
    source.write_text("# Note\n\nHello world.\n", encoding="utf-8")
    commands._run_init(str(workspace), "test/model", "en", 20)
    monkeypatch.setattr(commands, "compile_short_doc", _stub_compile)

    nested_override = workspace / "wiki" / "concepts"
    output = commands._run_add(str(source), str(nested_override))
    status_output = commands._run_status(str(workspace))

    assert "OK note.md" in output
    assert (workspace / "raw" / "note.md").is_file()
    assert (workspace / "wiki" / "sources" / "note.md").is_file()
    assert "Summary pages: 1" in status_output
    assert "Known hashes: 1" in status_output


def test_run_add_renames_duplicate_basenames(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    input_dir = tmp_path / "input"
    first_dir = input_dir / "a"
    second_dir = input_dir / "b"
    first_dir.mkdir(parents=True)
    second_dir.mkdir(parents=True)
    (first_dir / "dup.md").write_text("# First\n", encoding="utf-8")
    (second_dir / "dup.md").write_text("# Second\n", encoding="utf-8")

    commands._run_init(str(workspace), "test/model", "en", 20)
    monkeypatch.setattr(commands, "compile_short_doc", _stub_compile)

    output = commands._run_add(str(input_dir), str(workspace))

    assert "OK dup.md" in output
    assert "as dup-2" in output
    assert (workspace / "raw" / "dup.md").is_file()
    assert (workspace / "raw" / "dup-2.md").is_file()
    assert (workspace / "wiki" / "sources" / "dup.md").is_file()
    assert (workspace / "wiki" / "sources" / "dup-2.md").is_file()


def test_run_add_continues_after_single_file_failure(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "ok.md").write_text("# OK\n", encoding="utf-8")
    (input_dir / "bad.md").write_text("# BAD\n", encoding="utf-8")

    commands._run_init(str(workspace), "test/model", "en", 20)

    def stub_compile(doc_name, source_path, paths, model):
        if doc_name == "bad":
            raise RuntimeError("simulated compile failure")
        return _stub_compile(doc_name, source_path, paths, model)

    monkeypatch.setattr(commands, "compile_short_doc", stub_compile)

    output = commands._run_add(str(input_dir), str(workspace))
    status_output = commands._run_status(str(workspace))

    assert "OK ok.md" in output
    assert "ERROR bad.md: simulated compile failure" in output
    assert "Known hashes: 1" in status_output
    assert (workspace / "wiki" / "sources" / "ok.md").is_file()
