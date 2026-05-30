---
name: hermes-wiki
description: Hermes wiki, hermes wiki, wiki init, wiki add, wiki status. Use ONLY when the user wants OpenCode to operate a locally installed Hermes Wiki runtime through `hermes wiki ...` commands.
---

# Hermes Wiki Operator

Use this skill when the user wants to initialize, inspect, configure, or ingest a Hermes Wiki workspace through a locally installed Hermes runtime.

This skill is an operator wrapper around Hermes CLI commands. Do not re-implement wiki generation in OpenCode.

## Use Only When

- the user wants to work with a Hermes Wiki workspace
- the user mentions `hermes wiki`, `wiki init`, `wiki add`, `wiki status`, `wiki list`, or `wiki config`
- the user wants OpenCode to drive an already installed local Hermes Wiki setup
- the user wants documents ingested into the existing Hermes Wiki workflow

Do not use this skill for general markdown editing, generic note-taking, or building a separate non-Hermes wiki system.

## Core Rule

Prefer the Hermes CLI as the control surface:

```bash
hermes wiki init <path> --domain "<domain>"
hermes wiki status --workspace <path>
hermes wiki list --workspace <path>
hermes wiki config --workspace <path> --model <model> --provider <provider> --language <lang>
hermes wiki add <path> --workspace <workspace>
hermes wiki deps --install all
```

Do not use standalone `hermes-wiki add`. It cannot generate summaries or concepts because it does not have Hermes plugin runtime LLM access.

## Goals

- keep Hermes Wiki as the single source of truth
- reuse the existing workspace layout and generation flow
- avoid re-implementing summary or concept generation in OpenCode
- surface Hermes errors clearly and act as a reliable operator

## Workspace Expectations

A Hermes Wiki workspace contains:

```text
raw/
wiki/
.hermeskb/
AGENTS.md
```

Generated wiki content lives under `wiki/`. Runtime state lives under `.hermeskb/`.

If the workspace already exists, reuse it. Do not reinitialize unless the user explicitly asks.

## Operating Procedure

1. Resolve the intended workspace path.
2. If the user wants to inspect or ingest an existing workspace, check status first when practical.
3. Read the capability and dependency output before attempting ingest.
4. If the workspace does not exist and the user wants one, initialize it with a specific domain.
5. If model or provider settings are missing or wrong, update them with `hermes wiki config` before ingest.
6. Use `hermes wiki add` for actual ingest and generation.
7. Use `hermes wiki list` and `hermes wiki status` to verify results.
8. Report Hermes output clearly, especially for blocked capabilities, skipped files, dependency problems, and unsupported long-doc cases.

## Initialization Rules

Before running `hermes wiki init`:

- resolve the intended workspace path
- ask the user what domain the wiki covers unless already known
- ask for a specific domain, not a vague label
- if the user answers in another language, translate the domain to concise English
- preserve the user's intended meaning
- if the domain is ambiguous, ask one short clarification

Example:

```bash
hermes wiki init ./research-wiki --domain "AI safety evaluations for frontier language models"
```

## Model and Provider Rules

- use persisted workspace settings by default
- prefer `hermes wiki config` to set `model` and `provider` before ingest
- do not pass one-off `--model` or `--provider` to `hermes wiki add` unless the user explicitly asks
- for Docker ChatGPT or Codex sessions, prefer unprefixed Codex model IDs such as `gpt-5.4-mini` with provider `openai-codex`
- do not use `openai/gpt-*` model IDs with provider `openai-codex`

Example:

```bash
hermes wiki config --workspace ./research-wiki --model gpt-5.4-mini --provider openai-codex --language en
```

## Ingest Rules

Use `hermes wiki add` when the user wants summaries and concept pages created or updated.

Example:

```bash
hermes wiki add ./docs --workspace ./research-wiki
```

Before ingest:

- confirm the workspace exists
- check status if the environment may be misconfigured
- make sure required dependencies are available
- make sure the model and provider configuration matches the intended runtime

Do not manually create summary pages or concept pages unless the user explicitly asks for manual edits.

## Capability Checks

Important blockers from `hermes wiki status` may include:

- missing Hermes plugin LLM access
- missing `json-repair`
- missing `pymupdf`
- missing `markitdown`

If ingest is blocked, say so clearly before retrying.

## Dependency Repair

If dependencies are missing, prefer the Hermes-managed repair path first:

```bash
hermes wiki deps --install all
```

If the user wants a narrower install, use one of:

```bash
hermes wiki deps --install core
hermes wiki deps --install pdf
hermes wiki deps --install office
```

After repair, re-run:

```bash
hermes wiki status --workspace <path>
```

before retrying ingest.

## Long-Document Rules

- long PDFs may route through PageIndex
- unsupported long non-PDF workflows should be surfaced clearly
- do not invent fallback behavior
- prefer the Hermes workflow and its guardrails

## Verification

After a successful operation, prefer verifying with Hermes commands:

```bash
hermes wiki status --workspace <path>
hermes wiki list --workspace <path>
```

When ingest succeeds, confirm whether summaries and concepts were created or updated.

## Failure Handling

If Hermes is not installed, the plugin is unavailable, or the command fails:

- report the exact blocking condition
- suggest the smallest next step
- do not pretend the wiki was updated
- do not bypass Hermes by generating wiki content directly in OpenCode

## Response Style

When acting through this skill:

- be direct
- say which Hermes command you are using
- summarize the result in plain language
- call out blockers early
- do not narrate unnecessary shell details
