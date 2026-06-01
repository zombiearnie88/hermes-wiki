from __future__ import annotations

import argparse
import sys

from .commands import (
    _run_add,
    _run_config,
    _run_deps,
    _run_get_document_structure,
    _run_get_page_content,
    _run_init,
    _run_list,
    _run_status,
    is_failure_output,
)
from .config import DEFAULT_CONFIG


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hermes-wiki")
    subcommands = parser.add_subparsers(dest="command")

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
    deps_parser.add_argument("--install", choices=["core", "pdf", "office", "all"], default=None)

    structure_parser = subcommands.add_parser(
        "get-document-structure",
        help="Show PageIndex structure for a long document",
    )
    structure_parser.add_argument("--workspace", default=None)
    structure_parser.add_argument("--doc-name", required=True)
    structure_parser.add_argument("--json", action="store_true")

    content_parser = subcommands.add_parser(
        "get-page-content",
        help="Show selected PageIndex page content for a long document",
    )
    content_parser.add_argument("--workspace", default=None)
    content_parser.add_argument("--doc-name", required=True)
    content_parser.add_argument("--pages", required=True)
    content_parser.add_argument("--json", action="store_true")

    return parser


def run_args(args: argparse.Namespace) -> str:
    if args.command == "init":
        return _run_init(
            args.path,
            args.model,
            args.language,
            args.long_doc_threshold,
            provider=args.provider,
            domain=args.domain,
        )
    if args.command == "add":
        return _run_add(args.path, args.workspace, args.model, args.language, args.provider)
    if args.command == "status":
        return _run_status(args.workspace)
    if args.command == "list":
        return _run_list(args.workspace)
    if args.command == "config":
        return _run_config(
            args.workspace,
            model=args.model,
            provider=args.provider,
            language=args.language,
            long_doc_threshold=args.long_doc_threshold,
            concept_generation_concurrency=args.concept_generation_concurrency,
        )
    if args.command == "deps":
        return _run_deps(args.install)
    if args.command == "get-document-structure":
        return _run_get_document_structure(args.workspace, args.doc_name, as_json=args.json)
    if args.command == "get-page-content":
        return _run_get_page_content(args.workspace, args.doc_name, args.pages, as_json=args.json)
    return "Usage: hermes-wiki <init|add|status|list|config|deps|get-document-structure|get-page-content>"


def main(argv: list[str] | None = None) -> int:
    try:
        parser = build_parser()
        args = parser.parse_args(argv)
        output = run_args(args)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(output)
    return 1 if is_failure_output(output) else 0
