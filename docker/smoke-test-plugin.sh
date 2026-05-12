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

check_clinic_discovery() {
  local output

  note "Checking plugin discovery in hermes-clinic"
  output=$(docker compose exec -T hermes-clinic /opt/hermes/.venv/bin/hermes plugins list)
  printf '%s\n' "$output" | grep -q 'hermes-wiki' || fail "hermes-clinic does not list hermes-wiki"
  printf '%s\n' "$output" | grep -Eq 'hermes-wiki.*enabled' || fail "hermes-wiki is not enabled in hermes-clinic"
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
    test -f /home/hermeswebui/.hermes/plugins/hermes-wiki/skills/wiki-operator/SKILL.md
  '
}

check_webui_discovery() {
  local output
  local status

  note "Attempting plugin discovery in hermes-webui"
  set +e
  output=$(docker compose exec -T -u 0 hermes-webui sh -lc '/home/hermeswebui/.hermes/hermes-agent/hermes plugins list' 2>&1)
  status=$?
  set -e

  if [[ $status -eq 0 ]]; then
    printf '%s\n' "$output" | grep -q 'hermes-wiki' || fail "hermes-webui does not list hermes-wiki"
    note "hermes-webui can run Hermes plugin discovery directly"
    return
  fi

  if [[ "$output" == *"No module named 'yaml'"* ]]; then
    note "hermes-webui image does not ship Hermes CLI Python deps; using mount and container-health checks instead"
    return
  fi

  fail "unexpected hermes-webui plugin discovery failure: $output"
}

main() {
  note "Checking Docker service status"
  check_service_running hermes-clinic
  check_service_running hermes-webui

  check_clinic_files
  retry 10 2 "hermes-clinic plugin discovery" check_clinic_discovery
  retry 10 2 "hermes-clinic runtime dependencies" check_clinic_runtime_deps
  check_webui_files
  check_webui_discovery

  note "Docker plugin smoke test passed"
}

main "$@"
