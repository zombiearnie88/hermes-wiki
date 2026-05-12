# Hermes Wiki Repo Guide

## Purpose

This repo builds a Hermes plugin that helps users create and maintain an LLM wiki.

The product direction is to clone the useful workflow from `code-donor/OpenKB`, but to implement it as a Hermes-native plugin that uses Hermes `AIAgent` for generation.

## Source of Truth

- `code-donor/OpenKB/` is a reference donor, not the runtime target
- `code-donor/PageIndex/` is a reference donor for v2 long-doc work, not a v1 dependency
- New implementation work should live in new repo-owned plugin code, not inside donor folders
- V2 PageIndex planning lives in `plans/V2_PAGEINDEX_IMPLEMENTATION_PLAN.md`

## Core Decisions

- Use Hermes plugin commands, not an OpenKB standalone CLI
- Use Hermes `AIAgent`, not LiteLLM
- Use workspace layout:
  - `AGENTS.md`
  - `raw/`
  - `wiki/`
  - `.hermeskb/`
- Target OpenKB short-doc parity for v1
- Defer long-doc `PageIndex` support to v2

## V1 Scope

### Build

- Hermes plugin scaffold
- `wiki init`
- `wiki add <file-or-dir>`
- `wiki status`
- short-doc conversion
- summary generation
- concept creation and concept updates
- wiki index maintenance
- append-only operation log
- file hash dedupe

### Do not build in v1

- PageIndex long-document indexing
- OpenKB query/chat/lint/watch surfaces
- LiteLLM-based generation paths
- custom Hermes model-provider plugin

## Workspace Layout

The plugin should manage this layout:

```text
AGENTS.md
raw/
wiki/
  SCHEMA.md
  index.md
  log.md
  sources/
  summaries/
  concepts/
  explorations/
  reports/
.hermeskb/
  config.yaml
  hashes.json
```

Root `AGENTS.md` is agent-facing runtime guidance for Hermes. `wiki/SCHEMA.md` is the compiler-facing wiki content contract.

## Reuse Rules

### Safe to port nearly verbatim

- `code-donor/OpenKB/openkb/state.py`
- `code-donor/OpenKB/openkb/log.py`

### Safe to port with light adaptation

- `code-donor/OpenKB/openkb/config.py`
- `code-donor/OpenKB/openkb/schema.py`
- `code-donor/OpenKB/openkb/converter.py`
- `code-donor/OpenKB/openkb/images.py`

### Must be rewritten for Hermes

- `code-donor/OpenKB/openkb/agent/compiler.py`
- `code-donor/OpenKB/openkb/cli.py`

### Must stay out of the new runtime for now

- everything under `code-donor/PageIndex/`
- OpenKB query/chat/lint/watch code

## Hermes Generation Rules

When generating summaries or concepts:

- instantiate a fresh `AIAgent` per generation task
- set `quiet_mode=True`
- set `skip_memory=True`
- set `skip_context_files=True`
- keep generation deterministic where possible
- do not share one `AIAgent` across concurrent tasks
- start with sequential concept generation in v1

Rationale:

- the wiki compiler needs controlled prompts and predictable outputs
- ambient Hermes context files should not leak into wiki-compilation prompts

## Prompt and Content Rules

- keep root `AGENTS.md` as the Hermes agent instruction file
- keep `wiki/SCHEMA.md` as the wiki content/schema file
- read `wiki/SCHEMA.md` from disk at compile time
- do not introduce `wiki/AGENTS.md`
- preserve OpenKB-style page types:
  - summary pages
  - concept pages
  - index page
  - log page
- use `[[wikilinks]]`
- code manages frontmatter; model output should not

## Long-Doc Boundary

If a file crosses the long-doc threshold, do not attempt partial PageIndex integration in v1.

Expected behavior:

- detect the long document
- return a clear not-supported-yet message
- leave the file uncompiled rather than routing through LiteLLM

## Implementation Priorities

Build in this order:

1. plugin scaffold
2. workspace initialization
3. markdown and text ingest
4. Hermes summary/concept compiler
5. remaining short-doc converters
6. directory ingest
7. tests and docs

## Coding Guidance

- prefer small, direct ports over broad abstraction
- keep donor-derived behavior intact unless there is a clear Hermes reason to change it
- isolate donor references from new runtime code
- avoid adding compatibility layers for LiteLLM
- fail clearly on unsupported long-doc workflows in v1
- add tests around file writes, index updates, and generated-JSON parsing

## Success Criteria

- the repo contains a real Hermes plugin, not just a donor fork
- the plugin can initialize a wiki workspace
- the plugin can ingest short docs and compile summaries and concepts
- the plugin has no LiteLLM dependency in its generation path
- v1 boundaries are explicit and enforced
