from __future__ import annotations

import hashlib
import json
from pathlib import Path


class HashRegistry:
    """Persistent registry mapping file hashes to metadata dicts."""

    def __init__(self, path: Path) -> None:
        self._path = path
        if path.exists():
            try:
                with path.open("r", encoding="utf-8") as handle:
                    self._data: dict[str, dict] = json.load(handle)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"Hash registry is corrupt: {path}") from exc
        else:
            self._data = {}

    def is_known(self, file_hash: str) -> bool:
        return file_hash in self._data

    def get(self, file_hash: str) -> dict | None:
        return self._data.get(file_hash)

    def all_entries(self) -> dict[str, dict]:
        return dict(self._data)

    def add(self, file_hash: str, metadata: dict) -> None:
        self._data[file_hash] = metadata
        self._persist()

    def _persist(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("w", encoding="utf-8") as handle:
            json.dump(self._data, handle, indent=2)

    @staticmethod
    def hash_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(65536), b""):
                digest.update(chunk)
        return digest.hexdigest()
