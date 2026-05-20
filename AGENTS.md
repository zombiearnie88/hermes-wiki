# Hermes Wiki Repo Guide

## Purpose

This repo builds a Hermes plugin that helps users create and maintain an LLM wiki.

The product direction is to clone the useful workflow from `code-donor/OpenKB`, but to implement it as a Hermes-native plugin that uses Hermes plugin LLM access (`ctx.llm`) for generation.

## Source of Truth

- `code-donor/OpenKB/` is a reference donor, not the runtime target
- `code-donor/PageIndex/` is a reference donor; runtime PageIndex code is repo-owned under `hermes_wiki/pageindex/`
- New implementation work should live in new repo-owned plugin code, not inside donor folders
- V2 PageIndex planning lives in `plans/V2_PAGEINDEX_IMPLEMENTATION_PLAN.md`

## Core Decisions

- Use Hermes plugin commands, not an OpenKB standalone CLI
- Use Hermes plugin `ctx.llm`, not direct `run_agent.AIAgent` or LiteLLM
- Use workspace layout:
  - `AGENTS.md`
  - `raw/`
  - `wiki/`
  - `.hermeskb/`
- Target OpenKB short-doc parity plus repo-owned long-PDF PageIndex support
- Defer unsupported long non-PDF workflows

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
- PageIndex-backed long-PDF ingest

### Do not build in v1

- OpenKB query/chat/lint/watch surfaces
- LiteLLM-based generation paths
- custom Hermes model-provider plugin
- long non-PDF PageIndex workflows

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
  pageindex/
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

- call `ctx.llm.acomplete()` through the runtime adapter
- pass workspace `.hermeskb/config.yaml` `model` and `provider` explicitly to `ctx.llm`
- keep generation deterministic where possible with `temperature=0.0`
- use bounded async fan-out for concept generation
- keep concept file writes, backlinks, related links, and index updates serial after concurrent generation finishes
- do not add a fallback to direct `run_agent.AIAgent` or LiteLLM

Rationale:

- the wiki compiler needs controlled prompts and predictable outputs
- ambient Hermes context files should not leak into wiki-compilation prompts
- plugin LLM trust gates must allow explicit provider/model routing for workspace config values

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

Long PDFs route through the repo-owned PageIndex pipeline when they meet the configured threshold.

Expected behavior:

- detect supported long PDFs and compile PageIndex summaries through `ctx.llm`
- keep PageIndex state under `.hermeskb/pageindex/`
- return a clear not-supported-yet message for unsupported long non-PDF workflows
- leave unsupported files uncompiled rather than routing through LiteLLM

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
- avoid adding compatibility layers for LiteLLM or direct `run_agent.AIAgent`
- fail clearly on unsupported long-doc workflows in v1
- add tests around file writes, index updates, and generated-JSON parsing

## Docker Runtime Reload

- When plugin Python code, schemas, slash commands, or bundled skills change, recreate Hermes Docker containers when possible so runtime imports and skill registrations are refreshed.
- Prefer `docker compose -f docker/docker-compose.yml up -d --force-recreate hermes-agent hermes-webui` for this repo's local Docker setup.
- Existing wiki workspaces keep their current `AGENTS.md` and `wiki/SCHEMA.md`; recreate/restart only reloads plugin runtime code and bundled skill files.

## Success Criteria

- the repo contains a real Hermes plugin, not just a donor fork
- the plugin can initialize a wiki workspace
- the plugin can ingest short docs and compile summaries and concepts
- the plugin has no LiteLLM dependency in its generation path
- v1 boundaries are explicit and enforced
