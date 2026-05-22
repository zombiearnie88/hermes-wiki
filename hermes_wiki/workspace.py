from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .config import DEFAULT_CONFIG, load_config, save_config
from .schema import build_agents_md, build_schema_md
from .state import HashRegistry


STATE_DIR_NAME = ".hermeskb"


@dataclass(frozen=True)
class WorkspacePaths:
    root: Path

    @property
    def raw_dir(self) -> Path:
        return self.root / "raw"

    @property
    def wiki_dir(self) -> Path:
        return self.root / "wiki"

    @property
    def state_dir(self) -> Path:
        return self.root / STATE_DIR_NAME

    @property
    def config_path(self) -> Path:
        return self.state_dir / "config.yaml"

    @property
    def hashes_path(self) -> Path:
        return self.state_dir / "hashes.json"

    @property
    def pageindex_dir(self) -> Path:
        return self.state_dir / "pageindex"

    @property
    def index_path(self) -> Path:
        return self.wiki_dir / "index.md"

    @property
    def log_path(self) -> Path:
        return self.wiki_dir / "log.md"

    @property
    def schema_path(self) -> Path:
        return self.wiki_dir / "SCHEMA.md"

    @property
    def agents_path(self) -> Path:
        return self.root / "AGENTS.md"

@dataclass(frozen=True)
class WorkspaceStatus:
    root: Path
    model: str
    provider: str
    language: str
    long_doc_threshold: int
    concept_generation_concurrency: int
    raw_files: int
    source_pages: int
    summary_pages: int
    concept_pages: int
    known_hashes: int


def workspace_paths(root: Path) -> WorkspacePaths:
    return WorkspacePaths(root=root.resolve())


def is_workspace(root: Path) -> bool:
    paths = workspace_paths(root)
    return paths.state_dir.is_dir() and paths.wiki_dir.is_dir() and paths.raw_dir.is_dir()


def find_workspace(start: Path | None = None) -> WorkspacePaths | None:
    current = (start or Path.cwd()).resolve()
    if current.is_file():
        current = current.parent

    while True:
        if is_workspace(current):
            return workspace_paths(current)
        parent = current.parent
        if parent == current:
            return None
        current = parent


def init_workspace(
    root: Path,
    *,
    model: str,
    provider: str | None = None,
    language: str,
    long_doc_threshold: int,
    domain: str | None = None,
) -> WorkspacePaths:
    paths = workspace_paths(root)
    existing = [
        path.name
        for path in (paths.raw_dir, paths.wiki_dir, paths.state_dir)
        if path.exists()
    ]
    if existing:
        names = ", ".join(sorted(existing))
        raise FileExistsError(f"Workspace already initialized or partially initialized ({names}).")

    paths.raw_dir.mkdir(parents=True, exist_ok=False)
    (paths.wiki_dir / "sources" / "images").mkdir(parents=True, exist_ok=False)
    (paths.wiki_dir / "summaries").mkdir(parents=True, exist_ok=False)
    (paths.wiki_dir / "concepts").mkdir(parents=True, exist_ok=False)
    (paths.wiki_dir / "explorations").mkdir(parents=True, exist_ok=False)
    (paths.wiki_dir / "reports").mkdir(parents=True, exist_ok=False)
    paths.state_dir.mkdir(parents=True, exist_ok=False)
    paths.pageindex_dir.mkdir(parents=True, exist_ok=False)

    paths.schema_path.write_text(build_schema_md(domain), encoding="utf-8")
    paths.agents_path.write_text(build_agents_md(), encoding="utf-8")
    paths.index_path.write_text(
        "# Knowledge Base Index\n\n## Documents\n\n## Concepts\n\n## Explorations\n",
        encoding="utf-8",
    )
    paths.log_path.write_text("# Operations Log\n\n", encoding="utf-8")

    config = dict(DEFAULT_CONFIG)
    config.update(
        {
            "model": model,
            "provider": provider or DEFAULT_CONFIG["provider"],
            "language": language,
            "long_doc_threshold": long_doc_threshold,
        }
    )
    save_config(paths.config_path, config)
    paths.hashes_path.write_text(json.dumps({}), encoding="utf-8")
    return paths


def read_workspace_status(paths: WorkspacePaths) -> WorkspaceStatus:
    """Return workspace counters and current persisted wiki settings."""
    config = load_config(paths.config_path)
    registry = HashRegistry(paths.hashes_path)
    sources_dir = paths.wiki_dir / "sources"
    source_pages = len(list(sources_dir.glob("*.md"))) + len(list(sources_dir.glob("*.jsonl")))
    summary_pages = len(list((paths.wiki_dir / "summaries").glob("*.md")))
    concept_pages = len(list((paths.wiki_dir / "concepts").glob("*.md")))
    raw_files = len([path for path in paths.raw_dir.iterdir() if path.is_file()]) if paths.raw_dir.exists() else 0

    return WorkspaceStatus(
        root=paths.root,
        model=str(config.get("model", DEFAULT_CONFIG["model"])),
        provider=str(config.get("provider", DEFAULT_CONFIG["provider"])),
        language=str(config.get("language", DEFAULT_CONFIG["language"])),
        long_doc_threshold=int(config.get("long_doc_threshold", DEFAULT_CONFIG["long_doc_threshold"])),
        concept_generation_concurrency=int(
            config.get("concept_generation_concurrency", DEFAULT_CONFIG["concept_generation_concurrency"])
        ),
        raw_files=raw_files,
        source_pages=source_pages,
        summary_pages=summary_pages,
        concept_pages=concept_pages,
        known_hashes=len(registry.all_entries()),
    )
