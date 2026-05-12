from __future__ import annotations

from pathlib import Path

from hermes_wiki.state import HashRegistry


def test_hash_registry_persists_entries(tmp_path: Path) -> None:
    registry_path = tmp_path / "hashes.json"
    registry = HashRegistry(registry_path)
    registry.add("abc123", {"name": "note.md", "type": "md"})

    reloaded = HashRegistry(registry_path)

    assert reloaded.is_known("abc123")
    assert reloaded.get("abc123") == {"name": "note.md", "type": "md"}


def test_hash_file_is_stable(tmp_path: Path) -> None:
    file_path = tmp_path / "note.txt"
    file_path.write_text("hello world\n", encoding="utf-8")

    first = HashRegistry.hash_file(file_path)
    second = HashRegistry.hash_file(file_path)

    assert first == second
    assert len(first) == 64


def test_hash_registry_reports_corrupt_json(tmp_path: Path) -> None:
    registry_path = tmp_path / "hashes.json"
    registry_path.write_text("{not valid json", encoding="utf-8")

    try:
        HashRegistry(registry_path)
    except RuntimeError as exc:
        assert "Hash registry is corrupt" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError")
