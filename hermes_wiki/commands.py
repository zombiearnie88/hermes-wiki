from __future__ import annotations

import argparse
import shlex
import subprocess
from pathlib import Path

from .compiler import compile_pageindex_doc, compile_short_doc
from .config import DEFAULT_CONFIG, load_config, normalize_concept_generation_concurrency, save_config
from .converter import SUPPORTED_EXTENSIONS, convert_document
from .deps import (
    build_uv_install_command,
    build_uv_install_command_for_packages,
    capability_statuses,
    dependency_statuses,
    install_dependency_group,
    install_groups,
    package_specs_for_groups,
    runtime_python_path,
)
from .log import append_log
from .state import HashRegistry
from .workspace import find_workspace, init_workspace, read_workspace_status, workspace_paths

_PDF_EXTENSIONS = {".pdf"}
_MARKITDOWN_EXTENSIONS = {".docx", ".pptx", ".xlsx", ".html", ".htm"}
_INSTALL_GROUP_ORDER = ("core", "pdf", "office")


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


def _validate_settings(
    *,
    model: str | None = None,
    provider: str | None = None,
    language: str | None = None,
    long_doc_threshold: int | None = None,
) -> None:
    if model is not None and not str(model).strip():
        raise ValueError("Model must not be empty.")
    if provider is not None and not str(provider).strip():
        raise ValueError("Provider must not be empty.")
    if language is not None and not str(language).strip():
        raise ValueError("Language must not be empty.")
    if long_doc_threshold is not None and long_doc_threshold <= 0:
        raise ValueError("Long-doc threshold must be greater than zero.")


def is_failure_output(text: str) -> bool:
    failure_prefixes = (
        "Usage:",
        "Failed ",
        "No Hermes wiki workspace found",
        "Workspace path does not exist:",
        "Not a Hermes wiki workspace:",
        "Path does not exist:",
        "No supported files found in ",
        "Unsupported file type:",
        "ERROR ",
    )
    return text.startswith(failure_prefixes)


def _dependency_repair_lines(*, include_group_commands: bool = False) -> list[str]:
    available = {entry.module_name: entry.available for entry in dependency_statuses()}
    lines: list[str] = []

    if not available.get("run_agent", False):
        lines.append("- Hermes runtime: run this plugin inside a Hermes environment that provides run_agent.AIAgent")

    if include_group_commands:
        group_lines = []
        for group in _INSTALL_GROUP_ORDER:
            command = build_uv_install_command(group, missing_only=True)
            if command:
                group_lines.append(f"- Install missing {group}: {command}")
        if group_lines:
            lines.extend(group_lines)
            all_command = build_uv_install_command("all", missing_only=True)
            if all_command:
                lines.append(f"- Install all missing packages: {all_command}")
        elif available.get("run_agent", False):
            lines.append("- Installable packages: none missing")
        return lines

    command = build_uv_install_command("all", missing_only=True)
    if command:
        lines.append(f"- Install missing packages: {command}")
    return lines


def _dependency_report_lines(*, include_group_commands: bool = False) -> list[str]:
    dependency_lines = [
        f"- {entry.label}: {'available' if entry.available else 'missing'}"
        for entry in dependency_statuses()
    ]
    capability_lines = [
        f"- {entry.label}: {'ready' if entry.ready else 'blocked'} ({entry.detail})"
        for entry in capability_statuses()
    ]
    lines = [
        f"Runtime Python: {runtime_python_path()}",
        "Capabilities:",
        *capability_lines,
        "Dependencies:",
        *dependency_lines,
    ]
    repair_lines = _dependency_repair_lines(include_group_commands=include_group_commands)
    if repair_lines:
        lines.extend(["Repair:", *repair_lines])
    return lines


def _required_install_groups_for_files(files: list[Path]) -> list[str]:
    groups = ["core"]
    for file_path in files:
        suffix = file_path.suffix.lower()
        if suffix in _PDF_EXTENSIONS and "pdf" not in groups:
            groups.append("pdf")
        if suffix in _MARKITDOWN_EXTENSIONS and "office" not in groups:
            groups.append("office")
    return groups


def _check_add_requirements(files: list[Path]) -> str | None:
    required_groups = _required_install_groups_for_files(files)
    available = {entry.module_name: entry.available for entry in dependency_statuses()}
    missing_messages: list[str] = []
    missing_install_groups: list[str] = []

    if not available.get("run_agent", False):
        missing_messages.append(
            "- Hermes runtime is missing: run this plugin inside a Hermes environment that provides run_agent.AIAgent."
        )
    if "core" in required_groups and not available.get("json_repair", False):
        missing_messages.append("- Missing json-repair for summary and concept generation.")
        missing_install_groups.append("core")
    if "pdf" in required_groups and not available.get("pymupdf", False):
        missing_messages.append("- Missing PyMuPDF for PDF ingest.")
        missing_install_groups.append("pdf")
    if "office" in required_groups and not available.get("markitdown", False):
        missing_messages.append("- Missing MarkItDown for Office/HTML ingest.")
        missing_install_groups.append("office")

    if not missing_messages:
        return None

    install_command = build_uv_install_command_for_packages(
        package_specs_for_groups(missing_install_groups, missing_only=True)
    )
    lines = [
        "ERROR wiki add is blocked by missing runtime dependencies.",
        f"Runtime Python: {runtime_python_path()}",
        *missing_messages,
    ]
    if install_command:
        lines.append(f"Repair command: {install_command}")
    return "\n".join(lines)


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
            f"Provider: {status.provider}",
            f"Language: {status.language}",
            f"Long-doc threshold: {status.long_doc_threshold}",
            f"Concept generation concurrency: {status.concept_generation_concurrency}",
            f"Raw files: {status.raw_files}",
            f"Source pages: {status.source_pages}",
            f"Summary pages: {status.summary_pages}",
            f"Concept pages: {status.concept_pages}",
            f"Known hashes: {status.known_hashes}",
            *_dependency_report_lines(),
        ]
    )


def _run_init(
    path: str,
    model: str,
    language: str,
    long_doc_threshold: int,
    *,
    provider: str | None = None,
    domain: str | None = None,
) -> str:
    _validate_settings(model=model, provider=provider, language=language, long_doc_threshold=long_doc_threshold)
    root = Path(path).expanduser().resolve()
    init_workspace(
        root,
        model=model,
        provider=provider,
        language=language,
        long_doc_threshold=long_doc_threshold,
        domain=domain,
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
            f"Provider: {status.provider}",
            f"Language: {status.language}",
            f"Long-doc threshold: {status.long_doc_threshold}",
            f"Concept generation concurrency: {status.concept_generation_concurrency}",
            f"Raw files: {status.raw_files}",
            f"Source pages: {status.source_pages}",
            f"Summary pages: {status.summary_pages}",
            f"Concept pages: {status.concept_pages}",
            f"Known hashes: {status.known_hashes}",
            *_dependency_report_lines(),
        ]
    )


def _run_deps(install: str | None = None) -> str:
    if install is None:
        return "\n".join(_dependency_report_lines(include_group_commands=True))

    if install not in install_groups():
        valid_groups = ", ".join(install_groups())
        return f"ERROR Unsupported dependency group: {install}. Valid groups: {valid_groups}"

    try:
        result = install_dependency_group(install, missing_only=True)
    except subprocess.TimeoutExpired as exc:
        timeout = int(exc.timeout) if exc.timeout else 0
        return f"ERROR dependency install failed: timed out after {timeout} seconds"
    except Exception as exc:
        return f"ERROR dependency install failed: {exc}"

    if result.exit_code != 0:
        lines = [
            "ERROR dependency install failed.",
            f"Group: {install}",
            f"Runtime Python: {runtime_python_path()}",
        ]
        if result.command:
            lines.append(f"Command: {result.command}")
        if result.stdout.strip():
            lines.extend(["stdout:", result.stdout.strip()])
        if result.stderr.strip():
            lines.extend(["stderr:", result.stderr.strip()])
        return "\n".join(lines)

    if result.packages:
        lines = [f"Installed dependency group '{install}': {', '.join(result.packages)}"]
        if result.command:
            lines.append(f"Command: {result.command}")
    else:
        lines = [f"Dependency group '{install}' is already satisfied."]
    lines.extend(_dependency_report_lines())
    return "\n".join(lines)


def _run_list(workspace_override: str | None) -> str:
    workspace_root, error = _resolve_workspace(workspace_override)
    if error:
        return error

    paths = workspace_paths(workspace_root)
    registry = HashRegistry(paths.hashes_path)
    entries = sorted(
        registry.all_entries().values(),
        key=lambda entry: (str(entry.get("doc_name", entry.get("name", ""))).lower(), str(entry.get("name", "")).lower()),
    )
    concept_names = sorted(path.stem for path in (paths.wiki_dir / "concepts").glob("*.md"))

    lines = [f"Workspace: {paths.root}", "Documents:"]
    if entries:
        for entry in entries:
            display_name = entry.get("doc_name") or Path(str(entry.get("name", ""))).stem
            source_name = entry.get("name", display_name)
            doc_type = entry.get("type", "unknown")
            lines.append(f"- {display_name} ({doc_type}) <- {source_name}")
    else:
        lines.append("- none")

    lines.append("Concepts:")
    if concept_names:
        lines.extend(f"- {name}" for name in concept_names)
    else:
        lines.append("- none")
    return "\n".join(lines)


def _run_config(
    workspace_override: str | None,
    *,
    model: str | None = None,
    provider: str | None = None,
    language: str | None = None,
    long_doc_threshold: int | None = None,
    concept_generation_concurrency: int | None = None,
) -> str:
    workspace_root, error = _resolve_workspace(workspace_override)
    if error:
        return error
    _validate_settings(model=model, provider=provider, language=language, long_doc_threshold=long_doc_threshold)

    paths = workspace_paths(workspace_root)
    config = load_config(paths.config_path)
    updated = False

    if model is not None:
        config["model"] = model
        updated = True
    if provider is not None:
        config["provider"] = provider
        updated = True
    if language is not None:
        config["language"] = language
        updated = True
    if long_doc_threshold is not None:
        config["long_doc_threshold"] = long_doc_threshold
        updated = True
    if concept_generation_concurrency is not None:
        config["concept_generation_concurrency"] = normalize_concept_generation_concurrency(
            concept_generation_concurrency
        )
        updated = True

    if updated:
        save_config(paths.config_path, config)

    lines = []
    if updated:
        lines.append("Updated workspace config.")
    lines.extend(
        [
            f"Workspace: {paths.root}",
            f"Model: {config.get('model', DEFAULT_CONFIG['model'])}",
            f"Provider: {config.get('provider', DEFAULT_CONFIG['provider'])}",
            f"Language: {config.get('language', DEFAULT_CONFIG['language'])}",
            f"Long-doc threshold: {config.get('long_doc_threshold', DEFAULT_CONFIG['long_doc_threshold'])}",
            "Concept generation concurrency: "
            f"{config.get('concept_generation_concurrency', DEFAULT_CONFIG['concept_generation_concurrency'])}",
        ]
    )
    return "\n".join(lines)


def _run_add(
    target_path: str,
    workspace_override: str | None,
    model_override: str | None = None,
    language_override: str | None = None,
    provider_override: str | None = None,
) -> str:
    workspace_root, error = _resolve_workspace(workspace_override)
    if error:
        return error
    _validate_settings(model=model_override, provider=provider_override, language=language_override)
    paths = workspace_paths(workspace_root)
    config = load_config(paths.config_path)
    model = model_override or str(config.get("model", DEFAULT_CONFIG["model"]))
    provider = provider_override or str(config.get("provider", DEFAULT_CONFIG["provider"]))

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

    dependency_error = _check_add_requirements(files)
    if dependency_error:
        return dependency_error

    lines: list[str] = []
    registry = HashRegistry(paths.hashes_path)
    for file_path in files:
        try:
            convert_result = convert_document(file_path, paths)
            if convert_result.skipped:
                lines.append(f"SKIP {file_path.name}: already in workspace")
                continue

            if convert_result.unsupported_long_doc:
                if convert_result.raw_path is None or convert_result.file_hash is None:
                    lines.append(f"ERROR {file_path.name}: conversion did not produce a raw PDF")
                    continue
                doc_name = convert_result.doc_name or file_path.stem
                compile_result = compile_pageindex_doc(
                    doc_name,
                    convert_result.raw_path,
                    paths,
                    model,
                    provider,
                    language_override=language_override,
                )
                registry.add(
                    convert_result.file_hash,
                    {
                        "name": file_path.name,
                        "type": "pageindex",
                        "doc_name": doc_name,
                    },
                )
                append_log(paths.wiki_dir, "ingest", file_path.name)
                rename_note = ""
                if doc_name != file_path.stem:
                    rename_note = f" as {doc_name}"
                lines.append(
                    f"OK {file_path.name}{rename_note}: pageindex summary written "
                    f"({convert_result.long_doc_page_count} pages), created {compile_result.created_concepts}, "
                    f"updated {compile_result.updated_concepts}, related {compile_result.related_concepts}"
                )
                continue

            if convert_result.source_path is None or convert_result.file_hash is None:
                lines.append(f"ERROR {file_path.name}: conversion did not produce a source page")
                continue

            doc_name = convert_result.doc_name or file_path.stem
            compile_result = compile_short_doc(
                doc_name,
                convert_result.source_path,
                paths,
                model,
                provider,
                language_override=language_override,
            )
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
    parser.add_argument("--provider", default=DEFAULT_CONFIG["provider"])
    parser.add_argument("--language", default=DEFAULT_CONFIG["language"])
    parser.add_argument("--long-doc-threshold", type=int, default=DEFAULT_CONFIG["long_doc_threshold"])
    parser.add_argument("--domain", default=None)
    parser.add_argument("-h", "--help", action="store_true")
    return parser


def _build_status_parser(prog: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=prog, add_help=False)
    parser.add_argument("--workspace", default=None)
    parser.add_argument("-h", "--help", action="store_true")
    return parser


def _build_list_parser(prog: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=prog, add_help=False)
    parser.add_argument("--workspace", default=None)
    parser.add_argument("-h", "--help", action="store_true")
    return parser


def _build_config_parser(prog: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=prog, add_help=False)
    parser.add_argument("--workspace", default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--provider", default=None)
    parser.add_argument("--language", default=None)
    parser.add_argument("--long-doc-threshold", type=int, default=None)
    parser.add_argument("--concept-generation-concurrency", type=int, default=None)
    parser.add_argument("-h", "--help", action="store_true")
    return parser


def _build_add_parser(prog: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=prog, add_help=False)
    parser.add_argument("path")
    parser.add_argument("--workspace", default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--provider", default=None)
    parser.add_argument("--language", default=None)
    parser.add_argument("-h", "--help", action="store_true")
    return parser


def _build_deps_parser(prog: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=prog, add_help=False)
    parser.add_argument("--install", choices=install_groups(), default=None)
    parser.add_argument("-h", "--help", action="store_true")
    return parser


def handle_wiki_init_command(raw_args: str) -> str:
    parser = _build_init_parser("/wiki-init")
    try:
        args = parser.parse_args(shlex.split(raw_args))
    except SystemExit:
        return "Usage: /wiki-init [path] [--model MODEL] [--provider PROVIDER] [--language LANG] [--long-doc-threshold N] [--domain DOMAIN]"
    if args.help:
        return "Usage: /wiki-init [path] [--model MODEL] [--provider PROVIDER] [--language LANG] [--long-doc-threshold N] [--domain DOMAIN]"
    try:
        return _run_init(
            args.path,
            args.model,
            args.language,
            args.long_doc_threshold,
            provider=args.provider,
            domain=args.domain,
        )
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
    try:
        return _run_status(args.workspace)
    except Exception as exc:
        return f"Failed to read status: {exc}"


def handle_wiki_list_command(raw_args: str) -> str:
    parser = _build_list_parser("/wiki-list")
    try:
        args = parser.parse_args(shlex.split(raw_args))
    except SystemExit:
        return "Usage: /wiki-list [--workspace DIR]"
    if args.help:
        return "Usage: /wiki-list [--workspace DIR]"
    try:
        return _run_list(args.workspace)
    except Exception as exc:
        return f"Failed to list workspace: {exc}"


def handle_wiki_config_command(raw_args: str) -> str:
    parser = _build_config_parser("/wiki-config")
    try:
        args = parser.parse_args(shlex.split(raw_args))
    except SystemExit:
        return "Usage: /wiki-config [--workspace DIR] [--model MODEL] [--provider PROVIDER] [--language LANG] [--long-doc-threshold N] [--concept-generation-concurrency N]"
    if args.help:
        return "Usage: /wiki-config [--workspace DIR] [--model MODEL] [--provider PROVIDER] [--language LANG] [--long-doc-threshold N] [--concept-generation-concurrency N]"
    try:
        return _run_config(
            args.workspace,
            model=args.model,
            provider=args.provider,
            language=args.language,
            long_doc_threshold=args.long_doc_threshold,
            concept_generation_concurrency=args.concept_generation_concurrency,
        )
    except Exception as exc:
        return f"Failed to update config: {exc}"


def handle_wiki_add_command(raw_args: str) -> str:
    parser = _build_add_parser("/wiki-add")
    try:
        args = parser.parse_args(shlex.split(raw_args))
    except SystemExit:
        return "Usage: /wiki-add <path> [--workspace DIR] [--model MODEL] [--provider PROVIDER] [--language LANG]"
    if args.help:
        return "Usage: /wiki-add <path> [--workspace DIR] [--model MODEL] [--provider PROVIDER] [--language LANG]"
    try:
        return _run_add(args.path, args.workspace, args.model, args.language, args.provider)
    except Exception as exc:
        return f"Failed to add content: {exc}"


def handle_wiki_deps_command(raw_args: str) -> str:
    parser = _build_deps_parser("/wiki-deps")
    try:
        args = parser.parse_args(shlex.split(raw_args))
    except SystemExit:
        return "Usage: /wiki-deps [--install core|pdf|office|all]"
    if args.help:
        return "Usage: /wiki-deps [--install core|pdf|office|all]"
    try:
        return _run_deps(args.install)
    except Exception as exc:
        return f"Failed to inspect dependencies: {exc}"


def setup_wiki_cli(subparser) -> None:
    subcommands = subparser.add_subparsers(dest="wiki_command")

    init_parser = subcommands.add_parser("init", help="Initialize a Hermes wiki workspace")
    init_parser.add_argument("path", nargs="?", default=".")
    init_parser.add_argument("--model", default=DEFAULT_CONFIG["model"])
    init_parser.add_argument("--provider", default=DEFAULT_CONFIG["provider"])
    init_parser.add_argument("--language", default=DEFAULT_CONFIG["language"])
    init_parser.add_argument("--long-doc-threshold", type=int, default=DEFAULT_CONFIG["long_doc_threshold"])
    init_parser.add_argument("--domain", default=None)

    add_parser = subcommands.add_parser("add", help="Add a file or directory to a Hermes wiki workspace")
    add_parser.add_argument("path")
    add_parser.add_argument("--workspace", default=None)
    add_parser.add_argument("--model", default=None)
    add_parser.add_argument("--provider", default=None)
    add_parser.add_argument("--language", default=None)

    status_parser = subcommands.add_parser("status", help="Show Hermes wiki workspace status")
    status_parser.add_argument("--workspace", default=None)

    list_parser = subcommands.add_parser("list", help="List Hermes wiki documents and concept pages")
    list_parser.add_argument("--workspace", default=None)

    config_parser = subcommands.add_parser("config", help="Show or update Hermes wiki workspace config")
    config_parser.add_argument("--workspace", default=None)
    config_parser.add_argument("--model", default=None)
    config_parser.add_argument("--provider", default=None)
    config_parser.add_argument("--language", default=None)
    config_parser.add_argument("--long-doc-threshold", type=int, default=None)
    config_parser.add_argument("--concept-generation-concurrency", type=int, default=None)

    deps_parser = subcommands.add_parser("deps", help="Inspect or install Hermes wiki runtime dependencies")
    deps_parser.add_argument("--install", choices=install_groups(), default=None)

    subparser.set_defaults(func=handle_wiki_cli)


def handle_wiki_cli(args) -> None:
    try:
        if args.wiki_command == "init":
            output = _run_init(
                args.path,
                args.model,
                args.language,
                args.long_doc_threshold,
                provider=args.provider,
                domain=args.domain,
            )
        elif args.wiki_command == "add":
            output = _run_add(args.path, args.workspace, args.model, args.language, args.provider)
        elif args.wiki_command == "status":
            output = _run_status(args.workspace)
        elif args.wiki_command == "list":
            output = _run_list(args.workspace)
        elif args.wiki_command == "config":
            output = _run_config(
                args.workspace,
                model=args.model,
                provider=args.provider,
                language=args.language,
                long_doc_threshold=args.long_doc_threshold,
                concept_generation_concurrency=args.concept_generation_concurrency,
            )
        elif args.wiki_command == "deps":
            output = _run_deps(args.install)
        else:
            output = "Usage: hermes wiki <init|add|status|list|config|deps>"
    except Exception as exc:
        output = f"Hermes wiki command failed: {exc}"
    print(output)
