from __future__ import annotations

import asyncio
from pathlib import Path

from hermes_wiki import commands
from hermes_wiki.compiler import CompileResult
from hermes_wiki.converter import ConvertResult
from hermes_wiki.deps import CapabilityStatus
from hermes_wiki.deps import DependencyInstallResult
from hermes_wiki.deps import DependencyStatus


async def _stub_compile(llm, doc_name, source_path, paths, model, provider=None, *, language_override=None):
    summary_path = paths.wiki_dir / "summaries" / f"{doc_name}.md"
    summary_path.write_text(
        "---\ndoc_type: short\nfull_text: sources/{0}.md\n---\n\n# Summary\n".format(doc_name),
        encoding="utf-8",
    )
    return CompileResult(doc_brief="brief", created_concepts=1, updated_concepts=0, related_concepts=0)


def _allow_add_requirements(monkeypatch) -> None:
    monkeypatch.setattr(commands, "_check_add_requirements", lambda files, **kwargs: None)


def test_run_init_and_status_round_trip(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"

    init_output = commands._run_init(str(workspace), "test/model", "fr", 12)
    status_output = commands._run_status(str(workspace))
    schema_text = (workspace / "wiki" / "SCHEMA.md").read_text(encoding="utf-8")

    assert "Initialized Hermes wiki workspace" in init_output
    assert (workspace / "raw").is_dir()
    assert (workspace / "wiki" / "summaries").is_dir()
    assert (workspace / ".hermeskb" / "config.yaml").is_file()
    assert "Workspace: " in status_output
    assert "Model: test/model" in status_output
    assert "Provider: openai-codex" in status_output
    assert "Language: fr" in status_output
    assert "Long-doc threshold: 12" in status_output
    assert "Concept generation concurrency: 3" in status_output
    assert "Capabilities:" in status_output
    assert "Dependencies:" in status_output
    assert "Unspecified. Ask the user to clarify the wiki domain before major ingest." in schema_text


def test_run_init_writes_domain_schema_and_agent_guidance(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    domain = "AI safety evaluations for frontier language models"

    commands._run_init(str(workspace), "test/model", "en", 20, domain=domain)

    schema_text = (workspace / "wiki" / "SCHEMA.md").read_text(encoding="utf-8")
    agents_text = (workspace / "AGENTS.md").read_text(encoding="utf-8")

    assert f"## Domain\n{domain}" in schema_text
    assert "## PageIndex Summary Rules" in schema_text
    assert "`doc_type: short`" in schema_text
    assert "`doc_type: pageindex`" in schema_text
    assert "wiki/SCHEMA.md" in agents_text
    assert "## Summary Frontmatter" not in agents_text


def test_wiki_init_slash_command_accepts_domain(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    domain = "AI safety evals for frontier LLMs"

    output = commands.handle_wiki_init_command(f"{workspace} --domain '{domain}'")

    schema_text = (workspace / "wiki" / "SCHEMA.md").read_text(encoding="utf-8")
    assert "Initialized Hermes wiki workspace" in output
    assert f"## Domain\n{domain}" in schema_text


def test_run_add_accepts_nested_workspace_override(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    source = tmp_path / "note.md"
    source.write_text("# Note\n\nHello world.\n", encoding="utf-8")
    commands._run_init(str(workspace), "test/model", "en", 20)
    monkeypatch.setattr(commands, "compile_short_doc_async", _stub_compile)
    _allow_add_requirements(monkeypatch)

    nested_override = workspace / "wiki" / "concepts"
    output = asyncio.run(commands._run_add_async(str(source), str(nested_override), llm="fake-llm"))
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
    monkeypatch.setattr(commands, "compile_short_doc_async", _stub_compile)
    _allow_add_requirements(monkeypatch)

    output = asyncio.run(commands._run_add_async(str(input_dir), str(workspace), llm="fake-llm"))

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
    _allow_add_requirements(monkeypatch)

    async def stub_compile(llm, doc_name, source_path, paths, model, provider, *, language_override=None):
        if doc_name == "bad":
            raise RuntimeError("simulated compile failure")
        return await _stub_compile(llm, doc_name, source_path, paths, model, provider, language_override=language_override)

    monkeypatch.setattr(commands, "compile_short_doc_async", stub_compile)

    output = asyncio.run(commands._run_add_async(str(input_dir), str(workspace), llm="fake-llm"))
    status_output = commands._run_status(str(workspace))

    assert "OK ok.md" in output
    assert "ERROR bad.md: simulated compile failure" in output
    assert "Known hashes: 1" in status_output
    assert (workspace / "wiki" / "sources" / "ok.md").is_file()


def test_run_add_reuses_doc_name_after_failed_attempt(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    source = tmp_path / "retry.md"
    source.write_text("# Retry\n", encoding="utf-8")
    commands._run_init(str(workspace), "test/model", "en", 20)
    _allow_add_requirements(monkeypatch)

    attempts = {"count": 0}

    async def flaky_compile(llm, doc_name, source_path, paths, model, provider, *, language_override=None):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("first attempt failed")
        return await _stub_compile(llm, doc_name, source_path, paths, model, provider, language_override=language_override)

    monkeypatch.setattr(commands, "compile_short_doc_async", flaky_compile)

    first_output = asyncio.run(commands._run_add_async(str(source), str(workspace), llm="fake-llm"))
    second_output = asyncio.run(commands._run_add_async(str(source), str(workspace), llm="fake-llm"))

    assert "ERROR retry.md: first attempt failed" in first_output
    assert "OK retry.md" in second_output
    assert "as retry-2" not in second_output
    assert (workspace / "raw" / "retry.md").is_file()
    assert not (workspace / "raw" / "retry-2.md").exists()
    assert (workspace / "wiki" / "sources" / "retry.md").is_file()


def test_run_status_includes_dependency_health(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    commands._run_init(str(workspace), "test/model", "en", 20)

    monkeypatch.setattr(
        commands,
        "capability_statuses",
        lambda **kwargs: [
            CapabilityStatus(label="markdown/text/csv ingest", ready=True, detail="built in"),
            CapabilityStatus(
                label="summary and concept generation",
                ready=False,
                detail="plugin LLM access unavailable outside Hermes plugin runtime",
            ),
        ],
    )
    monkeypatch.setattr(
        commands,
        "dependency_statuses",
        lambda: [DependencyStatus(label="json-repair", module_name="json_repair", available=True)],
    )

    output = commands._run_status(str(workspace))

    assert "Capabilities:" in output
    assert "- markdown/text/csv ingest: ready (built in)" in output
    assert (
        "- summary and concept generation: blocked "
        "(plugin LLM access unavailable outside Hermes plugin runtime)" in output
    )
    assert "Dependencies:" in output
    assert "- json-repair: available" in output


def test_run_add_passes_model_provider_and_language_overrides(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    source = tmp_path / "note.md"
    source.write_text("# Note\n", encoding="utf-8")
    commands._run_init(str(workspace), "workspace/model", "en", 20)
    captured = {}
    _allow_add_requirements(monkeypatch)

    async def capture_compile(llm, doc_name, source_path, paths, model, provider, *, language_override=None):
        captured["llm"] = llm
        captured["doc_name"] = doc_name
        captured["model"] = model
        captured["provider"] = provider
        captured["language_override"] = language_override
        return await _stub_compile(llm, doc_name, source_path, paths, model, provider)

    monkeypatch.setattr(commands, "compile_short_doc_async", capture_compile)

    output = asyncio.run(
        commands._run_add_async(
            str(source),
            str(workspace),
            model_override="override/model",
            language_override="de",
            provider_override="override-provider",
            llm="fake-llm",
        )
    )

    assert "OK note.md" in output
    assert captured["llm"] == "fake-llm"
    assert captured["doc_name"] == "note"
    assert captured["model"] == "override/model"
    assert captured["provider"] == "override-provider"
    assert captured["language_override"] == "de"


def test_run_deps_reports_runtime_and_group_commands(monkeypatch) -> None:
    monkeypatch.setattr(commands, "runtime_python_path", lambda: "/runtime/python")
    monkeypatch.setattr(
        commands,
        "capability_statuses",
        lambda **kwargs: [
            CapabilityStatus(label="summary and concept generation", ready=False, detail="missing json-repair"),
            CapabilityStatus(label="pdf ingest", ready=False, detail="missing PyMuPDF"),
        ],
    )
    monkeypatch.setattr(
        commands,
        "dependency_statuses",
        lambda: [
            DependencyStatus(label="json-repair", module_name="json_repair", available=False),
            DependencyStatus(label="PyMuPDF", module_name="pymupdf", available=False),
            DependencyStatus(label="MarkItDown", module_name="markitdown", available=True),
        ],
    )

    def fake_build(group: str = "all", *, missing_only: bool = False) -> str | None:
        assert missing_only is True
        commands_map = {
            "core": "uv pip install --python /runtime/python json-repair",
            "pdf": "uv pip install --python /runtime/python pymupdf",
            "office": None,
            "all": "uv pip install --python /runtime/python json-repair pymupdf",
        }
        return commands_map[group]

    monkeypatch.setattr(commands, "build_uv_install_command", fake_build)

    output = commands._run_deps()

    assert "Runtime Python: /runtime/python" in output
    assert "Repair:" in output
    assert "Install missing core: uv pip install --python /runtime/python json-repair" in output
    assert "Install missing pdf: uv pip install --python /runtime/python pymupdf" in output
    assert "Install all missing packages: uv pip install --python /runtime/python json-repair pymupdf" in output


def test_run_deps_install_reports_success(monkeypatch) -> None:
    monkeypatch.setattr(commands, "runtime_python_path", lambda: "/runtime/python")
    monkeypatch.setattr(
        commands,
        "install_dependency_group",
        lambda group, missing_only=True: DependencyInstallResult(
            group=group,
            packages=("json-repair",),
            command="uv pip install --python /runtime/python json-repair",
            exit_code=0,
            stdout="installed",
            stderr="",
        ),
    )
    monkeypatch.setattr(
        commands,
        "capability_statuses",
        lambda **kwargs: [
            CapabilityStatus(label="summary and concept generation", ready=True, detail="plugin LLM access + json-repair")
        ],
    )
    monkeypatch.setattr(
        commands,
        "dependency_statuses",
        lambda: [
            DependencyStatus(label="json-repair", module_name="json_repair", available=True),
        ],
    )
    monkeypatch.setattr(commands, "build_uv_install_command", lambda group="all", *, missing_only=False: None)

    output = commands._run_deps("core")

    assert "Installed dependency group 'core': json-repair" in output
    assert "Command: uv pip install --python /runtime/python json-repair" in output
    assert "Runtime Python: /runtime/python" in output


def test_run_add_blocks_before_side_effects_when_requirements_missing(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    source = tmp_path / "note.md"
    source.write_text("# Note\n", encoding="utf-8")
    commands._run_init(str(workspace), "workspace/model", "en", 20)
    monkeypatch.setattr(
        commands,
        "_check_add_requirements",
        lambda files, **kwargs: "ERROR wiki add is blocked by missing runtime dependencies.\nRuntime Python: /runtime/python",
    )

    output = asyncio.run(commands._run_add_async(str(source), str(workspace), llm="fake-llm"))

    assert output.startswith("ERROR wiki add is blocked by missing runtime dependencies.")
    assert not (workspace / "raw" / "note.md").exists()
    assert not (workspace / "wiki" / "sources" / "note.md").exists()


def test_run_config_reads_and_updates_workspace_config(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    commands._run_init(str(workspace), "initial/model", "en", 20)

    before = commands._run_config(str(workspace))
    after = commands._run_config(
        str(workspace),
        model="updated/model",
        provider="updated-provider",
        language="fr",
        long_doc_threshold=55,
        concept_generation_concurrency=3,
    )

    assert "Model: initial/model" in before
    assert "Provider: openai-codex" in before
    assert "Updated workspace config." in after
    assert "Model: updated/model" in after
    assert "Provider: updated-provider" in after
    assert "Language: fr" in after
    assert "Long-doc threshold: 55" in after
    assert "Concept generation concurrency: 3" in after


def test_run_init_rejects_invalid_settings(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"

    try:
        commands._run_init(str(workspace), "", "en", 20)
    except ValueError as exc:
        assert "Model must not be empty" in str(exc)
    else:
        raise AssertionError("Expected ValueError")

    try:
        commands._run_init(str(workspace), "test/model", "", 20)
    except ValueError as exc:
        assert "Language must not be empty" in str(exc)
    else:
        raise AssertionError("Expected ValueError")

    try:
        commands._run_init(str(workspace), "test/model", "en", 0)
    except ValueError as exc:
        assert "Long-doc threshold must be greater than zero" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_run_config_and_add_reject_invalid_overrides(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    source = tmp_path / "note.md"
    source.write_text("# Note\n", encoding="utf-8")
    commands._run_init(str(workspace), "initial/model", "en", 20)

    try:
        commands._run_config(str(workspace), long_doc_threshold=-1)
    except ValueError as exc:
        assert "Long-doc threshold must be greater than zero" in str(exc)
    else:
        raise AssertionError("Expected ValueError")

    try:
        asyncio.run(commands._run_add_async(str(source), str(workspace), model_override="", llm="fake-llm"))
    except ValueError as exc:
        assert "Model must not be empty" in str(exc)
    else:
        raise AssertionError("Expected ValueError")

    try:
        asyncio.run(commands._run_add_async(str(source), str(workspace), provider_override="", llm="fake-llm"))
    except ValueError as exc:
        assert "Provider must not be empty" in str(exc)
    else:
        raise AssertionError("Expected ValueError")

    try:
        asyncio.run(commands._run_add_async(str(source), str(workspace), language_override="", llm="fake-llm"))
    except ValueError as exc:
        assert "Language must not be empty" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_handle_wiki_status_command_reports_corrupt_hash_registry(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    commands._run_init(str(workspace), "test/model", "en", 20)
    (workspace / ".hermeskb" / "hashes.json").write_text("{broken", encoding="utf-8")

    output = commands.handle_wiki_status_command(f"--workspace {workspace}")

    assert "Failed to read status: Hash registry is corrupt" in output


def test_run_list_shows_documents_and_concepts(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    commands._run_init(str(workspace), "test/model", "en", 20)
    hashes_path = workspace / ".hermeskb" / "hashes.json"
    hashes_path.write_text(
        '{\n  "abc": {"name": "paper.pdf", "type": "pdf", "doc_name": "paper"},\n  "def": {"name": "notes.md", "type": "md", "doc_name": "notes"}\n}',
        encoding="utf-8",
    )
    (workspace / "wiki" / "concepts" / "attention.md").write_text("# Attention\n", encoding="utf-8")

    output = commands._run_list(str(workspace))

    assert "Documents:" in output
    assert "- notes (md) <- notes.md" in output
    assert "- paper (pdf) <- paper.pdf" in output
    assert "Concepts:" in output
    assert "- attention" in output


def test_run_add_routes_long_pdf_to_pageindex(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    source = tmp_path / "long.pdf"
    source.write_bytes(b"pdf")
    commands._run_init(str(workspace), "test/model", "en", 2)
    paths = commands.workspace_paths(workspace)
    raw_path = paths.raw_dir / "long.pdf"
    _allow_add_requirements(monkeypatch)

    monkeypatch.setattr(
        commands,
        "convert_document",
        lambda file_path, paths_arg: ConvertResult(
            doc_name="long",
            raw_path=raw_path,
            file_hash="hash-long",
            unsupported_long_doc=True,
            long_doc_page_count=30,
        ),
    )

    captured = {}

    async def fake_compile_pageindex(llm, doc_name, raw_path_arg, paths_arg, model, provider, *, language_override=None):
        captured["llm"] = llm
        captured["doc_name"] = doc_name
        captured["raw_path"] = raw_path_arg
        captured["model"] = model
        captured["provider"] = provider
        captured["language_override"] = language_override
        (paths_arg.wiki_dir / "summaries" / f"{doc_name}.md").write_text(
            "---\ndoc_type: pageindex\nfull_text: pageindex/long\n---\n\n# Summary\n",
            encoding="utf-8",
        )
        return CompileResult(doc_brief="brief", created_concepts=2, updated_concepts=1, related_concepts=0)

    monkeypatch.setattr(commands, "compile_pageindex_doc_async", fake_compile_pageindex)

    output = asyncio.run(
        commands._run_add_async(str(source), str(workspace), provider_override="test-provider", llm="fake-llm")
    )
    list_output = commands._run_list(str(workspace))

    assert "OK long.pdf: pageindex summary written (30 pages), created 2, updated 1, related 0" in output
    assert captured["llm"] == "fake-llm"
    assert captured["doc_name"] == "long"
    assert captured["raw_path"] == raw_path
    assert captured["provider"] == "test-provider"
    assert "- long (pageindex) <- long.pdf" in list_output


def test_failed_pageindex_build_does_not_register_hash(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    source = tmp_path / "long.pdf"
    source.write_bytes(b"pdf")
    commands._run_init(str(workspace), "test/model", "en", 2)
    paths = commands.workspace_paths(workspace)
    _allow_add_requirements(monkeypatch)

    monkeypatch.setattr(
        commands,
        "convert_document",
        lambda file_path, paths_arg: ConvertResult(
            doc_name="long",
            raw_path=paths.raw_dir / "long.pdf",
            file_hash="hash-long",
            unsupported_long_doc=True,
            long_doc_page_count=30,
        ),
    )
    monkeypatch.setattr(
        commands,
        "compile_pageindex_doc_async",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("pageindex failed")),
    )

    output = asyncio.run(commands._run_add_async(str(source), str(workspace), llm="fake-llm"))
    status_output = commands._run_status(str(workspace))

    assert "ERROR long.pdf: pageindex failed" in output
    assert "Known hashes: 0" in status_output
