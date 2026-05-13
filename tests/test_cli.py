from __future__ import annotations

from pathlib import Path

import hermes_wiki.cli as cli


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


def test_run_args_add_passes_overrides(tmp_path: Path, monkeypatch) -> None:
    parser = cli.build_parser()
    source = tmp_path / "note.md"
    source.write_text("# Note\n", encoding="utf-8")
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

    monkeypatch.setattr(cli, "_run_add", fake_run_add)
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

    assert output == "ok"
    assert captured["path"] == str(source)
    assert captured["workspace"] == str(tmp_path)
    assert captured["model"] == "override/model"
    assert captured["provider"] == "override-provider"
    assert captured["language"] == "de"


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
