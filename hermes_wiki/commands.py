from __future__ import annotations

import argparse
import shlex
from pathlib import Path

from hermes_wiki.compiler import compile_short_doc
from hermes_wiki.config import DEFAULT_CONFIG, load_config
from hermes_wiki.converter import SUPPORTED_EXTENSIONS, convert_document
from hermes_wiki.log import append_log
from hermes_wiki.state import HashRegistry
from hermes_wiki.workspace import find_workspace, init_workspace, read_workspace_status, workspace_paths


def _resolve_workspace(workspace_override: str | None) -> tuple[Path | None, str | None]:
    if workspace_override:
        candidate = Path(workspace_override).expanduser().resolve()
        if not candidate.exists():
            return None, f"Workspace path does not exist: {candidate}"
        paths = find_workspace(candidate)
        if paths is None:
            return None, f"Not a Hermes wiki workspace: {candidate}"
        return paths.root, None

    paths = find_workspace(Path.cwd())
    if paths is None:
        return None, "No Hermes wiki workspace found. Run `hermes wiki init` first."
    return paths.root, None


def _collect_supported_files(target: Path) -> list[Path]:
    return [
        path
        for path in sorted(target.rglob("*"))
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    ]


def _format_status() -> str:
    workspace_root, error = _resolve_workspace(None)
    if error:
        return error
    paths = workspace_paths(workspace_root)
    status = read_workspace_status(paths)
    return "\n".join(
        [
            f"Workspace: {status.root}",
            f"Model: {status.model}",
            f"Language: {status.language}",
            f"Long-doc threshold: {status.long_doc_threshold}",
            f"Raw files: {status.raw_files}",
            f"Source pages: {status.source_pages}",
            f"Summary pages: {status.summary_pages}",
            f"Concept pages: {status.concept_pages}",
            f"Known hashes: {status.known_hashes}",
        ]
    )


def _run_init(path: str, model: str, language: str, long_doc_threshold: int) -> str:
    root = Path(path).expanduser().resolve()
    init_workspace(
        root,
        model=model,
        language=language,
        long_doc_threshold=long_doc_threshold,
    )
    return "\n".join(
        [
            f"Initialized Hermes wiki workspace at {root}",
            "Created: raw/, wiki/, .hermeskb/",
        ]
    )


def _run_status(workspace_override: str | None) -> str:
    workspace_root, error = _resolve_workspace(workspace_override)
    if error:
        return error
    status = read_workspace_status(workspace_paths(workspace_root))
    return "\n".join(
        [
            f"Workspace: {status.root}",
            f"Model: {status.model}",
            f"Language: {status.language}",
            f"Long-doc threshold: {status.long_doc_threshold}",
            f"Raw files: {status.raw_files}",
            f"Source pages: {status.source_pages}",
            f"Summary pages: {status.summary_pages}",
            f"Concept pages: {status.concept_pages}",
            f"Known hashes: {status.known_hashes}",
        ]
    )


def _run_add(target_path: str, workspace_override: str | None) -> str:
    workspace_root, error = _resolve_workspace(workspace_override)
    if error:
        return error
    paths = workspace_paths(workspace_root)
    config = load_config(paths.config_path)
    model = str(config.get("model", DEFAULT_CONFIG["model"]))

    target = Path(target_path).expanduser().resolve()
    if not target.exists():
        return f"Path does not exist: {target}"

    if target.is_dir():
        files = _collect_supported_files(target)
        if not files:
            return f"No supported files found in {target}"
    else:
        if target.suffix.lower() not in SUPPORTED_EXTENSIONS:
            supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
            return f"Unsupported file type: {target.suffix}. Supported: {supported}"
        files = [target]

    lines: list[str] = []
    registry = HashRegistry(paths.hashes_path)
    for file_path in files:
        try:
            convert_result = convert_document(file_path, paths)
            if convert_result.skipped:
                lines.append(f"SKIP {file_path.name}: already in workspace")
                continue

            if convert_result.unsupported_long_doc:
                lines.append(
                    f"UNSUPPORTED {file_path.name}: long documents are not supported yet "
                    f"({convert_result.long_doc_page_count} pages >= {config.get('long_doc_threshold', 20)} threshold)"
                )
                continue

            if convert_result.source_path is None or convert_result.file_hash is None:
                lines.append(f"ERROR {file_path.name}: conversion did not produce a source page")
                continue

            doc_name = convert_result.doc_name or file_path.stem
            compile_result = compile_short_doc(doc_name, convert_result.source_path, paths, model)
            registry.add(
                convert_result.file_hash,
                {
                    "name": file_path.name,
                    "type": file_path.suffix.lstrip("."),
                    "doc_name": doc_name,
                },
            )
            append_log(paths.wiki_dir, "ingest", file_path.name)
            rename_note = ""
            if doc_name != file_path.stem:
                rename_note = f" as {doc_name}"
            lines.append(
                f"OK {file_path.name}{rename_note}: summary written, created {compile_result.created_concepts}, "
                f"updated {compile_result.updated_concepts}, related {compile_result.related_concepts}"
            )
        except Exception as exc:
            lines.append(f"ERROR {file_path.name}: {exc}")

    return "\n".join(lines)


def _build_init_parser(prog: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=prog, add_help=False)
    parser.add_argument("path", nargs="?", default=".")
    parser.add_argument("--model", default=DEFAULT_CONFIG["model"])
    parser.add_argument("--language", default=DEFAULT_CONFIG["language"])
    parser.add_argument("--long-doc-threshold", type=int, default=DEFAULT_CONFIG["long_doc_threshold"])
    parser.add_argument("-h", "--help", action="store_true")
    return parser


def _build_status_parser(prog: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=prog, add_help=False)
    parser.add_argument("--workspace", default=None)
    parser.add_argument("-h", "--help", action="store_true")
    return parser


def _build_add_parser(prog: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=prog, add_help=False)
    parser.add_argument("path")
    parser.add_argument("--workspace", default=None)
    parser.add_argument("-h", "--help", action="store_true")
    return parser


def handle_wiki_init_command(raw_args: str) -> str:
    parser = _build_init_parser("/wiki-init")
    try:
        args = parser.parse_args(shlex.split(raw_args))
    except SystemExit:
        return "Usage: /wiki-init [path] [--model MODEL] [--language LANG] [--long-doc-threshold N]"
    if args.help:
        return "Usage: /wiki-init [path] [--model MODEL] [--language LANG] [--long-doc-threshold N]"
    try:
        return _run_init(args.path, args.model, args.language, args.long_doc_threshold)
    except Exception as exc:
        return f"Failed to initialize workspace: {exc}"


def handle_wiki_status_command(raw_args: str) -> str:
    parser = _build_status_parser("/wiki-status")
    try:
        args = parser.parse_args(shlex.split(raw_args))
    except SystemExit:
        return "Usage: /wiki-status [--workspace DIR]"
    if args.help:
        return "Usage: /wiki-status [--workspace DIR]"
    return _run_status(args.workspace)


def handle_wiki_add_command(raw_args: str) -> str:
    parser = _build_add_parser("/wiki-add")
    try:
        args = parser.parse_args(shlex.split(raw_args))
    except SystemExit:
        return "Usage: /wiki-add <path> [--workspace DIR]"
    if args.help:
        return "Usage: /wiki-add <path> [--workspace DIR]"
    try:
        return _run_add(args.path, args.workspace)
    except Exception as exc:
        return f"Failed to add content: {exc}"


def setup_wiki_cli(subparser) -> None:
    subcommands = subparser.add_subparsers(dest="wiki_command")

    init_parser = subcommands.add_parser("init", help="Initialize a Hermes wiki workspace")
    init_parser.add_argument("path", nargs="?", default=".")
    init_parser.add_argument("--model", default=DEFAULT_CONFIG["model"])
    init_parser.add_argument("--language", default=DEFAULT_CONFIG["language"])
    init_parser.add_argument("--long-doc-threshold", type=int, default=DEFAULT_CONFIG["long_doc_threshold"])

    add_parser = subcommands.add_parser("add", help="Add a file or directory to a Hermes wiki workspace")
    add_parser.add_argument("path")
    add_parser.add_argument("--workspace", default=None)

    status_parser = subcommands.add_parser("status", help="Show Hermes wiki workspace status")
    status_parser.add_argument("--workspace", default=None)

    subparser.set_defaults(func=handle_wiki_cli)


def handle_wiki_cli(args) -> None:
    try:
        if args.wiki_command == "init":
            output = _run_init(args.path, args.model, args.language, args.long_doc_threshold)
        elif args.wiki_command == "add":
            output = _run_add(args.path, args.workspace)
        elif args.wiki_command == "status":
            output = _run_status(args.workspace)
        else:
            output = "Usage: hermes wiki <init|add|status>"
    except Exception as exc:
        output = f"Hermes wiki command failed: {exc}"
    print(output)
