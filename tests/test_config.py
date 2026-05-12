from __future__ import annotations

from pathlib import Path

from hermes_wiki.config import load_config, save_config


def test_config_round_trip_preserves_basic_values(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    save_config(
        config_path,
        {
            "model": "anthropic/claude-sonnet-4",
            "provider": "anthropic",
            "language": "fr",
            "long_doc_threshold": 42,
            "enabled": True,
        },
    )

    loaded = load_config(config_path)

    assert loaded["model"] == "anthropic/claude-sonnet-4"
    assert loaded["provider"] == "anthropic"
    assert loaded["language"] == "fr"
    assert loaded["long_doc_threshold"] == 42
    assert loaded["enabled"] is True


def test_load_config_ignores_comments_and_unknown_lines(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "# comment\nmodel: custom/model\ninvalid line\nlanguage: es\n",
        encoding="utf-8",
    )

    loaded = load_config(config_path)

    assert loaded["model"] == "custom/model"
    assert loaded["provider"] == "openai-codex"
    assert loaded["language"] == "es"
    assert loaded["long_doc_threshold"] == 20
