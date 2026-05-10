# Hermes Wiki

Hermes Wiki is a Hermes-native plugin for building and maintaining an LLM wiki from source documents.

The project follows the useful workflow and content model from `OpenKB`, but it is being rebuilt as a Hermes plugin that uses Hermes `AIAgent` for generation instead of LiteLLM.

## Status

This repository is in early development.

Current scaffold includes:

- Hermes plugin packaging and registration
- `wiki init`, `wiki add`, and `wiki status` command surfaces
- Workspace initialization for `raw/`, `wiki/`, and `.hermeskb/`
- Short-document conversion pipeline for markdown, text, csv, pdf, and MarkItDown-backed formats
- Hermes `AIAgent`-based summary/concept compiler structure
- Test coverage for workspace commands, conversion paths, compiler writes, and runtime integration

Current v1 boundary:

- short-document workflows only
- no PageIndex-backed long-document support yet

## Workspace Layout

The plugin manages this layout inside a user workspace:

```text
raw/
wiki/
  AGENTS.md
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

## Repo Layout

- `hermes_wiki/` - Hermes plugin implementation
- `code-donor/OpenKB/` - donor reference for short-doc wiki workflow
- `code-donor/PageIndex/` - donor reference for future long-doc support
- `AGENTS.md` - repo guidance and implementation rules
- `IMPLEMENTATION_PLAN.md` - phased execution plan and checklist

## Donor Strategy

This repo does not extend OpenKB directly.

- `OpenKB` is used as a donor reference for workspace structure, conversion flow, and wiki compilation behavior.
- `PageIndex` is kept as a donor reference only and is intentionally out of the v1 runtime.

The donor repositories are tracked as Git submodules so they stay clearly separated from the Hermes-native implementation.

## Planned Commands

- `hermes wiki init`
- `hermes wiki add <path>`
- `hermes wiki status`
- `/wiki-init`
- `/wiki-add <path>`
- `/wiki-status`

## Installation

### Plugin development install

From this repo:

```bash
pip install -e .
```

Hermes should discover the plugin through the `hermes_agent.plugins` entry point.

### Runtime requirements

- Hermes runtime providing `run_agent.AIAgent`
- `pymupdf` for PDF ingest
- `markitdown[all]` for `.docx`, `.pptx`, `.xlsx`, `.html`, and related formats

If Hermes is not importable at runtime, generation commands will fail with a clear error.

## Usage

Inside Hermes:

```text
/wiki-init .
/wiki-add notes/
/wiki-status
```

From Hermes CLI subcommands:

```bash
hermes wiki init .
hermes wiki add ./docs
hermes wiki status
```

## Development

Run tests locally with the repo virtualenv:

```bash
python3 -m venv .venv
.venv/bin/pip install pytest
.venv/bin/pytest
```

## Development Notes

- New runtime code should live in `hermes_wiki/`
- Do not build on LiteLLM for plugin generation paths
- Do not route long documents through PageIndex in v1

See `AGENTS.md` and `IMPLEMENTATION_PLAN.md` for the current working rules and roadmap.
