# Dependency Bootstrap Patch Plan

## Goal

Make Hermes Wiki dependency installation reliable for plugin tools, slash commands, and CLI commands when the plugin is loaded from a mounted directory instead of a pip-installed package.

## Why This Patch Is Needed

- `pyproject.toml` declares `json-repair`, `pymupdf`, and `markitdown[all]`, but directory-plugin loading does not install those package dependencies.
- In the local Docker workflow, Hermes imports `hermes_wiki/` directly from the mounted plugin directory, so the plugin can load even when its runtime dependencies are missing.
- The Hermes runtime container exposes `uv` by default, but the runtime Python may not have `pip` available.
- Installing packages with a generic `python3 -m pip install ...` can target the wrong interpreter and leave the actual plugin runtime unchanged.

## Current State

- `hermes_wiki/deps.py` can detect whether `run_agent`, `json_repair`, `pymupdf`, and `markitdown` are importable.
- `wiki status` reports missing capabilities and dependency health, but it does not tell the user how to repair the runtime.
- `wiki add` can fail after partial work when conversion or compilation reaches a missing dependency.
- The repo-local Docker setup currently enables the plugin, but it does not bootstrap plugin dependencies into `/opt/hermes/.venv/bin/python`.
- The Hermes container already ships with `uv`, which is the safest default installer for this environment.

## Patch Scope

### 1. Add Runtime-Aware Dependency Metadata

Files:

- `hermes_wiki/deps.py`

Add a central dependency manifest that records:

- display label
- import module name
- package spec for installation
- related capability
- install group such as `core`, `pdf`, `office`, and `all`

Also expose the active plugin runtime Python path so status output and repair commands can target the same interpreter Hermes is actually using.

### 2. Add Explicit Dependency Repair Surface

Files:

- `hermes_wiki/schemas.py`
- `hermes_wiki/tools.py`
- `hermes_wiki/commands.py`
- `hermes_wiki/__init__.py`

Add a dedicated dependency command surface:

- tool: `wiki_deps`
- slash command: `/wiki-deps`
- CLI: `hermes wiki deps`

Expected behavior:

- default mode reports dependency health and prints the exact repair command for the active runtime
- install mode accepts `core|pdf|office|all`
- install mode uses `uv pip --python <runtime-python> install ...`
- if `uv` is not available, return a clear error instead of silently falling back to the wrong interpreter

This keeps dependency mutation explicit while making the correct repair path discoverable from inside Hermes.

### 3. Add Preflight Checks Before Ingest

Files:

- `hermes_wiki/commands.py`
- `hermes_wiki/converter.py`
- `hermes_wiki/compiler.py`

Before `wiki_add` starts conversion or generation:

- require `run_agent` and `json-repair` for summary and concept generation
- require `pymupdf` for PDF ingest
- require `markitdown[all]` for Office and HTML ingest

Return a clear blocked result before raw/source files are partially written when the required capability is unavailable.

### 4. Improve Status Output

Files:

- `hermes_wiki/commands.py`
- `hermes_wiki/deps.py`

Extend `wiki status` so it includes:

- the plugin runtime Python path
- the preferred repair command built around `uv pip --python <runtime-python>`
- capability-specific guidance for missing `json-repair`, `pymupdf`, and `markitdown[all]`

The status output should stay compact, but it should be actionable enough that an agent can repair the environment without guessing.

### 5. Add Repo-Local Runtime Bootstrap Artifact

Files:

- `hermes_wiki/requirements.txt`

Add a small runtime requirements file containing:

- `json-repair`
- `pymupdf`
- `markitdown[all]`

This gives Docker bootstrap and manual repair one shared source of truth instead of duplicating package names across scripts and docs.

### 6. Bootstrap Dependencies in Docker Dev Flow

Files:

- `docker/docker-compose.yml`
- optionally `docker/smoke-test-plugin.sh`

Update the `hermes-clinic` startup flow so it installs plugin runtime dependencies before enabling the plugin:

```bash
uv pip install --python /opt/hermes/.venv/bin/python -r /opt/data/profiles/clinic/plugins/hermes-wiki/requirements.txt
```

This should happen in the same runtime where Hermes imports and executes the plugin.

If the smoke test is extended, it should verify both plugin discovery and importability of the required modules from `/opt/hermes/.venv/bin/python`.

### 7. Update Docs And Operator Guidance

Files:

- `README.md`
- `hermes_wiki/skills/wiki-operator/SKILL.md`

Document these rules clearly:

- mounted directory plugins do not automatically install `pyproject.toml` dependencies
- prefer `uv pip --python <hermes-runtime-python> install ...`
- do not assume `python3 -m pip install ...` updates the interpreter Hermes is using
- re-run `wiki status` after dependency repair before retrying `wiki add`

### 8. Add Focused Tests

Files:

- `tests/test_commands.py`
- `tests/test_tools.py`
- add new dependency-specific tests as needed

Cover at least:

- repair command generation uses `uv pip --python ...`
- `wiki_add` blocks before side effects when required deps are missing
- `wiki_deps` reports valid JSON and install guidance
- Docker bootstrap command references the shared requirements file

## Out Of Scope

- Auto-installing dependencies inside `wiki_init` or `wiki_add` without an explicit install action.
- Changing the generation model or the summary/concept compiler prompts.
- Adding long-document support.
- Replacing directory-plugin loading with entry-point-only packaging.

## Validation Checklist

1. Confirm `wiki status` shows the active runtime Python path and a usable `uv pip --python ...` repair command.
2. Confirm `wiki_deps` can report and explicitly install missing dependency groups.
3. Confirm `wiki_add` refuses work early when a required dependency is missing.
4. Confirm the Docker clinic container installs runtime deps before enabling the plugin.
5. Confirm README and the bundled operator skill both tell agents to use `uv pip --python <runtime-python>` rather than generic `python3 -m pip install`.
6. Confirm tests cover the new dependency guidance and preflight behavior.

## Notes

- The Hermes clinic container already has `uv`, so `uv pip` should be the default installer path for this repo.
- The key design constraint is interpreter correctness: install packages into the same Python runtime that imports `hermes_wiki`, not merely the shell's default Python.
- The patch should keep dependency installation explicit and observable rather than burying package mutation inside a normal wiki command.
