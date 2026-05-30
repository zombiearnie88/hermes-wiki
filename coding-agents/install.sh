#!/bin/zsh

set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  ./coding-agents/install.sh <opencode|codex|all> <repo|global> [target-repo]

Examples:
  ./coding-agents/install.sh opencode repo /path/to/other-repo
  ./coding-agents/install.sh codex repo /path/to/other-repo
  ./coding-agents/install.sh all repo /path/to/other-repo
  ./coding-agents/install.sh opencode global
  ./coding-agents/install.sh codex global
  ./coding-agents/install.sh all global

Notes:
  - repo mode requires a target repository path
  - global mode installs into ~/.config/opencode and ~/.agents
  - OpenCode config files are merged, not overwritten
EOF
}

if [[ $# -lt 2 ]]; then
  usage
  exit 1
fi

toolset="$1"
scope="$2"
target_repo="${3:-}"

case "$toolset" in
  opencode|codex|all) ;;
  -h|--help|help)
    usage
    exit 0
    ;;
  *)
    printf 'Unsupported toolset: %s\n' "$toolset" >&2
    usage
    exit 1
    ;;
esac

case "$scope" in
  repo|global) ;;
  *)
    printf 'Unsupported scope: %s\n' "$scope" >&2
    usage
    exit 1
    ;;
esac

if [[ "$scope" == "repo" && -z "$target_repo" ]]; then
  printf 'repo mode requires a target repository path\n' >&2
  usage
  exit 1
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${(%):-%N}")" && pwd)"
OPENCODE_SOURCE="$SCRIPT_DIR/opencode/skills/hermes-wiki"
CODEX_SOURCE="$SCRIPT_DIR/codex/skills/hermes-wiki"

if [[ ! -d "$OPENCODE_SOURCE" ]]; then
  printf 'Missing OpenCode source skill: %s\n' "$OPENCODE_SOURCE" >&2
  exit 1
fi

if [[ ! -d "$CODEX_SOURCE" ]]; then
  printf 'Missing Codex source skill: %s\n' "$CODEX_SOURCE" >&2
  exit 1
fi

copy_dir() {
  local source_dir="$1"
  local dest_dir="$2"

  mkdir -p "$(dirname "$dest_dir")"
  rm -rf "$dest_dir"
  cp -R "$source_dir" "$dest_dir"
}

merge_opencode_config() {
  local config_path="$1"
  local skill_path="$2"

  mkdir -p "$(dirname "$config_path")"
  python3 - "$config_path" "$skill_path" <<'PY'
import json
import pathlib
import sys

config_path = pathlib.Path(sys.argv[1])
skill_path = sys.argv[2]

if config_path.exists() and config_path.read_text(encoding="utf-8").strip():
    data = json.loads(config_path.read_text(encoding="utf-8"))
else:
    data = {}

if not isinstance(data, dict):
    raise SystemExit(f"OpenCode config is not a JSON object: {config_path}")

data.setdefault("$schema", "https://opencode.ai/config.json")
skills = data.setdefault("skills", {})
if not isinstance(skills, dict):
    raise SystemExit(f"OpenCode skills config is not an object: {config_path}")

paths = skills.get("paths")
if paths is None:
    paths = []
elif not isinstance(paths, list):
    raise SystemExit(f"OpenCode skills.paths is not an array: {config_path}")

if skill_path not in paths:
    paths.append(skill_path)

skills["paths"] = paths
config_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
PY
}

install_opencode_repo() {
  local repo_root="$1"
  local skill_dest="$repo_root/.opencode/skills/hermes-wiki"
  local config_path="$repo_root/.opencode/opencode.json"

  copy_dir "$OPENCODE_SOURCE" "$skill_dest"
  merge_opencode_config "$config_path" "./.opencode/skills"
  printf 'Installed OpenCode skill into %s\n' "$repo_root"
}

install_opencode_global() {
  local skill_dest="$HOME/.config/opencode/skills/hermes-wiki"
  local config_path="$HOME/.config/opencode/opencode.json"
  local skill_path="$HOME/.config/opencode/skills"

  copy_dir "$OPENCODE_SOURCE" "$skill_dest"
  merge_opencode_config "$config_path" "$skill_path"
  printf 'Installed OpenCode skill into %s\n' "$HOME/.config/opencode"
}

install_codex_repo() {
  local repo_root="$1"
  local skill_dest="$repo_root/.agents/skills/hermes-wiki"

  copy_dir "$CODEX_SOURCE" "$skill_dest"
  printf 'Installed Codex skill into %s\n' "$repo_root"
}

install_codex_global() {
  local skill_dest="$HOME/.agents/skills/hermes-wiki"

  copy_dir "$CODEX_SOURCE" "$skill_dest"
  printf 'Installed Codex skill into %s\n' "$HOME/.agents/skills"
}

if [[ "$scope" == "repo" ]]; then
  mkdir -p "$target_repo"
  target_repo="$(cd "$target_repo" && pwd)"
fi

case "$toolset" in
  opencode)
    if [[ "$scope" == "repo" ]]; then
      install_opencode_repo "$target_repo"
    else
      install_opencode_global
    fi
    ;;
  codex)
    if [[ "$scope" == "repo" ]]; then
      install_codex_repo "$target_repo"
    else
      install_codex_global
    fi
    ;;
  all)
    if [[ "$scope" == "repo" ]]; then
      install_opencode_repo "$target_repo"
      install_codex_repo "$target_repo"
    else
      install_opencode_global
      install_codex_global
    fi
    ;;
esac

printf '\nRestart OpenCode and/or Codex so they reload the new config and assets.\n'
