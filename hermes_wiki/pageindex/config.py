from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import DEFAULT_CONFIG, load_config


@dataclass(frozen=True)
class PageIndexConfig:
    toc_check_pages: int
    max_pages_per_node: int
    max_tokens_per_node: int
    summary_token_threshold: int
    max_pages_per_tool_call: int


def _positive_int(config: dict[str, Any], key: str) -> int:
    value = int(config.get(key, DEFAULT_CONFIG[key]))
    if value <= 0:
        raise ValueError(f"{key} must be greater than zero.")
    return value


def load_pageindex_config(config_path: Path) -> PageIndexConfig:
    config = load_config(config_path)
    return PageIndexConfig(
        toc_check_pages=_positive_int(config, "pageindex_toc_check_pages"),
        max_pages_per_node=_positive_int(config, "pageindex_max_pages_per_node"),
        max_tokens_per_node=_positive_int(config, "pageindex_max_tokens_per_node"),
        summary_token_threshold=_positive_int(config, "pageindex_summary_token_threshold"),
        max_pages_per_tool_call=_positive_int(config, "pageindex_max_pages_per_tool_call"),
    )
