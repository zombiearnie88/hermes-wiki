from __future__ import annotations

from pathlib import Path

from hermes_wiki.config import CONCEPT_GENERATION_CONCURRENCY_MAX, DEFAULT_CONFIG, load_config, save_config


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


def test_default_config_includes_concept_generation_concurrency(tmp_path: Path) -> None:
    loaded = load_config(tmp_path / "missing.yaml")

    assert DEFAULT_CONFIG["concept_generation_concurrency"] == 3
    assert loaded["concept_generation_concurrency"] == 3


def test_concept_generation_concurrency_normalizes_invalid_values(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"

    config_path.write_text("concept_generation_concurrency: invalid\n", encoding="utf-8")
    assert load_config(config_path)["concept_generation_concurrency"] == 3

    config_path.write_text("concept_generation_concurrency: -2\n", encoding="utf-8")
    assert load_config(config_path)["concept_generation_concurrency"] == 1

    config_path.write_text("concept_generation_concurrency: 999\n", encoding="utf-8")
    assert load_config(config_path)["concept_generation_concurrency"] == CONCEPT_GENERATION_CONCURRENCY_MAX
