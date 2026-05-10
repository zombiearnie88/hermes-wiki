from __future__ import annotations

from pathlib import Path
from typing import Any

DEFAULT_CONFIG: dict[str, Any] = {
    "model": "anthropic/claude-sonnet-4",
    "language": "en",
    "long_doc_threshold": 20,
}


def _parse_scalar(value: str) -> Any:
    stripped = value.strip()
    if not stripped:
        return ""
    if stripped.isdigit():
        return int(stripped)
    if stripped.lower() in {"true", "false"}:
        return stripped.lower() == "true"
    if (stripped.startswith('"') and stripped.endswith('"')) or (
        stripped.startswith("'") and stripped.endswith("'")
    ):
        return stripped[1:-1]
    return stripped


def _dump_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def load_config(config_path: Path) -> dict[str, Any]:
    config = dict(DEFAULT_CONFIG)
    if config_path.exists():
        data: dict[str, Any] = {}
        for raw_line in config_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or ":" not in line:
                continue
            key, value = line.split(":", 1)
            data[key.strip()] = _parse_scalar(value)
        config.update(data)
    return config


def save_config(config_path: Path, config: dict[str, Any]) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{key}: {_dump_scalar(config[key])}" for key in sorted(config)]
    config_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
