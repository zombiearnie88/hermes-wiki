#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${SCRIPT_DIR}/docker-compose.yml"
DEFAULT_ENV_FILE="${SCRIPT_DIR}/mac-mini.env"
EXAMPLE_ENV_FILE="${SCRIPT_DIR}/mac-mini.env.example"
PROFILES_GENERATOR="${SCRIPT_DIR}/generate-profiles-compose.py"
DEFAULT_PROFILES_FILE="${SCRIPT_DIR}/profiles.yaml"
EXAMPLE_PROFILES_FILE="${SCRIPT_DIR}/profiles.yaml.example"
GENERATED_PROFILES_COMPOSE_FILE="${SCRIPT_DIR}/docker-compose.profiles.generated.yml"

ENV_FILE="${DEFAULT_ENV_FILE}"
ENV_FILE_EXPLICIT=0
PROFILES_FILE="${DEFAULT_PROFILES_FILE}"
PROFILES_FILE_EXPLICIT=0
COMMAND=""
COMMAND_ARGS=()

usage() {
  cat <<EOF
Usage: $0 [--env PATH] <command>

Commands:
  bootstrap-local  First-run local-only deploy: preflight, storage, up, wait, verify
  bootstrap-lan    First-run LAN deploy: preflight, storage, up, wait, verify
  profiles-generate         Generate compose from profiles.yaml
  profiles-bootstrap-local  First-run local profile deploy
  profiles-bootstrap-lan    First-run LAN profile deploy
  profiles-preflight        Check Docker and profile port availability
  profiles-init-storage     Create and chown profile host storage
  profiles-up-local         Deploy profile WebUIs bound to 127.0.0.1
  profiles-up-lan           Deploy profile WebUIs bound to 0.0.0.0
  profiles-wait-ready       Wait until profile WebUIs respond locally
  profiles-verify           Check profile containers and HTTP access
  profiles-ps               Show profile compose service status
  profiles-logs             Show recent profile logs
  profiles-cleanup          Remove completed one-shot profile setup containers
  profiles-down             Stop profile containers, preserving volumes and host data
  profiles-down-volumes     Stop profile containers plus Docker named runtime volumes
  preflight        Check Docker, UID/GID, port availability, and compose status
  init-storage     Create and chown persistent host storage
  up-local         Deploy WebUI bound to 127.0.0.1
  up-lan           Deploy WebUI bound to 0.0.0.0
  wait-ready       Wait until WebUI responds locally
  verify           Check containers, plugin enablement, imports, and HTTP access
  auth [args...]   Run hermes auth inside the Hermes Agent container
  auth-providers   List auth providers available in the Hermes Agent runtime
  ps               Show compose service status
  logs             Show recent deployment logs
  restart          Restart Hermes Agent and WebUI
  update           Rerun plugin installers and restart runtime services
  pull             Pull base images and recreate containers
  down             Stop and remove containers, preserving volumes and host data
  down-volumes     Stop and remove containers plus Docker named runtime volumes

Options:
  --env PATH       Env file to load. Defaults to ${DEFAULT_ENV_FILE} if present
  --profiles PATH  Profiles YAML to load. Defaults to ${DEFAULT_PROFILES_FILE} if present, else ${EXAMPLE_PROFILES_FILE}
  -h, --help       Show this help

Copy-and-run local deploy:
  $0 bootstrap-local

Optional customization:
  cp ${EXAMPLE_ENV_FILE} ${DEFAULT_ENV_FILE}
  cp ${EXAMPLE_PROFILES_FILE} ${DEFAULT_PROFILES_FILE}
  vi ${DEFAULT_ENV_FILE}
  $0 bootstrap-local
EOF
}

die() {
  printf 'error: %s\n' "$*" >&2
  exit 1
}

info() {
  printf '%s\n' "$*"
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --env)
      [ "$#" -ge 2 ] || die '--env requires a path'
      ENV_FILE="$2"
      ENV_FILE_EXPLICIT=1
      shift 2
      ;;
    --profiles)
      [ "$#" -ge 2 ] || die '--profiles requires a path'
      PROFILES_FILE="$2"
      PROFILES_FILE_EXPLICIT=1
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      COMMAND="$1"
      shift
      COMMAND_ARGS=("$@")
      break
      ;;
  esac
done

[ -n "${COMMAND}" ] || {
  usage
  exit 1
}

[ -f "${COMPOSE_FILE}" ] || die "compose file not found: ${COMPOSE_FILE}"
[ -f "${PROFILES_GENERATOR}" ] || die "profiles generator not found: ${PROFILES_GENERATOR}"

if [ -f "${PROFILES_FILE}" ]; then
  :
elif [ "${PROFILES_FILE_EXPLICIT}" = "1" ]; then
  die "profiles file not found: ${PROFILES_FILE}"
elif [ -f "${EXAMPLE_PROFILES_FILE}" ]; then
  PROFILES_FILE="${EXAMPLE_PROFILES_FILE}"
else
  die "profiles file not found: ${DEFAULT_PROFILES_FILE}; example file not found: ${EXAMPLE_PROFILES_FILE}"
fi

if [ -f "${ENV_FILE}" ]; then
  set -a
  # shellcheck disable=SC1090
  . "${ENV_FILE}"
  set +a
elif [ "${ENV_FILE_EXPLICIT}" = "1" ]; then
  die "env file not found: ${ENV_FILE}"
fi

HERMES_COMPOSE_PROJECT="${HERMES_COMPOSE_PROJECT:-hermes-mac-mini}"
HERMES_PROFILES_COMPOSE_PROJECT="${HERMES_PROFILES_COMPOSE_PROJECT:-hermes-mac-mini-profiles}"
HERMES_PROFILES_BASE_DIR="${HERMES_PROFILES_BASE_DIR:-/Users/Shared/hermes/profiles}"
HERMES_UID="${HERMES_UID:-$(id -u)}"
HERMES_GID="${HERMES_GID:-$(id -g)}"
HERMES_WEBUI_BIND_IP="${HERMES_WEBUI_BIND_IP:-127.0.0.1}"
HERMES_WEBUI_PORT="${HERMES_WEBUI_PORT:-8787}"
HERMES_HOME_DIR="${HERMES_HOME_DIR:-/Users/Shared/hermes/home}"
HERMES_WORKSPACE_DIR="${HERMES_WORKSPACE_DIR:-/Users/Shared/hermes/workspace}"
HERMES_WIKI_PACKAGE="${HERMES_WIKI_PACKAGE:-https://github.com/zombiearnie88/hermes-wiki/archive/refs/tags/v0.1.0.tar.gz}"
HERMES_SHM_SIZE="${HERMES_SHM_SIZE:-1g}"
HERMES_SKIP_CHMOD="${HERMES_SKIP_CHMOD:-1}"

export HERMES_COMPOSE_PROJECT HERMES_PROFILES_COMPOSE_PROJECT HERMES_UID HERMES_GID HERMES_WEBUI_BIND_IP HERMES_WEBUI_PORT
export HERMES_HOME_DIR HERMES_WORKSPACE_DIR HERMES_WIKI_PACKAGE
export HERMES_PROFILES_BASE_DIR HERMES_SHM_SIZE HERMES_SKIP_CHMOD

compose() {
  docker compose -p "${HERMES_COMPOSE_PROJECT}" -f "${COMPOSE_FILE}" "$@"
}

profiles_compose() {
  [ -f "${GENERATED_PROFILES_COMPOSE_FILE}" ] || profiles_generate
  docker compose -p "${HERMES_PROFILES_COMPOSE_PROJECT}" -f "${GENERATED_PROFILES_COMPOSE_FILE}" "$@"
}

absolute_path() {
  case "$1" in
    /*) printf '%s\n' "$1" ;;
    *) printf '%s\n' "$(pwd)/$1" ;;
  esac
}

run_profiles_generator() {
  if command -v python3 >/dev/null 2>&1; then
    python3 "${PROFILES_GENERATOR}" "$@"
    return
  fi

  profiles_abs="$(absolute_path "${PROFILES_FILE}")"
  profiles_dir="$(cd "$(dirname "${profiles_abs}")" && pwd)"
  profiles_name="$(basename "${profiles_abs}")"
  output_abs="$(absolute_path "${GENERATED_PROFILES_COMPOSE_FILE}")"
  output_dir="$(cd "$(dirname "${output_abs}")" && pwd)"
  output_name="$(basename "${output_abs}")"

  docker_args=()
  for arg in "$@"; do
    case "$arg" in
      "${PROFILES_FILE}"|"${profiles_abs}")
        docker_args+=("/profiles/${profiles_name}")
        ;;
      "${GENERATED_PROFILES_COMPOSE_FILE}"|"${output_abs}")
        docker_args+=("/output/${output_name}")
        ;;
      *)
        docker_args+=("$arg")
        ;;
    esac
  done

  docker run --rm \
    -v "${SCRIPT_DIR}:/bundle:ro" \
    -v "${profiles_dir}:/profiles:ro" \
    -v "${output_dir}:/output" \
    -w /bundle \
    python:3.13-alpine \
    python /bundle/generate-profiles-compose.py "${docker_args[@]}"
}

profiles_generate() {
  bind_ip_override="${1:-}"
  args=(
    --profiles "${PROFILES_FILE}"
    --output "${GENERATED_PROFILES_COMPOSE_FILE}"
    --default-base-dir "${HERMES_PROFILES_BASE_DIR}"
    --shm-size "${HERMES_SHM_SIZE}"
  )
  if [ -n "${bind_ip_override}" ]; then
    args+=(--bind-ip-override "${bind_ip_override}")
  fi
  run_profiles_generator "${args[@]}"
}

profiles_metadata() {
  flag="$1"
  bind_ip_override="${2:-}"
  args=(
    --profiles "${PROFILES_FILE}"
    --default-base-dir "${HERMES_PROFILES_BASE_DIR}"
    "${flag}"
  )
  if [ -n "${bind_ip_override}" ]; then
    args+=(--bind-ip-override "${bind_ip_override}")
  fi
  run_profiles_generator "${args[@]}"
}

show_config() {
  info "Bundle dir: ${SCRIPT_DIR}"
  info "Env file: ${ENV_FILE}"
  info "Profiles file: ${PROFILES_FILE}"
  info "Compose file: ${COMPOSE_FILE}"
  info "Profiles compose file: ${GENERATED_PROFILES_COMPOSE_FILE}"
  info "HERMES_COMPOSE_PROJECT=${HERMES_COMPOSE_PROJECT}"
  info "HERMES_PROFILES_COMPOSE_PROJECT=${HERMES_PROFILES_COMPOSE_PROJECT}"
  info "HERMES_PROFILES_BASE_DIR=${HERMES_PROFILES_BASE_DIR}"
  info "HERMES_UID=${HERMES_UID}"
  info "HERMES_GID=${HERMES_GID}"
  info "HERMES_WEBUI_BIND_IP=${HERMES_WEBUI_BIND_IP}"
  info "HERMES_WEBUI_PORT=${HERMES_WEBUI_PORT}"
  info "HERMES_HOME_DIR=${HERMES_HOME_DIR}"
  info "HERMES_WORKSPACE_DIR=${HERMES_WORKSPACE_DIR}"
  info "HERMES_WIKI_PACKAGE=${HERMES_WIKI_PACKAGE}"
}

check_port_free() {
  info "Checking TCP port ${HERMES_WEBUI_PORT}:"
  if lsof -nP -iTCP:"${HERMES_WEBUI_PORT}" -sTCP:LISTEN; then
    die "port ${HERMES_WEBUI_PORT} is already in use"
  fi
  info "Port ${HERMES_WEBUI_PORT}: free"
}

preflight() {
  show_config
  info ""
  docker --version
  docker compose version
  docker info >/dev/null
  info "Docker daemon: reachable"
  info "Architecture: $(uname -m)"
  info "Current UID:GID: $(id -u):$(id -g)"

  if [ "${HERMES_UID}" != "$(id -u)" ] || [ "${HERMES_GID}" != "$(id -g)" ]; then
    info "warning: HERMES_UID:HERMES_GID does not match current user $(id -u):$(id -g)"
  fi

  case "${HERMES_WIKI_PACKAGE}" in
    git+*)
      info "warning: git+ package URLs require git inside installer images; release archive URLs are safer for Docker deployment"
      ;;
  esac

  info ""
  check_port_free

  info ""
  info "Compose stack status:"
  compose ps

  info ""
  info "Running containers:"
  docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'
}

init_storage() {
  info "Creating persistent storage:"
  info "  ${HERMES_HOME_DIR}"
  info "  ${HERMES_WORKSPACE_DIR}"
  sudo mkdir -p "${HERMES_HOME_DIR}" "${HERMES_WORKSPACE_DIR}"
  sudo chown -R "${HERMES_UID}:${HERMES_GID}" "${HERMES_HOME_DIR}" "${HERMES_WORKSPACE_DIR}"
  ls -ld "${HERMES_HOME_DIR}" "${HERMES_WORKSPACE_DIR}"
}

up_local() {
  export HERMES_WEBUI_BIND_IP=127.0.0.1
  info "Deploying local-only WebUI on http://127.0.0.1:${HERMES_WEBUI_PORT}"
  compose up -d
}

up_lan() {
  export HERMES_WEBUI_BIND_IP=0.0.0.0
  info "Deploying LAN WebUI on port ${HERMES_WEBUI_PORT}"
  compose up -d

  LAN_IP=""
  for iface in en0 en1; do
    LAN_IP="$(ipconfig getifaddr "${iface}" 2>/dev/null || true)"
    if [ -n "${LAN_IP}" ]; then
      break
    fi
  done

  if [ -n "${LAN_IP}" ]; then
    info "LAN URL: http://${LAN_IP}:${HERMES_WEBUI_PORT}"
  else
    info "LAN URL: http://<mac-mini-lan-ip>:${HERMES_WEBUI_PORT}"
    info "Run 'ipconfig getifaddr en0' or 'ipconfig getifaddr en1' to find the address."
  fi
}

wait_ready() {
  timeout_seconds="${1:-300}"
  start_seconds="${SECONDS}"
  info "Waiting up to ${timeout_seconds}s for http://127.0.0.1:${HERMES_WEBUI_PORT}"

  while [ $((SECONDS - start_seconds)) -lt "${timeout_seconds}" ]; do
    if curl -fsS -o /dev/null "http://127.0.0.1:${HERMES_WEBUI_PORT}"; then
      info "WebUI is ready: http://127.0.0.1:${HERMES_WEBUI_PORT}"
      return 0
    fi
    sleep 5
  done

  compose ps
  compose logs --tail=120 hermes-webui
  die "WebUI did not become ready within ${timeout_seconds}s"
}

verify() {
  info "Compose status:"
  compose ps

  info ""
  info "Verifying Hermes Agent plugin state:"
  compose exec -T hermes-agent /opt/hermes/.venv/bin/hermes plugins list

  info ""
  info "Verifying WebUI package import:"
  compose exec -T -u 0 hermes-webui /app/venv/bin/python3 -c "import hermes_wiki; assert callable(hermes_wiki.register)"

  info ""
  info "Verifying local HTTP response:"
  curl -fsS -o /dev/null "http://127.0.0.1:${HERMES_WEBUI_PORT}"
  info "HTTP OK: http://127.0.0.1:${HERMES_WEBUI_PORT}"
}

logs() {
  compose logs --tail=100 hermes-agent-plugin-install hermes-webui-plugin-install hermes-agent hermes-webui
}

run_auth() {
  compose exec hermes-agent /opt/hermes/.venv/bin/hermes auth "$@"
}

auth_providers() {
  [ "$#" -eq 0 ] || die 'auth-providers does not accept arguments'
  compose exec -T hermes-agent /opt/hermes/.venv/bin/python -c '
from hermes_cli.auth import PROVIDER_REGISTRY, SERVICE_PROVIDER_NAMES

print("provider_id\tname\tauth_type")
for provider in sorted(PROVIDER_REGISTRY.values(), key=lambda item: item.id):
    print(f"{provider.id}\t{provider.name}\t{provider.auth_type}")
for provider in sorted(SERVICE_PROVIDER_NAMES):
    print(f"{provider}\tservice\tservice")
'
}

check_profiles_ports() {
  bind_ip_override="${1:-}"
  ports_output="$(profiles_metadata --print-ports "${bind_ip_override}")"
  while IFS=$'\t' read -r profile_id port_kind port; do
    [ -n "${profile_id}" ] || continue
    info "Checking ${profile_id} ${port_kind} port ${port}:"
    if lsof -nP -iTCP:"${port}" -sTCP:LISTEN; then
      die "port ${port} is already in use"
    fi
    info "Port ${port}: free"
  done <<EOF
${ports_output}
EOF
}

profiles_preflight() {
  bind_ip_override="${1:-}"
  profiles_generate "${bind_ip_override}"
  show_config
  info ""
  docker --version
  docker compose version
  docker info >/dev/null
  info "Docker daemon: reachable"
  info "Architecture: $(uname -m)"
  info "Current UID:GID: $(id -u):$(id -g)"

  if [ "${HERMES_UID}" != "$(id -u)" ] || [ "${HERMES_GID}" != "$(id -g)" ]; then
    info "warning: HERMES_UID:HERMES_GID does not match current user $(id -u):$(id -g)"
  fi

  info ""
  check_profiles_ports "${bind_ip_override}"

  info ""
  info "Profile compose stack status:"
  profiles_compose ps
}

profiles_init_storage() {
  dirs_output="$(profiles_metadata --print-dirs)"
  info "Creating profile persistent storage:"
  while IFS= read -r directory; do
    [ -n "${directory}" ] || continue
    info "  ${directory}"
    sudo mkdir -p "${directory}"
    sudo chown -R "${HERMES_UID}:${HERMES_GID}" "${directory}"
  done <<EOF
${dirs_output}
EOF
}

profiles_up_local() {
  profiles_generate 127.0.0.1
  info "Deploying profile WebUIs locally"
  profiles_compose up -d
  profiles_print_urls local
}

profiles_up_lan() {
  profiles_generate 0.0.0.0
  info "Deploying profile WebUIs on LAN"
  profiles_compose up -d
  profiles_print_urls lan
}

profiles_print_urls() {
  access_mode="${1:-local}"
  ports_output="$(profiles_metadata --print-ports)"
  lan_ip=""
  for iface in en0 en1; do
    lan_ip="$(ipconfig getifaddr "${iface}" 2>/dev/null || true)"
    if [ -n "${lan_ip}" ]; then
      break
    fi
  done
  [ -n "${lan_ip}" ] || lan_ip="<mac-mini-lan-ip>"

  while IFS=$'\t' read -r profile_id port_kind port; do
    [ -n "${profile_id}" ] || continue
    if [ "${access_mode}" = "lan" ]; then
      host_text="http://127.0.0.1:${port} or http://${lan_ip}:${port}"
    else
      host_text="http://127.0.0.1:${port}"
    fi
    case "${port_kind}" in
      webui)
        info "${profile_id} WebUI: ${host_text}"
        ;;
      dashboard)
        info "${profile_id} dashboard: ${host_text}"
        ;;
      gateway)
        info "${profile_id} gateway API: ${host_text}"
        ;;
    esac
  done <<EOF
${ports_output}
EOF
}

profiles_wait_ready() {
  timeout_seconds="${1:-300}"
  webui_ports_output="$(profiles_metadata --print-webui-ports)"

  while IFS=$'\t' read -r profile_id port; do
    [ -n "${profile_id}" ] || continue
    start_seconds="${SECONDS}"
    info "Waiting up to ${timeout_seconds}s for ${profile_id} WebUI at http://127.0.0.1:${port}"
    while [ $((SECONDS - start_seconds)) -lt "${timeout_seconds}" ]; do
      if curl -fsS -o /dev/null "http://127.0.0.1:${port}"; then
        info "${profile_id} WebUI is ready: http://127.0.0.1:${port}"
        break
      fi
      sleep 5
    done
    if [ $((SECONDS - start_seconds)) -ge "${timeout_seconds}" ]; then
      profiles_compose ps
      profiles_compose logs --tail=120 "hermes-webui-${profile_id}"
      die "${profile_id} WebUI did not become ready within ${timeout_seconds}s"
    fi
  done <<EOF
${webui_ports_output}
EOF
}

profiles_verify() {
  info "Profile compose status:"
  profiles_compose ps

  ids_output="$(profiles_metadata --print-profile-ids)"
  while IFS= read -r profile_id; do
    [ -n "${profile_id}" ] || continue
    info ""
    info "Verifying ${profile_id} Hermes Agent plugin state:"
    profiles_compose exec -T "hermes-agent-${profile_id}" /opt/hermes/.venv/bin/hermes plugins list
    info ""
    info "Verifying ${profile_id} WebUI package import:"
    profiles_compose exec -T -u 0 "hermes-webui-${profile_id}" /app/venv/bin/python3 -c "import hermes_wiki; assert callable(hermes_wiki.register)"
  done <<EOF
${ids_output}
EOF

  webui_ports_output="$(profiles_metadata --print-webui-ports)"
  while IFS=$'\t' read -r profile_id port; do
    [ -n "${profile_id}" ] || continue
    info ""
    info "Verifying ${profile_id} local HTTP response:"
    curl -fsS -o /dev/null "http://127.0.0.1:${port}"
    info "HTTP OK: http://127.0.0.1:${port}"
  done <<EOF
${webui_ports_output}
EOF
}

profiles_bootstrap_local() {
  profiles_preflight 127.0.0.1
  profiles_init_storage
  profiles_up_local
  profiles_wait_ready
  profiles_verify
  profiles_cleanup
}

profiles_bootstrap_lan() {
  profiles_preflight 0.0.0.0
  profiles_init_storage
  profiles_up_lan
  profiles_wait_ready
  profiles_verify
  profiles_cleanup
}

profiles_logs() {
  profiles_compose logs --tail=100
}

profiles_cleanup() {
  ids_output="$(profiles_metadata --print-profile-ids)"
  services=(hermes-agent-src-init hermes-agent-plugin-install)

  while IFS= read -r profile_id; do
    [ -n "${profile_id}" ] || continue
    services+=(
      "hermes-agent-profile-install-${profile_id}"
      "hermes-webui-plugin-install-${profile_id}"
    )
  done <<EOF
${ids_output}
EOF

  info "Removing completed profile setup containers:"
  for service in "${services[@]}"; do
    info "  ${service}"
  done
  profiles_compose rm -f "${services[@]}"
}

restart_services() {
  compose restart hermes-agent hermes-webui
}

update_plugins() {
  compose up -d --force-recreate hermes-agent-plugin-install hermes-webui-plugin-install
  compose restart hermes-agent hermes-webui
}

pull_images() {
  compose pull
  compose up -d --force-recreate
}

bootstrap_local() {
  export HERMES_WEBUI_BIND_IP=127.0.0.1
  preflight
  init_storage
  up_local
  wait_ready
  verify
}

bootstrap_lan() {
  export HERMES_WEBUI_BIND_IP=0.0.0.0
  preflight
  init_storage
  up_lan
  wait_ready
  verify
}

case "${COMMAND}" in
  bootstrap-local)
    bootstrap_local
    ;;
  bootstrap-lan)
    bootstrap_lan
    ;;
  profiles-generate)
    if [ "${#COMMAND_ARGS[@]}" -eq 0 ]; then
      profiles_generate
    else
      profiles_generate "${COMMAND_ARGS[@]}"
    fi
    ;;
  profiles-bootstrap-local)
    profiles_bootstrap_local
    ;;
  profiles-bootstrap-lan)
    profiles_bootstrap_lan
    ;;
  profiles-preflight)
    if [ "${#COMMAND_ARGS[@]}" -eq 0 ]; then
      profiles_preflight
    else
      profiles_preflight "${COMMAND_ARGS[@]}"
    fi
    ;;
  profiles-init-storage)
    profiles_init_storage
    ;;
  profiles-up-local)
    profiles_up_local
    ;;
  profiles-up-lan)
    profiles_up_lan
    ;;
  profiles-wait-ready)
    if [ "${#COMMAND_ARGS[@]}" -eq 0 ]; then
      profiles_wait_ready
    else
      profiles_wait_ready "${COMMAND_ARGS[@]}"
    fi
    ;;
  profiles-verify)
    profiles_verify
    ;;
  profiles-ps)
    profiles_compose ps
    ;;
  profiles-logs)
    profiles_logs
    ;;
  profiles-cleanup)
    profiles_cleanup
    ;;
  profiles-down)
    profiles_compose down
    ;;
  profiles-down-volumes)
    profiles_compose down -v
    ;;
  preflight)
    preflight
    ;;
  init-storage)
    init_storage
    ;;
  up-local)
    up_local
    ;;
  up-lan)
    up_lan
    ;;
  wait-ready)
    if [ "${#COMMAND_ARGS[@]}" -eq 0 ]; then
      wait_ready
    else
      wait_ready "${COMMAND_ARGS[@]}"
    fi
    ;;
  verify)
    verify
    ;;
  auth)
    if [ "${#COMMAND_ARGS[@]}" -eq 0 ]; then
      run_auth
    else
      run_auth "${COMMAND_ARGS[@]}"
    fi
    ;;
  auth-providers)
    if [ "${#COMMAND_ARGS[@]}" -eq 0 ]; then
      auth_providers
    else
      auth_providers "${COMMAND_ARGS[@]}"
    fi
    ;;
  ps)
    compose ps
    ;;
  logs)
    logs
    ;;
  restart)
    restart_services
    ;;
  update)
    update_plugins
    ;;
  pull)
    pull_images
    ;;
  down)
    compose down
    ;;
  down-volumes)
    compose down -v
    ;;
  *)
    usage
    die "unknown command: ${COMMAND}"
    ;;
esac
