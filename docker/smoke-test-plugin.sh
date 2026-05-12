#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
cd "$SCRIPT_DIR"

note() {
  printf '[smoke] %s\n' "$*"
}

fail() {
  printf '[smoke] ERROR: %s\n' "$*" >&2
  exit 1
}

retry() {
  local attempts=$1
  local delay=$2
  local label=$3
  shift 3

  local try=1
  while true; do
    if "$@"; then
      return 0
    fi
    if [[ $try -ge $attempts ]]; then
      fail "$label did not become ready after $attempts attempts"
    fi
    sleep "$delay"
    try=$((try + 1))
  done
}

check_service_running() {
  local service=$1
  local running

  running=$(docker compose ps --status running --services "$service")
  [[ "$running" == "$service" ]] || fail "service '$service' is not running"
}

check_clinic_plugin_loaded() {
  note "Checking runtime plugin load in hermes-clinic"
  docker compose exec -T hermes-clinic /opt/hermes/.venv/bin/python - <<'PY'
try:
    from hermes_cli.plugins import PluginManager
except ModuleNotFoundError as exc:
    raise SystemExit(f"Hermes PluginManager is not importable: {exc}") from None

manager = PluginManager()
manager.discover_and_load(force=True)
matches = [plugin for plugin in manager.list_plugins() if plugin.get("name") == "hermes-wiki"]
if not matches:
    raise SystemExit("hermes-wiki was not discovered")
plugin = matches[0]
if plugin.get("enabled") is not True or plugin.get("error") is not None:
    raise SystemExit(
        f"hermes-wiki runtime load failed: enabled={plugin.get('enabled')} error={plugin.get('error')!r}"
    )
PY
}

check_clinic_files() {
  note "Checking mounted plugin files in hermes-clinic"
  docker compose exec -T hermes-clinic sh -lc '
    test -f /opt/data/profiles/clinic/plugins/hermes-wiki/plugin.yaml &&
    test -f /opt/data/profiles/clinic/plugins/hermes-wiki/__init__.py &&
    test -f /opt/data/profiles/clinic/plugins/hermes-wiki/requirements.txt &&
    test -f /opt/data/profiles/clinic/plugins/hermes-wiki/skills/wiki-operator/SKILL.md
  '
}

check_clinic_runtime_deps() {
  note "Checking wiki runtime dependencies in hermes-clinic"
  docker compose exec -T hermes-clinic /opt/hermes/.venv/bin/python -c '
import importlib.util
required = ("run_agent", "json_repair", "pymupdf", "markitdown")
missing = [name for name in required if importlib.util.find_spec(name) is None]
if missing:
    raise SystemExit(f"missing runtime dependencies: {missing}")
'
}

check_webui_files() {
  note "Checking mounted plugin files in hermes-webui"
  docker compose exec -T -u 0 hermes-webui sh -lc '
    test -f /home/hermeswebui/.hermes/plugins/hermes-wiki/plugin.yaml &&
    test -f /home/hermeswebui/.hermes/plugins/hermes-wiki/__init__.py &&
    test -f /home/hermeswebui/.hermes/plugins/hermes-wiki/requirements.txt &&
    test -f /home/hermeswebui/.hermes/plugins/hermes-wiki/skills/wiki-operator/SKILL.md
  '
}

check_webui_runtime_deps() {
  note "Checking wiki runtime dependencies in hermes-webui"
  docker compose exec -T -u 0 hermes-webui /app/venv/bin/python3 - <<'PY'
import importlib.util

required = ("json_repair", "pymupdf", "markitdown")
missing = [name for name in required if importlib.util.find_spec(name) is None]
if missing:
    raise SystemExit(f"missing WebUI runtime dependencies: {missing}")
PY
}

check_webui_plugin_loaded() {
  note "Checking runtime plugin load in hermes-webui"
  docker compose exec -T -u 0 hermes-webui /app/venv/bin/python3 - <<'PY'
try:
    from hermes_cli.plugins import PluginManager
except ModuleNotFoundError as exc:
    raise SystemExit(f"Hermes PluginManager is not importable yet: {exc}") from None

manager = PluginManager()
manager.discover_and_load(force=True)
matches = [plugin for plugin in manager.list_plugins() if plugin.get("name") == "hermes-wiki"]
if not matches:
    raise SystemExit("hermes-wiki was not discovered")
plugin = matches[0]
if plugin.get("enabled") is not True or plugin.get("error") is not None:
    raise SystemExit(
        f"hermes-wiki runtime load failed: enabled={plugin.get('enabled')} error={plugin.get('error')!r}"
    )
PY
}

main() {
  note "Checking Docker service status"
  check_service_running hermes-clinic
  check_service_running hermes-webui

  check_clinic_files
  retry 10 2 "hermes-clinic runtime dependencies" check_clinic_runtime_deps
  retry 10 2 "hermes-clinic runtime plugin load" check_clinic_plugin_loaded
  check_webui_files
  retry 10 2 "hermes-webui runtime dependencies" check_webui_runtime_deps
  retry 60 5 "hermes-webui runtime plugin load" check_webui_plugin_loaded

  note "Docker plugin smoke test passed"
}

main "$@"
