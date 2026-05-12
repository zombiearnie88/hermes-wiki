# WebUI Plugin Load Patch Plan

## Goal

Make `hermes-wiki` load as an enabled plugin in the repo-local `hermes-webui` container, not merely appear in `plugins.enabled` config.

## Current Symptom

The WebUI container can be healthy while `hermes-wiki` is unavailable to Hermes:

```text
/health -> status ok
PluginManager list -> hermes-wiki enabled=False, error="No module named 'hermes_wiki'"
```

`docker/data/hermes-home/profiles/clinic/config.yaml` can still show:

```yaml
plugins:
  enabled:
    - hermes-wiki
  disabled: []
```

This means the plugin is enabled by configuration, but disabled at runtime because the import failed during plugin loading.

## Root Cause

Hermes loads directory plugins from `~/.hermes/plugins/<name>` as synthetic modules under `hermes_plugins.*`. For this repo-local Docker setup, `hermes_wiki/` is mounted as:

```text
/home/hermeswebui/.hermes/plugins/hermes-wiki
/opt/data/profiles/clinic/plugins/hermes-wiki
```

The plugin module name at runtime is therefore similar to:

```text
hermes_plugins.hermes_wiki
```

Several PageIndex modules still use absolute imports from the package-install path:

```python
from hermes_wiki.images import load_pymupdf
```

In directory-plugin mode, `hermes_wiki` is not installed as an importable top-level package, so these absolute imports fail and Hermes records the plugin as `enabled=False` with `No module named 'hermes_wiki'`.

## Secondary Issue

The WebUI uses a different Python runtime than `hermes-clinic`:

```text
hermes-clinic: /opt/hermes/.venv/bin/python
hermes-webui:  /app/venv/bin/python3
```

Installing dependencies into the clinic runtime does not install them into the WebUI runtime. Use `uv pip --python` and target the interpreter that imports the plugin.

For WebUI:

```bash
docker compose exec -T hermes-webui uv pip install --python /app/venv/bin/python3 -r /home/hermeswebui/.hermes/plugins/hermes-wiki/requirements.txt
```

For clinic:

```bash
docker compose exec -T hermes-clinic uv pip install --python /opt/hermes/.venv/bin/python -r /opt/data/profiles/clinic/plugins/hermes-wiki/requirements.txt
```

## Patch Scope

Fix importability first. Installing runtime dependencies with `uv pip` is still required, but it does not fix `No module named 'hermes_wiki'` caused by absolute imports in directory-plugin mode.

### 1. Fix Directory-Plugin Imports

Files:

- `hermes_wiki/pageindex/builder.py`
- `hermes_wiki/pageindex/retrieve.py`
- `hermes_wiki/pageindex/store.py`
- `hermes_wiki/pageindex/prompts.py`
- `hermes_wiki/pageindex/config.py`

Replace absolute package imports with relative imports so the plugin works both as an installed package and as a Hermes directory plugin.

Examples:

```python
from hermes_wiki.images import load_pymupdf
```

should become:

```python
from ..images import load_pymupdf
```

### 2. Bootstrap WebUI Dependencies Explicitly

Files:

- `docker/docker-compose.yml`
- optionally `docker/smoke-test-plugin.sh`

Add or document a WebUI dependency bootstrap step that installs `hermes_wiki/requirements.txt` into `/app/venv/bin/python3` with `uv pip install --python`.

Do not use generic `pip install` or `python3 -m pip install` without `--python`, because that can target the wrong interpreter.

### 3. Improve Smoke Test Coverage

Files:

- `docker/smoke-test-plugin.sh`

The current `hermes plugins list` output can show `hermes-wiki enabled` from configuration even when plugin import fails later. Add a runtime load check using `PluginManager.discover_and_load()` and assert:

```text
name == hermes-wiki
enabled == True
error is None
```

Also verify WebUI runtime imports:

```text
json_repair
pymupdf
markitdown
```

against `/app/venv/bin/python3`.

### 4. Update Tests

Files:

- `tests/test_plugin_registration.py`
- add a focused test if needed

Add a regression test that loads `hermes_wiki/__init__.py` through a synthetic module name matching Hermes directory-plugin behavior, for example `hermes_plugins.hermes_wiki`. This catches accidental absolute imports that only work in editable/package installs.

## Validation Checklist

1. `PluginManager.discover_and_load()` reports `hermes-wiki enabled=True` and `error=None` in `hermes-webui`.
2. `PluginManager.discover_and_load()` reports `hermes-wiki enabled=True` and `error=None` in `hermes-clinic`.
3. `/app/venv/bin/python3` can import `json_repair`, `pymupdf`, and `markitdown` in `hermes-webui`.
4. `/opt/hermes/.venv/bin/python` can import `json_repair`, `pymupdf`, and `markitdown` in `hermes-clinic`.
5. `docker compose restart hermes-webui` refreshes the loaded plugin state after source or dependency changes.
6. `./docker/smoke-test-plugin.sh` fails if the plugin is only config-enabled but runtime-disabled.

## Notes

- `hermes plugins list` is useful but not sufficient for this bug class because it may reflect enablement config rather than successful runtime registration.
- A healthy WebUI container does not guarantee the Hermes plugin imported successfully.
- Dependency installation must target the interpreter that imports the plugin.
