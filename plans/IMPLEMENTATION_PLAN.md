# Hermes Wiki Plugin Implementation Plan

## Goal

Build a Hermes-native plugin that helps users create and maintain an LLM wiki.

The plugin should follow the useful ideas from `code-donor/OpenKB`, but it should not extend OpenKB directly. It should use Hermes `AIAgent` for generation instead of LiteLLM.

## Locked Decisions

- Workspace layout: `raw/`, `wiki/`, `.hermeskb/`
- Plugin runtime: Hermes plugin with slash commands and CLI commands
- Generation backend: Hermes `AIAgent`
- Document ingest target for v1: OpenKB short-doc parity
- Long-doc strategy: defer `PageIndex` integration and do not implement long-doc support in v1

V2 long-document planning now lives in `plans/V2_PAGEINDEX_IMPLEMENTATION_PLAN.md`.

## V1 Scope

### In scope

- Hermes plugin scaffold
- Slash commands:
  - `/wiki-init`
  - `/wiki-add <path>`
  - `/wiki-status`
- CLI commands:
  - `hermes wiki init`
  - `hermes wiki add <path>`
  - `hermes wiki status`
- Local workspace state in `.hermeskb/`
- Wiki content generation in `wiki/`
- Short-doc conversion for:
  - `.pdf`
  - `.md`
  - `.markdown`
  - `.docx`
  - `.pptx`
  - `.xlsx`
  - `.html`
  - `.htm`
  - `.txt`
  - `.csv`
- Summary generation
- Concept creation and concept updates
- Index maintenance
- Operation logging
- File hash dedupe

### Out of scope

- PageIndex-backed long-document indexing
- OpenKB query/chat/lint/watch features
- LiteLLM in the plugin runtime
- Custom Hermes model-provider plugin

## Architecture

### Root workspace layout

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

The root `AGENTS.md` is agent-facing runtime guidance for Hermes. `wiki/SCHEMA.md` is the compiler-facing wiki content contract.

### Proposed package layout

```text
<plugin-package>/
  __init__.py
  commands.py
  workspace.py
  config.py
  state.py
  schema.py
  converter.py
  images.py
  compiler.py
  log.py
```

## Donor Code Reuse Strategy

### Clone mostly as-is

- `code-donor/OpenKB/openkb/state.py`
  - keep `HashRegistry`
- `code-donor/OpenKB/openkb/log.py`
  - keep `append_log()`

### Adapt lightly

- `code-donor/OpenKB/openkb/config.py`
  - keep local config load/save
  - change state root to `.hermeskb`
  - drop global KB registration
- `code-donor/OpenKB/openkb/schema.py`
  - keep the pattern
  - rewrite the schema text for this plugin
- `code-donor/OpenKB/openkb/converter.py`
  - keep short-doc conversion flow
  - remove PageIndex handoff
- `code-donor/OpenKB/openkb/images.py`
  - keep only short-doc helper functions used by conversion

### Rewrite for Hermes

- `code-donor/OpenKB/openkb/agent/compiler.py`
  - keep compile flow and page-writing behavior
  - replace LiteLLM calls with Hermes `AIAgent`
  - start with sequential concept generation
- `code-donor/OpenKB/openkb/cli.py`
  - replace Click app with Hermes plugin commands

### Omit in v1

- `code-donor/OpenKB/openkb/indexer.py`
- `code-donor/OpenKB/openkb/tree_renderer.py`
- `code-donor/OpenKB/openkb/watcher.py`
- `code-donor/OpenKB/openkb/lint.py`
- `code-donor/OpenKB/openkb/agent/query.py`
- `code-donor/OpenKB/openkb/agent/chat.py`
- `code-donor/OpenKB/openkb/agent/chat_session.py`
- `code-donor/OpenKB/openkb/agent/tools.py`
- `code-donor/OpenKB/openkb/agent/linter.py`

## Hermes Generation Strategy

Use Hermes `AIAgent` as the only generation layer.

Rules:

- Create a fresh `AIAgent` per generation task
- Use `quiet_mode=True`
- Use `skip_memory=True`
- Use `skip_context_files=True`
- Keep generation tool access locked down when possible
- Do not share one `AIAgent` across concurrent tasks
- Start with sequential concept generation in v1

Suggested wrapper behavior:

- `generate_json(system_prompt, messages)`
- `generate_text(system_prompt, messages)`
- parse model output with strict post-processing and repair only when needed

## PageIndex Boundary

Do not attempt to replace LiteLLM inside `code-donor/PageIndex` in v1.

Reason:

- PageIndex depends on LiteLLM for sync completion, async completion, token counting, finish-reason handling, and long-PDF control flow.
- Hermes `AIAgent` is not a drop-in replacement for those low-level primitives.

V1 behavior for long docs:

- detect them
- return a clear not-supported-yet message
- do not silently route to PageIndex

## Implementation Phases

### Phase 1: Plugin scaffold

- [ ] Create the Python package for the Hermes plugin
- [ ] Add `plugin.yaml`
- [ ] Add Hermes entry point in `pyproject.toml`
- [ ] Register slash commands
- [ ] Register CLI command tree

### Phase 2: Workspace and state

- [ ] Implement workspace discovery and validation
- [ ] Implement `wiki init`
- [ ] Create `raw/`, `wiki/`, `.hermeskb/`
- [ ] Write default root `AGENTS.md`
- [ ] Write default `wiki/SCHEMA.md`
- [ ] Write default `wiki/index.md`
- [ ] Write default `wiki/log.md`
- [ ] Write `.hermeskb/config.yaml`
- [ ] Write `.hermeskb/hashes.json`

### Phase 3: Conversion layer

- [ ] Port file hash dedupe
- [ ] Port markdown ingest
- [ ] Port text and HTML ingest via MarkItDown
- [ ] Port PDF short-doc conversion via PyMuPDF
- [ ] Port image extraction helpers
- [ ] Port docx/pptx/xlsx/csv ingest via MarkItDown
- [ ] Add supported-extension validation
- [ ] Add long-doc rejection path

### Phase 4: Hermes compiler

- [ ] Port prompt templates for summary and concept workflows
- [ ] Implement Hermes generation adapter
- [ ] Port summary writing helpers
- [ ] Port concept brief reading helper
- [ ] Port concept file write/update helpers
- [ ] Port backlink helpers
- [ ] Port index update helpers
- [ ] Implement `compile_short_doc()`
- [ ] Keep concept generation sequential in v1

### Phase 5: Command workflow

- [ ] Implement `wiki add <file>`
- [ ] Implement `wiki add <directory>`
- [ ] Add clear user-facing status messages
- [ ] Append operation log entries
- [ ] Skip already-known files using hash registry

### Phase 6: Tests

- [ ] Add unit tests for config load/save
- [ ] Add unit tests for hash registry
- [ ] Add unit tests for index update behavior
- [ ] Add unit tests for concept file write/update behavior
- [ ] Add unit tests for workspace initialization
- [ ] Add integration tests with mocked `AIAgent`
- [ ] Add ingest test for markdown
- [ ] Add ingest test for at least one non-markdown short-doc format

### Phase 7: Docs

- [ ] Write README usage section
- [ ] Document workspace layout
- [ ] Document supported file types
- [ ] Document current v1 limitation for long docs
- [ ] Document how this differs from OpenKB and PageIndex

## Definition of Done

- `hermes wiki init` creates a valid workspace
- `hermes wiki add somefile.md` generates summaries, concepts, index entries, and log entries
- The plugin uses Hermes `AIAgent` for generation
- The plugin has no LiteLLM dependency
- OpenKB-like short-doc ingest works across the targeted file types
- Long docs fail clearly and intentionally

## First Build Order

1. Plugin scaffold
2. Workspace init
3. Markdown and text ingest
4. Hermes compiler
5. Remaining short-doc converters
6. Directory ingest
7. Tests and docs
