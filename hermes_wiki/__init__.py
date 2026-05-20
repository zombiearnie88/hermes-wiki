from __future__ import annotations

from pathlib import Path

from . import schemas, tools
from .commands import (
    handle_wiki_config_command,
    handle_wiki_init_command,
    handle_wiki_list_command,
    make_wiki_add_command_handler,
    make_wiki_cli_handler,
    make_wiki_deps_command_handler,
    make_wiki_status_command_handler,
    setup_wiki_cli,
)


def _ctx_has_llm(ctx) -> bool:
    return getattr(ctx, "llm", None) is not None


def _make_wiki_add_tool(ctx):
    async def handler(args: dict, **kwargs) -> str:
        return await tools.wiki_add_async(args, llm=getattr(ctx, "llm", None), **kwargs)

    return handler


def _make_wiki_status_tool(ctx):
    def handler(args: dict, **kwargs) -> str:
        return tools.wiki_status(args, plugin_llm_available=_ctx_has_llm(ctx), **kwargs)

    return handler


def _make_wiki_deps_tool(ctx):
    def handler(args: dict, **kwargs) -> str:
        return tools.wiki_deps(args, plugin_llm_available=_ctx_has_llm(ctx), **kwargs)

    return handler


def register(ctx) -> None:
    wiki_cli_handler = make_wiki_cli_handler(ctx)

    def setup_ctx_wiki_cli(subparser) -> None:
        setup_wiki_cli(subparser)
        subparser.set_defaults(func=wiki_cli_handler)

    ctx.register_tool(
        name="wiki_init",
        toolset="hermes_wiki",
        schema=schemas.WIKI_INIT,
        handler=tools.wiki_init,
        description="Initialize a Hermes wiki workspace.",
    )
    ctx.register_tool(
        name="wiki_add",
        toolset="hermes_wiki",
        schema=schemas.WIKI_ADD,
        handler=_make_wiki_add_tool(ctx),
        is_async=True,
        description="Ingest a file or directory into a Hermes wiki workspace.",
    )
    ctx.register_tool(
        name="wiki_status",
        toolset="hermes_wiki",
        schema=schemas.WIKI_STATUS,
        handler=_make_wiki_status_tool(ctx),
        description="Show Hermes wiki workspace status and capability readiness.",
    )
    ctx.register_tool(
        name="wiki_config",
        toolset="hermes_wiki",
        schema=schemas.WIKI_CONFIG,
        handler=tools.wiki_config,
        description="Show or update a Hermes wiki workspace config.",
    )
    ctx.register_tool(
        name="wiki_list",
        toolset="hermes_wiki",
        schema=schemas.WIKI_LIST,
        handler=tools.wiki_list,
        description="List tracked documents and concept pages in a Hermes wiki workspace.",
    )
    ctx.register_tool(
        name="wiki_deps",
        toolset="hermes_wiki",
        schema=schemas.WIKI_DEPS,
        handler=_make_wiki_deps_tool(ctx),
        description="Inspect or install Hermes wiki runtime dependencies.",
    )
    ctx.register_tool(
        name="get_document_structure",
        toolset="hermes_wiki",
        schema=schemas.GET_DOCUMENT_STRUCTURE,
        handler=tools.get_document_structure,
        description="Return PageIndex structure for a long document.",
    )
    ctx.register_tool(
        name="get_page_content",
        toolset="hermes_wiki",
        schema=schemas.GET_PAGE_CONTENT,
        handler=tools.get_page_content,
        description="Return selected PageIndex page content for a long document.",
    )

    ctx.register_command(
        "wiki-init",
        handler=handle_wiki_init_command,
        description="Initialize a Hermes wiki workspace",
        args_hint="[path] [--model MODEL] [--provider PROVIDER] [--language LANG] [--domain DOMAIN]",
    )
    ctx.register_command(
        "wiki-add",
        handler=make_wiki_add_command_handler(ctx),
        description="Add a file or directory to the wiki workspace",
        args_hint="<path> [--workspace DIR] [--model MODEL] [--provider PROVIDER] [--language LANG]",
    )
    ctx.register_command(
        "wiki-status",
        handler=make_wiki_status_command_handler(ctx),
        description="Show Hermes wiki workspace status",
        args_hint="[--workspace DIR]",
    )
    ctx.register_command(
        "wiki-config",
        handler=handle_wiki_config_command,
        description="Show or update Hermes wiki workspace config",
        args_hint="[--workspace DIR] [--model MODEL] [--provider PROVIDER] [--language LANG] [--long-doc-threshold N]",
    )
    ctx.register_command(
        "wiki-list",
        handler=handle_wiki_list_command,
        description="List Hermes wiki documents and concept pages",
        args_hint="[--workspace DIR]",
    )
    ctx.register_command(
        "wiki-deps",
        handler=make_wiki_deps_command_handler(ctx),
        description="Inspect or install Hermes wiki runtime dependencies",
        args_hint="[--install core|pdf|office|all]",
    )
    ctx.register_cli_command(
        name="wiki",
        help="Manage Hermes wiki workspaces",
        description="Initialize, ingest, and inspect Hermes wiki workspaces",
        setup_fn=setup_ctx_wiki_cli,
        handler_fn=wiki_cli_handler,
    )

    skills_dir = Path(__file__).parent / "skills"
    for child in sorted(skills_dir.iterdir() if skills_dir.exists() else []):
        skill_md = child / "SKILL.md"
        if child.is_dir() and skill_md.exists():
            ctx.register_skill(child.name, skill_md)
