# Hermes Wiki Docker Plugin Test Checklist

Use this checklist when testing the local bind-mounted `hermes-wiki` plugin with `docker/docker-compose.yml`.

## Prerequisites

- Docker Desktop is running.
- `docker/.env` exists and sets `HERMES_UID`, `HERMES_GID`, `HERMES_SHM_SIZE`, and `HERMES_WEBUI_PORT`.
- The plugin repo root is mounted into the stack from `..`.
- The workspace path is `docker/data/hermes-home/workspace` on the host and `/workspace` in containers.

## Pull Images

```bash
docker compose -f docker/docker-compose.yml pull hermes-agent hermes-webui
```

## Start Or Recreate Stack

```bash
docker compose -f docker/docker-compose.yml up -d --force-recreate hermes-agent hermes-webui-plugin-deps hermes-webui
```

## Check Services

```bash
docker compose -f docker/docker-compose.yml ps
curl -fsS http://127.0.0.1:8787/health
```

Expected:

- `hermes-agent` is `Up`.
- `hermes-webui` is `Up` and `healthy`.
- The health endpoint returns `"status": "ok"`.

## Verify Plugin Mounts

```bash
docker compose -f docker/docker-compose.yml exec -T hermes-agent sh -lc '
  test -f /opt/data/plugins/hermes-wiki/plugin.yaml &&
  test -f /opt/data/plugins/hermes-wiki/__init__.py &&
  test -f /opt/data/plugins/hermes-wiki/requirements.txt
'

docker compose -f docker/docker-compose.yml exec -T -u 0 hermes-webui sh -lc '
  test -f /home/hermeswebui/.hermes/plugins/hermes-wiki/plugin.yaml &&
  test -f /home/hermeswebui/.hermes/plugins/hermes-wiki/__init__.py &&
  test -f /home/hermeswebui/.hermes/plugins/hermes-wiki/requirements.txt
'
```

## Verify Plugin Load

```bash
docker compose -f docker/docker-compose.yml exec -T hermes-agent /opt/hermes/.venv/bin/python -c "from hermes_cli.plugins import PluginManager; m=PluginManager(); m.discover_and_load(force=True); matches=[p for p in m.list_plugins() if p.get('name') == 'hermes-wiki']; print(matches); raise SystemExit(0 if matches and matches[0].get('enabled') is True and matches[0].get('error') is None else 1)"

docker compose -f docker/docker-compose.yml exec -T -u 0 hermes-webui /app/venv/bin/python3 -c "from hermes_cli.plugins import PluginManager; m=PluginManager(); m.discover_and_load(force=True); matches=[p for p in m.list_plugins() if p.get('name') == 'hermes-wiki']; print(matches); raise SystemExit(0 if matches and matches[0].get('enabled') is True and matches[0].get('error') is None else 1)"
```

Expected:

- `enabled` is `True`.
- `error` is `None`.
- `tools` is `8`.
- `commands` is `6`.

## Verify Dependencies

```bash
docker compose -f docker/docker-compose.yml exec -T hermes-agent /opt/hermes/.venv/bin/python -c "import importlib.util; required=('json_repair','pymupdf','markitdown'); missing=[name for name in required if importlib.util.find_spec(name) is None]; print({'missing': missing}); raise SystemExit(1 if missing else 0)"

docker compose -f docker/docker-compose.yml exec -T -u 0 hermes-webui /app/venv/bin/python3 -c "import importlib.util; required=('json_repair','pymupdf','markitdown'); missing=[name for name in required if importlib.util.find_spec(name) is None]; print({'missing': missing}); raise SystemExit(1 if missing else 0)"
```

Expected:

- `missing` is an empty list.

## Test Plugin Commands

```bash
docker compose -f docker/docker-compose.yml exec -T hermes-agent /opt/hermes/.venv/bin/hermes plugins list
```

Expected:

- `hermes-wiki` appears as enabled.

Note: depending on Hermes CLI command registration behavior, `hermes wiki ...` may not appear in plain CLI help even when the plugin is enabled. Plugin manager load checks are the source of truth for runtime registration.

## Trust Gate Config For Generation

Generation uses plugin LLM access with explicit workspace `provider` and `model` routing. The Hermes runtime must allow these overrides for `hermes-wiki`.

Example config under `docker/data/hermes-home/config.yaml`:

```yaml
plugins:
  entries:
    hermes-wiki:
      llm:
        allow_provider_override: true
        allow_model_override: true
        allowed_providers:
          - openai-codex
        allowed_models:
          - gpt-5.4-mini
```

Development-only setups may use `allowed_providers: ["*"]` and `allowed_models: ["*"]`.

## Common Issues

- Docker daemon unavailable: start Docker Desktop, then rerun compose.
- WebUI restarts with `chown` errors on `.git` files: keep the repo mounted outside WebUI home at `/opt/hermes-wiki-src:ro` and symlink it into `/home/hermeswebui/.hermes/plugins/hermes-wiki` before running `/hermeswebui_init.bash`.
- Plugin enabled but not loaded: inspect `PluginManager.discover_and_load(force=True)` output and check `error`.
- Dependency import failures: recreate `hermes-webui-plugin-deps` and `hermes-agent` so requirements install again.
- New plugin Python code or schemas not reflected: recreate `hermes-agent` and `hermes-webui`.
