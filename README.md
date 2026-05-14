# Hermes Wiki

Hermes Wiki is a Hermes-native plugin for building and maintaining an LLM wiki from source documents.

The project follows the useful workflow and content model from `OpenKB`, but it is being rebuilt as a Hermes plugin that uses Hermes `AIAgent` for generation instead of LiteLLM.

## Status

The plugin supports short-document wiki ingest and PageIndex-backed long-PDF ingest.

Current capabilities include:

- Hermes plugin packaging and registration
- Hermes plugin tools for workspace init, ingest, status, config, and listing
- `wiki init`, `wiki add`, and `wiki status` command surfaces
- Workspace initialization for `raw/`, `wiki/`, and `.hermeskb/`
- Short-document conversion pipeline for markdown, text, csv, pdf, and MarkItDown-backed formats
- PageIndex-backed long-PDF ingest above `long_doc_threshold`
- Guarded long-document retrieval tools for document structure and selected page ranges
- Hermes `AIAgent`-based summary/concept compiler with opt-in bounded concurrent concept generation
- Test coverage for workspace commands, conversion paths, compiler writes, and runtime integration

Current boundary:

- long PDFs are supported through PageIndex
- long Markdown and MarkItDown-backed long documents are still deferred
- retrieval is through Hermes wiki tools, not a separate PageIndex chat surface

See `plans/V2_PAGEINDEX_IMPLEMENTATION_PLAN.md` for the PageIndex implementation plan.
See `plans/AIAGENT_CONCURRENT_CONCEPT_GENERATION_PLAN.md` for the concurrent concept generation design.

## Workspace Layout

The plugin manages this layout inside a user workspace:

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

The root `AGENTS.md` guides Hermes agents when answering questions from the wiki. `wiki/SCHEMA.md` defines the wiki content contract used by compiler prompts.

## Repo Layout

- `hermes_wiki/` - Hermes plugin directory and implementation source of truth
- `code-donor/OpenKB/` - donor reference for short-doc wiki workflow
- `code-donor/PageIndex/` - donor reference for future long-doc support
- `AGENTS.md` - repo guidance and implementation rules
- `plans/` - implementation and patch plans, including `IMPLEMENTATION_PLAN.md` and compiler concurrency plans

## Donor Strategy

This repo does not extend OpenKB directly.

- `OpenKB` is used as a donor reference for workspace structure, conversion flow, and wiki compilation behavior.
- `PageIndex` is kept as a donor reference only; the runtime implementation is repo-owned.
- Repo-owned PageIndex runtime code lives under `hermes_wiki/pageindex/`.

The donor repositories are tracked as Git submodules so they stay clearly separated from the Hermes-native implementation.

## Planned Commands

- `hermes wiki init`
- `hermes wiki add <path>`
- `hermes wiki status`
- `hermes wiki list`
- `hermes wiki config`
- `/wiki-init`
- `/wiki-add <path>`
- `/wiki-status`
- `/wiki-list`
- `/wiki-config`

## Installation

### Pip install from GitHub

For a Hermes runtime that supports Python entry-point plugins, install `hermes-wiki` into the same Python environment that runs Hermes:

```bash
uv pip install --python <hermes-runtime-python> git+https://github.com/zombiearnie88/hermes-wiki.git
hermes plugins enable hermes-wiki
```

For the repo-local Docker runtime paths this means:

```bash
uv pip install --python /opt/hermes/.venv/bin/python git+https://github.com/zombiearnie88/hermes-wiki.git
uv pip install --python /app/venv/bin/python3 git+https://github.com/zombiearnie88/hermes-wiki.git
```

Pip installation uses the `hermes_agent.plugins` entry point declared in `pyproject.toml`. It does not copy files into `~/.hermes/plugins/hermes-wiki/`; that directory is only for directory-plugin installs.

For the detailed publishing workflow, see `plans/PIP_PUBLISHING_PLAN.md`.

### Plugin development install

From this repo:

```bash
pip install -e .
hermes plugins enable hermes-wiki
```

If Hermes is loading the plugin from a mounted `hermes_wiki/` directory instead of the pip-installed package, bootstrap the runtime dependencies into the Hermes interpreter explicitly with `uv pip --python`:

```bash
uv pip install --python <hermes-runtime-python> json-repair pymupdf 'markitdown[all]'
```

For the repo-local Docker stack, `hermes-clinic` and `hermes-webui` use different Python interpreters. Install into the interpreter that imports the plugin.

For `hermes-clinic`:

```bash
docker compose exec -T hermes-clinic uv pip install --python /opt/hermes/.venv/bin/python -r /opt/data/profiles/clinic/plugins/hermes-wiki/requirements.txt
```

For `hermes-webui`:

```bash
docker compose exec -T hermes-webui uv pip install --python /app/venv/bin/python3 -r /home/hermeswebui/.hermes/plugins/hermes-wiki/requirements.txt
```

The repo-local Docker stack bootstraps `hermes-clinic` directly at startup. It bootstraps WebUI through the one-shot `hermes-webui-plugin-deps` service, which installs `hermes_wiki/requirements.txt` into the shared `/app/venv` volume before `hermes-webui` starts.

If you cloned this repo fresh, initialize donor references too:

```bash
git submodule update --init --recursive
```

Hermes discovers the plugin through the `hermes_agent.plugins` entry point, but general plugins are opt-in, so `hermes plugins enable hermes-wiki` is still required before the plugin loads.

For directory-plugin workflows, `hermes_wiki/` is the self-contained plugin directory. It contains the registration module, schemas, handlers, bundled skills, and `plugin.yaml`.

For local development outside Hermes, the package also exposes a small standalone CLI:

```bash
hermes-wiki init .
hermes-wiki config --workspace . --model gpt-5.4-mini --provider openai-codex --language en
hermes-wiki add ./docs --workspace .
hermes-wiki status --workspace .
```

### Runtime requirements

- Hermes runtime providing `run_agent.AIAgent`
- `json-repair` for robust compiler JSON parsing
- `pymupdf` for PDF ingest
- `markitdown[all]` for `.docx`, `.pptx`, `.xlsx`, `.html`, and related formats

Install these into the same Python interpreter Hermes uses to import the plugin. In the local container workflow, prefer `uv pip --python <runtime-python> ...` so the runtime environment and the shell environment do not drift apart. The clinic runtime is typically `/opt/hermes/.venv/bin/python`; the WebUI runtime is typically `/app/venv/bin/python3`.

If Hermes is not importable at runtime, generation commands will fail with a clear error.

## Usage

Inside Hermes:

```text
/wiki-init .
/wiki-add notes/
/wiki-status
```

When the plugin is enabled, Hermes also sees these tools:

- `wiki_init`
- `wiki_add`
- `wiki_status`
- `wiki_config`
- `wiki_list`
- `wiki_deps`
- `get_document_structure`
- `get_page_content`

From Hermes CLI subcommands:

```bash
hermes wiki init .
hermes wiki config --model gpt-5.4-mini --provider openai-codex --language en
hermes wiki add ./docs
hermes wiki status
hermes wiki list
hermes wiki config --model anthropic/claude-opus-4-6 --provider anthropic --language fr
hermes wiki deps --install all
```

From the standalone dev CLI:

```bash
hermes-wiki init .
hermes-wiki config --workspace . --model gpt-5.4-mini --provider openai-codex --language en
hermes-wiki add ./docs --workspace .
hermes-wiki status --workspace .
hermes-wiki list --workspace .
hermes-wiki config --workspace . --model anthropic/claude-opus-4-6 --provider anthropic --language fr
hermes-wiki deps --install all
```

`wiki add` uses the persisted `model` and `provider` from `.hermeskb/config.yaml` by default.
It also accepts one-off `--model`, `--provider`, and `--language` overrides without rewriting workspace config.
`wiki config` updates the persisted workspace configuration in `.hermeskb/config.yaml`.
`concept_generation_concurrency` defaults to `3` for bounded concurrent concept page generation. Values are clamped to `1..8`; set it to `1` to force serial concept generation.

For the repo-local Docker ChatGPT/Codex setup, configure generation with unprefixed Codex model IDs:

```yaml
model: gpt-5.4-mini
provider: openai-codex
language: en
long_doc_threshold: 20
concept_generation_concurrency: 3
pageindex_toc_check_pages: 20
pageindex_max_pages_per_node: 10
pageindex_max_tokens_per_node: 20000
pageindex_summary_token_threshold: 200
pageindex_max_pages_per_tool_call: 8
```

Do not use `openai/gpt-*` model IDs with `provider: openai-codex`; the Codex ChatGPT backend expects model IDs such as `gpt-5.4-mini`, `gpt-5.5`, or `gpt-5.5-mini`.

`wiki status` reports both capability readiness and the underlying dependency health for the current environment.

If `wiki status` shows missing `json-repair`, `PyMuPDF`, or `MarkItDown`, use `wiki_deps` or repair the Hermes runtime first and then retry ingest. Avoid assuming `python3 -m pip install ...` touched the same interpreter Hermes is running.

### Long PDFs

PDFs with page counts greater than or equal to `long_doc_threshold` are copied to `raw/` and compiled through PageIndex. The wiki summary uses `doc_type: pageindex`, stores compact structure under `wiki/summaries/`, and writes PageIndex state to `.hermeskb/pageindex/{doc_name}/`:

```text
index.json
pages.jsonl
audit.json
```

Use `get_document_structure` first to inspect the tree, then `get_page_content` with a narrow selector such as `"5"`, `"5-7"`, or `"3,8"`. `get_page_content` rejects out-of-range and too-large requests; it never returns a whole long document by convenience mode.

## Bundled Skill

The plugin bundles a read-only skill for operating the wiki plugin:

```python
skill_view("hermes-wiki:wiki-operator")
```

Plugin skills are explicit-load only. They do not appear in Hermes' normal available-skills index, so the fully qualified plugin name is required.

Supported ingest types:

- Native paths: `.md`, `.markdown`, `.txt`, `.csv`, `.pdf`
- MarkItDown-backed: `.docx`, `.pptx`, `.xlsx`, `.html`, `.htm`
- Long PDFs: PageIndex-backed when they meet or exceed `long_doc_threshold`

## Development

Run tests locally with the repo virtualenv:

```bash
python3 -m venv .venv
.venv/bin/pip install pytest
.venv/bin/pytest
```

### Docker Smoke Test

For Docker examples that install the plugin from GitHub with pip, including fresh local smoke tests and production-style VPS/Mac mini deployments, see `examples/README.md`.

After the Docker stack is running, you can verify the plugin mount and discovery wiring with:

```bash
./docker/smoke-test-plugin.sh
```

The script verifies real `PluginManager.discover_and_load()` state in both `hermes-clinic` and `hermes-webui`, and checks WebUI imports against `/app/venv/bin/python3`.

A plugin can be enabled in `config.yaml` but disabled at runtime if import fails. For example, `plugins.enabled: [hermes-wiki]` with `plugins.disabled: []` can still produce `PluginManager` state `enabled=False` when the loader records an error such as `No module named 'hermes_wiki'`. In that case, inspect runtime plugin state rather than relying only on `hermes plugins list`.

The repo-local clinic startup and WebUI dependency bootstrap service install the wiki plugin dependencies, and the smoke test verifies those imports in `/opt/hermes/.venv/bin/python` and `/app/venv/bin/python3`.

### Docker Development Reloads

The repo-local Docker stack bind-mounts `hermes_wiki/` into both `hermes-clinic` and `hermes-webui`, so source edits are visible inside running containers immediately.

Restart behavior depends on what is being tested:

- For one-off `docker compose exec hermes-clinic ... hermes ...` commands, Python source changes usually do not need a restart because each command starts a fresh Python process.
- For the running WebUI, restart `hermes-webui` after Python, plugin registration, schema, or bundled skill changes so loaded modules and plugin metadata refresh.
- For `hermes_wiki/requirements.txt` changes, reinstall dependencies into the affected runtime with `uv pip --python`. Use `/opt/hermes/.venv/bin/python` for `hermes-clinic` and `/app/venv/bin/python3` for `hermes-webui`.
- For `docker/docker-compose.yml`, volume, image, or environment changes, recreate the affected containers with `docker compose up -d --force-recreate`.

From `docker/`, restart the WebUI with:

```bash
docker compose restart hermes-webui
```

## Development Notes

- New runtime code should live in `hermes_wiki/`
- `hermes_wiki/` is also the directory-plugin source mounted by the local Docker setup
- Do not build on LiteLLM for plugin generation paths
- Long PDFs route through PageIndex; long non-PDF documents are still deferred

See `AGENTS.md`, `plans/IMPLEMENTATION_PLAN.md`, and `plans/V2_PAGEINDEX_IMPLEMENTATION_PLAN.md` for the current working rules and roadmap.
