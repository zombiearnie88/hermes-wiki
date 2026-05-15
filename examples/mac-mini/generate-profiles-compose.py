#!/usr/bin/env python3
"""Generate a Docker Compose file for Hermes Mac mini profiles.

This intentionally supports a small YAML subset so the generator works with
Python's standard library inside python:3.13-alpine, without PyYAML.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any


PROFILE_ID_RE = re.compile(r"^[a-z][a-z0-9-]*$")


def strip_comment(line: str) -> str:
    quote = ""
    escaped = False
    for index, char in enumerate(line):
        if escaped:
            escaped = False
            continue
        if char == "\\" and quote == '"':
            escaped = True
            continue
        if char in ("'", '"'):
            if not quote:
                quote = char
            elif quote == char:
                quote = ""
            continue
        if char == "#" and not quote:
            if index == 0 or line[index - 1].isspace():
                return line[:index]
    return line


def parse_scalar(value: str) -> Any:
    value = value.strip()
    if value == "":
        return ""
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    lowered = value.lower()
    if lowered in {"true", "yes"}:
        return True
    if lowered in {"false", "no"}:
        return False
    if lowered in {"null", "none"}:
        return None
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    return value


def parse_key_value(text: str, line_number: int) -> tuple[str, Any]:
    if ":" not in text:
        raise ValueError(f"line {line_number}: expected key: value")
    key, value = text.split(":", 1)
    key = key.strip()
    if not key:
        raise ValueError(f"line {line_number}: empty key")
    return key, parse_scalar(value)


def parse_profiles_yaml(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = {}
    current_list: str | None = None
    current_item: dict[str, Any] | None = None

    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = strip_comment(raw_line).rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        text = line.strip()

        if indent == 0:
            current_item = None
            if text.endswith(":"):
                key = text[:-1].strip()
                if key != "profiles":
                    raise ValueError(f"line {line_number}: unsupported top-level list {key!r}")
                data[key] = []
                current_list = key
            else:
                key, value = parse_key_value(text, line_number)
                data[key] = value
                current_list = None
            continue

        if indent == 2 and text.startswith("- "):
            if current_list != "profiles":
                raise ValueError(f"line {line_number}: list item outside profiles")
            current_item = {}
            data.setdefault("profiles", []).append(current_item)
            rest = text[2:].strip()
            if rest:
                key, value = parse_key_value(rest, line_number)
                current_item[key] = value
            continue

        if indent >= 4:
            if current_item is None:
                raise ValueError(f"line {line_number}: profile property outside profile item")
            key, value = parse_key_value(text, line_number)
            current_item[key] = value
            continue

        raise ValueError(f"line {line_number}: unsupported indentation")

    return data


def as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def as_port(value: Any, field: str, profile_id: str) -> int:
    try:
        port = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"profile {profile_id}: {field} must be an integer") from error
    if not 1 <= port <= 65535:
        raise ValueError(f"profile {profile_id}: {field} must be between 1 and 65535")
    return port


def quote(value: Any) -> str:
    text = str(value)
    return '"' + text.replace('\\', '\\\\').replace('"', '\\"') + '"'


def normalize_profiles(config: dict[str, Any], args: argparse.Namespace) -> list[dict[str, Any]]:
    raw_profiles = config.get("profiles")
    if not isinstance(raw_profiles, list) or not raw_profiles:
        raise ValueError("profiles.yaml must contain a non-empty profiles list")

    profiles: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_ports: dict[int, str] = {}

    for index, raw_profile in enumerate(raw_profiles):
        if not isinstance(raw_profile, dict):
            raise ValueError(f"profile item {index + 1}: expected object")

        profile_id = str(raw_profile.get("id", "")).strip()
        if not PROFILE_ID_RE.fullmatch(profile_id):
            raise ValueError(
                f"profile item {index + 1}: id must match {PROFILE_ID_RE.pattern}; got {profile_id!r}"
            )
        if profile_id in seen_ids:
            raise ValueError(f"duplicate profile id: {profile_id}")
        seen_ids.add(profile_id)

        bind_ip = args.bind_ip_override or str(raw_profile.get("bind_ip", "127.0.0.1"))
        home_dir = str(
            raw_profile.get("home_dir")
            or Path(args.default_base_dir).joinpath(profile_id, "home")
        )
        workspace_dir = str(
            raw_profile.get("workspace_dir")
            or Path(args.default_base_dir).joinpath(profile_id, "workspace")
        )

        profile = {
            "id": profile_id,
            "home_dir": home_dir,
            "workspace_dir": workspace_dir,
            "bind_ip": bind_ip,
            "webui_port": as_port(raw_profile.get("webui_port", 8787 + index), "webui_port", profile_id),
            "gateway_port": as_port(raw_profile.get("gateway_port", 8642 + index), "gateway_port", profile_id),
            "dashboard_port": as_port(raw_profile.get("dashboard_port", 9119 + index), "dashboard_port", profile_id),
            "dashboard_tui": as_bool(raw_profile.get("dashboard_tui"), False),
            "api_server_key": str(raw_profile.get("api_server_key") or f"local-{profile_id}-api-key"),
        }

        if len(profile["api_server_key"]) < 8:
            raise ValueError(f"profile {profile_id}: api_server_key must be at least 8 characters")

        for field in ("webui_port", "gateway_port", "dashboard_port"):
            port = int(profile[field])
            if port in seen_ports:
                raise ValueError(
                    f"profile {profile_id}: {field}={port} conflicts with profile {seen_ports[port]}"
                )
            seen_ports[port] = profile_id

        profiles.append(profile)

    return profiles


def emit_header(lines: list[str]) -> None:
    lines.extend(
        [
            "# Generated by generate-profiles-compose.py. Do not edit by hand.",
            "# Edit profiles.yaml, then run ./mac-mini.sh profiles-generate.",
            "",
            "services:",
            "  hermes-agent-src-init:",
            "    image: nousresearch/hermes-agent:latest",
            "    restart: \"no\"",
            "    command: version",
            "    volumes:",
            "      - hermes-agent-src:/opt/hermes",
            "    networks:",
            "      - hermes-private",
            "",
            "  hermes-agent-plugin-install:",
            "    image: nousresearch/hermes-agent:latest",
            "    restart: \"no\"",
            "    user: \"0\"",
            "    entrypoint: sh",
            "    depends_on:",
            "      hermes-agent-src-init:",
            "        condition: service_completed_successfully",
            "    command:",
            "      - -lc",
            "      - |",
            "        set -eu",
            "        chown -R \"$${HERMES_UID}:$${HERMES_GID}\" /opt/hermes",
            "        uv pip install --python /opt/hermes/.venv/bin/python \"$${HERMES_WIKI_PACKAGE}\"",
            "        chown -R \"$${HERMES_UID}:$${HERMES_GID}\" /opt/hermes",
            "    volumes:",
            "      - hermes-agent-src:/opt/hermes",
            "    environment:",
            "      HERMES_UID: ${HERMES_UID:-501}",
            "      HERMES_GID: ${HERMES_GID:-20}",
            "      HERMES_WIKI_PACKAGE: ${HERMES_WIKI_PACKAGE:-https://github.com/zombiearnie88/hermes-wiki/archive/refs/tags/v0.1.0.tar.gz}",
            "    networks:",
            "      - hermes-private",
            "",
        ]
    )


def emit_profile(lines: list[str], profile: dict[str, Any], args: argparse.Namespace) -> None:
    profile_id = profile["id"]
    install_service = f"hermes-agent-profile-install-{profile_id}"
    agent_service = f"hermes-agent-{profile_id}"
    webui_install_service = f"hermes-webui-plugin-install-{profile_id}"
    webui_service = f"hermes-webui-{profile_id}"
    webui_volume = f"hermes-webui-venv-{profile_id}"
    dashboard_tui = "1" if profile["dashboard_tui"] else "0"

    lines.extend(
        [
            f"  {install_service}:",
            "    image: nousresearch/hermes-agent:latest",
            "    restart: \"no\"",
            "    user: \"0\"",
            "    entrypoint: sh",
            "    depends_on:",
            "      hermes-agent-plugin-install:",
            "        condition: service_completed_successfully",
            "    command:",
            "      - -lc",
            "      - |",
            "        set -eu",
            "        chown -R \"$${HERMES_UID}:$${HERMES_GID}\" /opt/data/profiles/default /workspace",
            "        plugin_src=\"$(/opt/hermes/.venv/bin/python -c 'import pathlib, hermes_wiki; print(pathlib.Path(hermes_wiki.__file__).resolve().parent)')\"",
            "        mkdir -p \"$${HERMES_HOME}/plugins\"",
            "        rm -rf \"$${HERMES_HOME}/plugins/hermes-wiki\"",
            "        cp -R \"$${plugin_src}\" \"$${HERMES_HOME}/plugins/hermes-wiki\"",
            "        /opt/hermes/.venv/bin/hermes plugins enable hermes-wiki",
            "        chown -R \"$${HERMES_UID}:$${HERMES_GID}\" /opt/data/profiles/default /workspace",
            "    volumes:",
            "      - hermes-agent-src:/opt/hermes",
            f"      - {profile['home_dir']}:/opt/data/profiles/default",
            f"      - {profile['workspace_dir']}:/workspace",
            "    environment:",
            "      HERMES_HOME: /opt/data/profiles/default",
            "      HERMES_UID: ${HERMES_UID:-501}",
            "      HERMES_GID: ${HERMES_GID:-20}",
            "    networks:",
            "      - hermes-private",
            "",
            f"  {agent_service}:",
            "    image: nousresearch/hermes-agent:latest",
            "    restart: unless-stopped",
            "    depends_on:",
            f"      {install_service}:",
            "        condition: service_completed_successfully",
            "    command:",
            "      - gateway",
            "      - run",
            "    ports:",
            f"      - {quote(str(profile['bind_ip']) + ':' + str(profile['gateway_port']) + ':8642')}",
            f"      - {quote(str(profile['bind_ip']) + ':' + str(profile['dashboard_port']) + ':9119')}",
            f"    shm_size: {args.shm_size}",
            "    volumes:",
            "      - hermes-agent-src:/opt/hermes",
            f"      - {profile['home_dir']}:/opt/data/profiles/default",
            f"      - {profile['workspace_dir']}:/workspace",
            "    environment:",
            "      HERMES_HOME: /opt/data/profiles/default",
            "      HERMES_UID: ${HERMES_UID:-501}",
            "      HERMES_GID: ${HERMES_GID:-20}",
            "      API_SERVER_ENABLED: \"true\"",
            "      API_SERVER_HOST: 0.0.0.0",
            "      API_SERVER_PORT: \"8642\"",
            f"      API_SERVER_KEY: {quote(profile['api_server_key'])}",
            "      API_SERVER_CORS_ORIGINS: \"*\"",
            "      HERMES_DASHBOARD: \"1\"",
            "      HERMES_DASHBOARD_HOST: 0.0.0.0",
            "      HERMES_DASHBOARD_PORT: \"9119\"",
            f"      HERMES_DASHBOARD_TUI: {quote(dashboard_tui)}",
            "    networks:",
            "      - hermes-private",
            "",
            f"  {webui_install_service}:",
            "    image: ghcr.io/nesquena/hermes-webui:latest",
            "    restart: \"no\"",
            "    user: \"0\"",
            "    command:",
            "      - sh",
            "      - -lc",
            "      - |",
            "        set -eu",
            "        if [ ! -x /app/venv/bin/python3 ]; then",
            "          uv venv /app/venv",
            "        fi",
            "        uv pip install --python /app/venv/bin/python3 \"$${HERMES_WIKI_PACKAGE}\"",
            "        chmod -R a+rwX /app/venv",
            "    volumes:",
            f"      - {webui_volume}:/app/venv",
            "    environment:",
            "      HERMES_WIKI_PACKAGE: ${HERMES_WIKI_PACKAGE:-https://github.com/zombiearnie88/hermes-wiki/archive/refs/tags/v0.1.0.tar.gz}",
            "    networks:",
            "      - hermes-private",
            "",
            f"  {webui_service}:",
            "    image: ghcr.io/nesquena/hermes-webui:latest",
            "    restart: unless-stopped",
            "    depends_on:",
            "      hermes-agent-src-init:",
            "        condition: service_completed_successfully",
            f"      {agent_service}:",
            "        condition: service_started",
            f"      {webui_install_service}:",
            "        condition: service_completed_successfully",
            "    ports:",
            f"      - {quote(str(profile['bind_ip']) + ':' + str(profile['webui_port']) + ':8787')}",
            f"    shm_size: {args.shm_size}",
            "    volumes:",
            f"      - {profile['home_dir']}:/home/hermeswebui/.hermes",
            "      - hermes-agent-src:/home/hermeswebui/.hermes/hermes-agent",
            f"      - {webui_volume}:/app/venv",
            f"      - {profile['workspace_dir']}:/workspace",
            "    environment:",
            "      HERMES_HOME: /home/hermeswebui/.hermes",
            "      HERMES_CONFIG_PATH: /home/hermeswebui/.hermes/config.yaml",
            "      HERMES_WEBUI_HOST: 0.0.0.0",
            "      HERMES_WEBUI_PORT: \"8787\"",
            "      HERMES_WEBUI_STATE_DIR: /home/hermeswebui/.hermes/webui_state",
            "      HERMES_WEBUI_DEFAULT_WORKSPACE: /workspace",
            "      HERMES_SKIP_CHMOD: ${HERMES_SKIP_CHMOD:-1}",
            "      WANTED_UID: ${HERMES_UID:-501}",
            "      WANTED_GID: ${HERMES_GID:-20}",
            "    networks:",
            "      - hermes-private",
            "",
        ]
    )


def render_compose(profiles: list[dict[str, Any]], args: argparse.Namespace) -> str:
    lines: list[str] = []
    emit_header(lines)
    for profile in profiles:
        emit_profile(lines, profile, args)

    lines.extend(["networks:", "  hermes-private:", "    driver: bridge", "", "volumes:", "  hermes-agent-src:"])
    for profile in profiles:
        lines.append(f"  hermes-webui-venv-{profile['id']}:")
    lines.append("")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profiles", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--default-base-dir", default="/Users/Shared/hermes/profiles")
    parser.add_argument("--bind-ip-override", default="")
    parser.add_argument("--shm-size", default="1g")
    parser.add_argument("--print-dirs", action="store_true")
    parser.add_argument("--print-ports", action="store_true")
    parser.add_argument("--print-webui-ports", action="store_true")
    parser.add_argument("--print-profile-ids", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        config = parse_profiles_yaml(args.profiles)
        profiles = normalize_profiles(config, args)
    except Exception as error:  # noqa: BLE001 - print concise CLI errors.
        print(f"error: {error}", file=sys.stderr)
        return 1

    if args.print_dirs:
        seen: set[str] = set()
        for profile in profiles:
            for directory in (profile["home_dir"], profile["workspace_dir"]):
                if directory not in seen:
                    print(directory)
                    seen.add(directory)
        return 0

    if args.print_ports:
        for profile in profiles:
            print(f"{profile['id']}\twebui\t{profile['webui_port']}")
            print(f"{profile['id']}\tgateway\t{profile['gateway_port']}")
            print(f"{profile['id']}\tdashboard\t{profile['dashboard_port']}")
        return 0

    if args.print_webui_ports:
        for profile in profiles:
            print(f"{profile['id']}\t{profile['webui_port']}")
        return 0

    if args.print_profile_ids:
        for profile in profiles:
            print(profile["id"])
        return 0

    if not args.output:
        print("error: --output is required unless printing metadata", file=sys.stderr)
        return 1

    args.output.write_text(render_compose(profiles, args), encoding="utf-8")
    print(f"Generated {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
