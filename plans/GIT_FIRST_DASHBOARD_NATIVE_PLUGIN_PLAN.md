# Git-First Dashboard-Native Plugin Plan

## Goal

Make `hermes-wiki` install cleanly through Hermes Agent dashboard and `hermes plugins install` from the GitHub repository URL, without manual directory repair or pip/archive install steps.

Primary install target:

```bash
hermes plugins install --enable https://github.com/zombiearnie88/hermes-wiki.git
```

The repo root should be a valid Hermes directory plugin.

## Current Problem

`hermes plugins install` clones the Git repository root into `$HERMES_HOME/plugins/hermes-wiki`.

Hermes directory-plugin discovery expects the plugin directory to contain:

```text
plugin.yaml
__init__.py
```

The current valid plugin directory is `hermes_wiki/`, not the repository root. As a result, Git/dashboard install clones the repo but Hermes warns that the installed directory is not a valid plugin until `hermes_wiki/` is manually copied or moved into the plugin directory.

## Direction

Use a Git-first directory-plugin layout.

Do not rename `hermes_wiki/` to `scripts/`. The `hermes_wiki` package contains runtime implementation code, not just scripts, and the name is specific enough to avoid generic top-level module conflicts.

Keep `hermes_wiki/` as the internal implementation package. Make the repo root the Hermes plugin wrapper.

## Target Layout

```text
plugin.yaml
__init__.py
after-install.md
requirements.txt
pyproject.toml
hermes_wiki/
  __init__.py
  commands.py
  tools.py
  schemas.py
  compiler.py
  workspace.py
  deps.py
  skills/
    wiki-operator/
      SKILL.md
```

`plugin.yaml` and `__init__.py` at repo root make Git/dashboard install native.

`hermes_wiki/` remains the implementation package imported by the root wrapper.

## Root Plugin Wrapper

Add repo-root `__init__.py`:

```python
from __future__ import annotations

from .hermes_wiki import register

__all__ = ["register"]
```

This lets Hermes load the cloned repo root as a directory plugin while keeping the existing implementation under `hermes_wiki/`.

## Plugin Manifest

Move the plugin manifest to repo root as `plugin.yaml`:

```yaml
name: hermes-wiki
version: 0.1.1
description: Hermes plugin for building and maintaining an LLM wiki
author: Thach Duong
provides_tools:
  - wiki_init
  - wiki_add
  - wiki_status
  - wiki_config
  - wiki_list
  - wiki_deps
  - get_document_structure
  - get_page_content
```

Remove `hermes_wiki/plugin.yaml` once local Docker and tests no longer depend on mounting `hermes_wiki/` directly as the plugin root.

## Dependencies

Move `hermes_wiki/requirements.txt` to repo-root `requirements.txt`.

Required runtime packages remain:

```text
json-repair
pymupdf
markitdown[all]
```

Do not rely on pip package install as the primary deployment path.

Keep `wiki deps --install all` as the supported runtime dependency repair command.

Add `after-install.md` at repo root to guide dashboard users:

````markdown
# Hermes Wiki Installed

Run dependency setup in the Hermes runtime:

```bash
hermes wiki deps --install all
hermes gateway restart
```

For Docker deployments with separate Agent and WebUI Python environments, run dependency setup in both runtimes if WebUI imports the plugin directly.
````

## Versioning

Bump plugin version to `0.1.1`.

Update version references in:

```text
plugin.yaml
pyproject.toml
docs/examples that mention v0.1.0 as the latest release
```

Do not mutate or retag `v0.1.0`.

Create a new tag after implementation and tests pass:

```bash
git tag v0.1.1
```

Only push the tag after explicit approval.

## Test Updates

Update `tests/test_plugin_registration.py`.

Expected changes:

```text
ROOT / "plugin.yaml" exists
ROOT / "__init__.py" exists
ROOT plugin loads through Hermes directory-plugin import style
register(ctx) still wires all tools, slash commands, CLI command, and bundled skills
hermes_wiki/ remains importable as the implementation package
old assertion that repo root has no plugin.yaml or __init__.py is removed
old local Docker direct-mount assertions are removed or updated
```

Add a root plugin load test using `importlib.util.spec_from_file_location` against `ROOT / "__init__.py"` with `submodule_search_locations=[str(ROOT)]`.

Keep tests that validate plugin registration behavior through `hermes_wiki.register` so internal imports remain covered.

## Docker Example Updates

Stop treating `hermes_wiki/` as the plugin root.

Update repo-local Docker compose if it still bind-mounts:

```text
../hermes_wiki:/opt/data/profiles/clinic/plugins/hermes-wiki
../hermes_wiki:/home/hermeswebui/.hermes/plugins/hermes-wiki
```

Replace with repo-root plugin mount or remove the plugin mount from production examples entirely:

```text
..:/opt/data/profiles/clinic/plugins/hermes-wiki
..:/home/hermeswebui/.hermes/plugins/hermes-wiki
```

For production VPS, keep plugin install out of the compose stack. The target install path is the Hermes Agent dashboard or `hermes plugins install`.

## Documentation Updates

Update `README.md`.

Make Git/dashboard install the primary path:

```bash
hermes plugins install --enable https://github.com/zombiearnie88/hermes-wiki.git
hermes wiki deps --install all
hermes gateway restart
```

Remove or demote pip install as a legacy/development detail.

Remove instructions that copy installed `hermes_wiki` into `$HERMES_HOME/plugins/hermes-wiki`.

Update `examples/README.md` and `examples/VPS_DEPLOY_CHECKLIST.md` to point dashboard users at:

```text
https://github.com/zombiearnie88/hermes-wiki.git
```

Update troubleshooting text that says `No module named 'hermes_wiki'` usually means a directory-plugin import path problem. After this change, that error should only happen if repo root is incomplete, runtime dependencies are missing, or the cloned plugin directory is corrupted.

## Release Validation

Run unit tests:

```bash
pytest
```

Validate plugin root imports locally:

```bash
python -c "import importlib.util, pathlib; root=pathlib.Path('.').resolve(); spec=importlib.util.spec_from_file_location('hermes_plugins.hermes_wiki', root / '__init__.py', submodule_search_locations=[str(root)]); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); assert callable(m.register)"
```

Validate Docker/VPS install after release:

```bash
docker --context hermes-agent compose -p hermes-production \
  -f examples/docker-compose.production-vps.yml \
  --env-file examples/.env.vps \
  exec -T -u 1000:1000 hermes-agent \
  /opt/hermes/.venv/bin/hermes plugins install --force --enable https://github.com/zombiearnie88/hermes-wiki.git
```

Then restart and verify:

```bash
docker --context hermes-agent compose -p hermes-production \
  -f examples/docker-compose.production-vps.yml \
  --env-file examples/.env.vps \
  restart hermes-agent hermes-webui

docker --context hermes-agent compose -p hermes-production \
  -f examples/docker-compose.production-vps.yml \
  --env-file examples/.env.vps \
  exec -T -u 1000:1000 hermes-agent \
  /opt/hermes/.venv/bin/hermes plugins list
```

Expected plugin list entry:

```text
hermes-wiki    enabled    0.1.1    user
```

Validate CLI registration:

```bash
docker --context hermes-agent compose -p hermes-production \
  -f examples/docker-compose.production-vps.yml \
  --env-file examples/.env.vps \
  exec -T -u 1000:1000 hermes-agent \
  /opt/hermes/.venv/bin/hermes wiki --help
```

## Non-Goals

Do not build a custom Hermes model-provider plugin as part of this change.

Do not add PageIndex long-document support beyond the existing v2 boundary.

Do not add LiteLLM generation paths.

Do not change `hermes_wiki/` to `scripts/`.

Do not force-push or mutate `v0.1.0`.

## Risks

Hermes `plugins install` still does not install Python dependencies automatically.

Directory-plugin install from Git will be layout-native after this change, but runtime dependencies still need `hermes wiki deps --install all` or an equivalent environment bootstrap.

WebUI and Agent may use different Python environments in Docker. If WebUI imports plugin code directly, dependencies may need to exist in both runtimes.

Existing local Docker tests and docs currently assume `hermes_wiki/` is the plugin root and must be updated in the same change.

## Success Criteria

`hermes plugins install --enable https://github.com/zombiearnie88/hermes-wiki.git` installs a valid directory plugin without manual copy/move repair.

`hermes plugins list` shows `hermes-wiki` as enabled with version `0.1.1`.

`hermes wiki --help` works after restart.

`wiki deps --install all` installs runtime dependencies through the plugin command.

Docs present Git/dashboard install as the primary production path and no longer require pip/archive installation.
