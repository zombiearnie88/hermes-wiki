# Hermes Wiki

Hermes Wiki is a Hermes-native plugin for building and maintaining an LLM wiki from source documents.

The project follows the useful workflow and content model from `OpenKB`, but it is being rebuilt as a Hermes plugin that uses Hermes `AIAgent` for generation instead of LiteLLM.

## Status

This repository is in early development.

Current scaffold includes:

- Hermes plugin packaging and registration
- Hermes plugin tools for workspace init, ingest, status, config, and listing
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

- `hermes_wiki/` - Hermes plugin directory and implementation source of truth
- `code-donor/OpenKB/` - donor reference for short-doc wiki workflow
- `code-donor/PageIndex/` - donor reference for future long-doc support
- `AGENTS.md` - repo guidance and implementation rules
- `plans/` - implementation and patch plans, including `IMPLEMENTATION_PLAN.md`

## Donor Strategy

This repo does not extend OpenKB directly.

- `OpenKB` is used as a donor reference for workspace structure, conversion flow, and wiki compilation behavior.
- `PageIndex` is kept as a donor reference only and is intentionally out of the v1 runtime.

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

### Plugin development install

From this repo:

```bash
pip install -e .
hermes plugins enable hermes-wiki
```

If Hermes is loading the plugin from a mounted `hermes_wiki/` directory instead of the pip-installed package, bootstrap the runtime dependencies into the Hermes interpreter explicitly:

```bash
uv pip install --python /opt/hermes/.venv/bin/python json-repair pymupdf 'markitdown[all]'
```

For the repo-local Docker stack, run that inside `hermes-clinic`:

```bash
docker compose exec -T hermes-clinic uv pip install --python /opt/hermes/.venv/bin/python json-repair pymupdf 'markitdown[all]'
```

The repo-local `hermes-clinic` container now runs this bootstrap automatically from `hermes_wiki/requirements.txt` before enabling the plugin.

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

Install these into the same Python interpreter Hermes uses to import the plugin. In the local container workflow, prefer `uv pip --python /opt/hermes/.venv/bin/python ...` so the runtime environment and the shell environment do not drift apart.

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

For the repo-local Docker ChatGPT/Codex setup, configure generation with unprefixed Codex model IDs:

```yaml
model: gpt-5.4-mini
provider: openai-codex
language: en
long_doc_threshold: 20
```

Do not use `openai/gpt-*` model IDs with `provider: openai-codex`; the Codex ChatGPT backend expects model IDs such as `gpt-5.4-mini`, `gpt-5.5`, or `gpt-5.5-mini`.

`wiki status` reports both capability readiness and the underlying dependency health for the current environment.

If `wiki status` shows missing `json-repair`, `PyMuPDF`, or `MarkItDown`, use `wiki_deps` or repair the Hermes runtime first and then retry ingest. Avoid assuming `python3 -m pip install ...` touched the same interpreter Hermes is running.

## Bundled Skill

The plugin bundles a read-only skill for operating the wiki plugin:

```python
skill_view("hermes-wiki:wiki-operator")
```

Plugin skills are explicit-load only. They do not appear in Hermes' normal available-skills index, so the fully qualified plugin name is required.

Supported v1 ingest types:

- Native paths: `.md`, `.markdown`, `.txt`, `.csv`, `.pdf`
- MarkItDown-backed: `.docx`, `.pptx`, `.xlsx`, `.html`, `.htm`

## Development

Run tests locally with the repo virtualenv:

```bash
python3 -m venv .venv
.venv/bin/pip install pytest
.venv/bin/pytest
```

### Docker Smoke Test

After the Docker stack is running, you can verify the plugin mount and discovery wiring with:

```bash
./docker/smoke-test-plugin.sh
```

The script verifies real plugin discovery in `hermes-clinic` and checks the mounted plugin payload in `hermes-webui`. If the WebUI image does not include the Hermes CLI Python dependencies, it falls back to mount and container-health checks there.

The repo-local clinic startup now bootstraps the wiki plugin dependencies before enabling the plugin, and the smoke test verifies those imports in `/opt/hermes/.venv/bin/python`.

### Docker Development Reloads

The repo-local Docker stack bind-mounts `hermes_wiki/` into both `hermes-clinic` and `hermes-webui`, so source edits are visible inside running containers immediately.

Restart behavior depends on what is being tested:

- For one-off `docker compose exec hermes-clinic ... hermes ...` commands, Python source changes usually do not need a restart because each command starts a fresh Python process.
- For the running WebUI, restart `hermes-webui` after Python, plugin registration, schema, or bundled skill changes so loaded modules and plugin metadata refresh.
- For `hermes_wiki/requirements.txt` changes, restart `hermes-clinic` or rerun the startup install command manually: `uv pip install --python /opt/hermes/.venv/bin/python -r /opt/data/profiles/clinic/plugins/hermes-wiki/requirements.txt`.
- For `docker/docker-compose.yml`, volume, image, or environment changes, recreate the affected containers with `docker compose up -d --force-recreate`.

From `docker/`, restart the WebUI with:

```bash
docker compose restart hermes-webui
```

## Development Notes

- New runtime code should live in `hermes_wiki/`
- `hermes_wiki/` is also the directory-plugin source mounted by the local Docker setup
- Do not build on LiteLLM for plugin generation paths
- Do not route long documents through PageIndex in v1

See `AGENTS.md` and `plans/IMPLEMENTATION_PLAN.md` for the current working rules and roadmap.
