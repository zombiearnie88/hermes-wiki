from __future__ import annotations

import json
from pathlib import Path

import hermes_wiki.cli as cli
from hermes_wiki.pageindex.store import write_pageindex
from hermes_wiki.pageindex.types import PageIndexBuildResult
from hermes_wiki.pageindex.types import PageRecord
from hermes_wiki.workspace import workspace_paths


def test_run_args_init_and_status(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    domain = "AI safety evaluations for frontier language models"
    parser = cli.build_parser()

    init_args = parser.parse_args([
        "init",
        str(workspace),
        "--model",
        "test/model",
        "--provider",
        "test-provider",
        "--language",
        "en",
        "--domain",
        domain,
    ])
    init_output = cli.run_args(init_args)

    status_args = parser.parse_args(["status", "--workspace", str(workspace)])
    status_output = cli.run_args(status_args)
    schema_text = (workspace / "wiki" / "SCHEMA.md").read_text(encoding="utf-8")

    assert "Initialized Hermes wiki workspace" in init_output
    assert "Workspace: " in status_output
    assert "Model: test/model" in status_output
    assert "Provider: test-provider" in status_output
    assert f"## Domain\n{domain}" in schema_text


def test_main_prints_output(tmp_path: Path, capsys) -> None:
    workspace = tmp_path / "workspace"

    exit_code = cli.main(["init", str(workspace)])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "Initialized Hermes wiki workspace" in captured.out


def test_main_returns_nonzero_for_missing_workspace(capsys) -> None:
    exit_code = cli.main(["status", "--workspace", "/definitely/missing/workspace"])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "Workspace path does not exist" in captured.out


def test_main_returns_nonzero_for_invalid_settings(tmp_path: Path, capsys) -> None:
    workspace = tmp_path / "workspace"

    exit_code = cli.main(["init", str(workspace), "--model", ""])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "Model must not be empty" in captured.err


def test_run_args_add_fails_without_plugin_llm(tmp_path: Path) -> None:
    parser = cli.build_parser()
    source = tmp_path / "note.md"
    source.write_text("# Note\n", encoding="utf-8")
    args = parser.parse_args([
        "add",
        str(source),
        "--workspace",
        str(tmp_path),
        "--model",
        "override/model",
        "--provider",
        "override-provider",
        "--language",
        "de",
    ])

    output = cli.run_args(args)

    assert output.startswith("ERROR wiki add requires Hermes plugin runtime LLM access")
    assert "standalone hermes-wiki add" in output


def test_run_args_config_updates_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    parser = cli.build_parser()

    cli.run_args(parser.parse_args(["init", str(workspace)]))
    output = cli.run_args(
        parser.parse_args(
            [
                "config",
                "--workspace",
                str(workspace),
                "--model",
                "updated/model",
                "--provider",
                "updated-provider",
                "--language",
                "it",
                "--long-doc-threshold",
                "77",
                "--concept-generation-concurrency",
                "3",
            ]
        )
    )

    assert "Updated workspace config." in output
    assert "Model: updated/model" in output
    assert "Provider: updated-provider" in output
    assert "Language: it" in output
    assert "Long-doc threshold: 77" in output
    assert "Concept generation concurrency: 3" in output


def test_run_args_list_reads_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    parser = cli.build_parser()

    cli.run_args(parser.parse_args(["init", str(workspace)]))
    (workspace / ".hermeskb" / "hashes.json").write_text(
        '{\n  "abc": {"name": "notes.md", "type": "md", "doc_name": "notes"}\n}',
        encoding="utf-8",
    )

    output = cli.run_args(parser.parse_args(["list", "--workspace", str(workspace)]))

    assert "Documents:" in output
    assert "- notes (md) <- notes.md" in output


def test_run_args_deps_passes_install_group(monkeypatch) -> None:
    parser = cli.build_parser()
    captured = {}

    def fake_run_deps(install: str | None = None) -> str:
        captured["install"] = install
        return "ok"

    monkeypatch.setattr(cli, "_run_deps", fake_run_deps)

    output = cli.run_args(parser.parse_args(["deps", "--install", "office"]))

    assert output == "ok"
    assert captured["install"] == "office"


def test_run_args_pageindex_retrieval_commands(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    parser = cli.build_parser()

    cli.run_args(parser.parse_args(["init", str(workspace)]))
    write_pageindex(
        workspace_paths(workspace),
        PageIndexBuildResult(
            doc_name="paper",
            page_count=3,
            doc_description="Overview",
            structure=[
                {
                    "title": "Intro",
                    "node_id": "0001",
                    "start_index": 1,
                    "end_index": 3,
                    "summary": "Intro summary",
                }
            ],
            pages=[
                PageRecord(page=1, content="page one"),
                PageRecord(page=2, content="page two"),
                PageRecord(page=3, content="page three"),
            ],
        ),
    )

    structure_output = cli.run_args(
        parser.parse_args(["get-document-structure", "--workspace", str(workspace), "--doc-name", "paper"])
    )
    content_output = cli.run_args(
        parser.parse_args(["get-page-content", "--workspace", str(workspace), "--doc-name", "paper", "--pages", "2-3"])
    )
    content_json = json.loads(
        cli.run_args(
            parser.parse_args(
                [
                    "get-page-content",
                    "--workspace",
                    str(workspace),
                    "--doc-name",
                    "paper",
                    "--pages",
                    "2-3",
                    "--json",
                ]
            )
        )
    )

    assert "Structure:" in structure_output
    assert "Intro summary" in structure_output
    assert "[Page 2]" in content_output
    assert content_json["ok"] is True
    assert content_json["pages"][0] == {"page": 2, "content": "page two"}


def test_main_returns_nonzero_for_json_pageindex_error(tmp_path: Path, capsys) -> None:
    workspace = tmp_path / "workspace"

    cli.main(["init", str(workspace)])
    capsys.readouterr()
    exit_code = cli.main(
        [
            "get-page-content",
            "--workspace",
            str(workspace),
            "--doc-name",
            "missing",
            "--pages",
            "1",
            "--json",
        ]
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 1
    assert payload["ok"] is False
    assert payload["action"] == "get_page_content"
