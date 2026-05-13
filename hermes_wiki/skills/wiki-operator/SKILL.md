---
name: wiki-operator
description: Operate the hermes-wiki plugin to initialize, inspect, configure, and ingest Hermes wiki workspaces.
version: 0.1.0
author: Thach Duong
metadata:
  hermes:
    tags: [wiki, knowledge-base, plugin]
---

# Hermes Wiki Operator

Use this skill when the user wants to initialize, inspect, configure, or ingest a Hermes Wiki workspace.

## When To Use

- create a new Hermes Wiki workspace
- check workspace health or generation readiness
- update workspace config such as model, provider, language, or long-doc threshold
- ingest supported files or directories into the wiki

## Preferred Surfaces

Use the plugin tools first when they are available:

- `wiki_init`
- `wiki_add`
- `wiki_status`
- `wiki_config`
- `wiki_list`
- `wiki_deps`
- `get_document_structure`
- `get_page_content`

If slash commands are the active surface in the current Hermes session, use:

```text
/wiki-init <path> --domain <domain>
/wiki-status [--workspace <path>]
/wiki-list [--workspace <path>]
/wiki-config --workspace <path> --model <model> --provider <provider> ...
/wiki-add <path> --workspace <workspace>
/wiki-deps [--install core|pdf|office|all]
```

If plugin tools are unavailable but terminal access is available, use the Hermes CLI subcommands:

```bash
hermes wiki init <path> --domain <domain>
hermes wiki status --workspace <path>
hermes wiki list --workspace <path>
hermes wiki config --workspace <path> --model <model> --provider <provider> ...
hermes wiki add <path> --workspace <workspace>
hermes wiki deps [--install core|pdf|office|all]
```

Use the standalone `hermes-wiki` executable only as a development fallback outside a Hermes runtime:

```bash
hermes-wiki init <path> --domain <domain>
hermes-wiki status --workspace <path>
hermes-wiki list --workspace <path>
hermes-wiki config --workspace <path> --model <model> --provider <provider> ...
hermes-wiki add <path> --workspace <workspace>
hermes-wiki deps [--install core|pdf|office|all]
```

## Model Selection

- Store generation routing in `.hermeskb/config.yaml` via `wiki_config`; normal `wiki_add` calls should use the stored model and provider.
- Use `wiki_config` to set `model` and `provider` before ingest if the workspace config is missing, stale, or incompatible with the user's runtime.
- Do not pass `model` or `provider` to `wiki_add` unless the user explicitly asks for a one-off override.
- For Docker ChatGPT/Codex sessions, use `model: gpt-5.4-mini` and `provider: openai-codex` or another model ID listed by the Hermes Codex provider.
- Do not use `openai/gpt-*` model IDs with `provider: openai-codex`; use the unprefixed Codex model ID such as `gpt-5.4-mini`.
- If the right model/provider is unclear, ask the user or inspect workspace status/config before changing it.

Do not manually create or rewrite the wiki structure unless the user explicitly asks.

## Workspace Rules

- A Hermes Wiki workspace root contains `raw/`, `wiki/`, and `.hermeskb/`.
- Generated content lives under `wiki/`; runtime state lives under `.hermeskb/`.
- Prefer one workspace path per task and keep using the same path consistently.
- If the workspace already exists, do not reinitialize it unless the user asks.

## Initialization

- Resolve the intended workspace path before calling `wiki_init`.
- Ask the user what domain the wiki covers unless the domain is already specified.
- Ask for specificity, for example `AI safety evals for frontier LLMs`, not just `AI`.
- If the user answers in another language, translate the domain to concise English before initialization.
- If translating would change meaning or the answer is ambiguous, ask one clarification before initialization.
- Pass the concise English domain as `domain` to `wiki_init`, `/wiki-init`, or the CLI init command; init writes that value into `wiki/SCHEMA.md`.
- If initialization must run non-interactively without a domain, the tool will write an unspecified-domain placeholder; clarify the domain before major ingest.

## Operating Procedure

1. Resolve the intended workspace path.
2. If the user wants to inspect or ingest an existing workspace, check status first when practical.
3. Read the `Capabilities:` section before attempting ingest so you know whether generation or format support is blocked.
4. If the user asks to initialize a workspace, ask for a specific domain unless already known, translate it to concise English if needed, then run `wiki_init` or the equivalent CLI command with the English `domain`.
5. If the user asks to ingest content, use `wiki_add` with the correct workspace path.
6. If the user asks what is already present, use `wiki_list`.
7. Report the plugin output clearly, especially for blocked capabilities, skipped files, PageIndex builds, and guarded retrieval errors.

## Capability Checks

Important blockers from `wiki_status`:

- `summary and concept generation` requires Hermes runtime and `json-repair`
- `pdf ingest` requires PyMuPDF
- `office/html ingest` requires MarkItDown
- Long-PDF PageIndex ingest requires Hermes runtime, `json-repair`, and PyMuPDF

If a needed capability is blocked, say so clearly before continuing.

## Dependency Repair

- If `wiki_status` shows missing `json-repair`, `PyMuPDF`, or `MarkItDown`, prefer `wiki_deps` when that tool surface is available.
- If `wiki_deps` is unavailable, install the packages into the Python runtime that is actually importing the plugin.
- Prefer `uv pip install --python <hermes-runtime-python> json-repair pymupdf 'markitdown[all]'`.
- In Docker, prefer the mounted `requirements.txt` with `uv pip install --python <hermes-runtime-python> -r <plugin>/requirements.txt` when the path is known.
- In this repo's Docker clinic container, `<hermes-runtime-python>` is typically `/opt/hermes/.venv/bin/python`.
- In this repo's Docker WebUI container, `<hermes-runtime-python>` is typically `/app/venv/bin/python3`.
- Do not assume `python3 -m pip install ...` touched the same interpreter Hermes is using.
- Re-run `wiki_status` after repairing dependencies before retrying `wiki_add`.

## Plugin Load Debugging

- A plugin can be enabled in `config.yaml` but disabled at runtime if import fails during plugin loading.
- For `hermes-webui`, `plugins.enabled: [hermes-wiki]` and `plugins.disabled: []` does not prove that the plugin registered successfully.
- If the WebUI reports the plugin unavailable, inspect the runtime plugin manager error; `No module named 'hermes_wiki'` usually means a directory-plugin import path problem, not a config disablement.
- A healthy WebUI container only proves the web server is running; it does not prove plugin import succeeded.

## Failure Cases

- Long PDFs route through PageIndex once they meet or exceed the configured threshold.
- Long non-PDF documents are not supported yet.
- Use `get_document_structure` before `get_page_content` and fetch tight page ranges only.
- Existing workspaces should be reused rather than recreated.
- Unsupported file types should be surfaced clearly instead of being forced through the ingest path.

## Verification

- Use `wiki_status` to verify workspace health and capability readiness.
- Use `wiki_list` to verify documents and concept pages after ingest.
- When `wiki_add` succeeds, confirm the output mentions summaries and concept updates or creation counts.
- For PageIndex documents, use `get_document_structure` and a small `get_page_content` range to verify retrieval.
