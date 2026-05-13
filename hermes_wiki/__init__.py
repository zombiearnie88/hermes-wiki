from __future__ import annotations

from pathlib import Path

from . import schemas, tools
from .commands import (
    handle_wiki_add_command,
    handle_wiki_cli,
    handle_wiki_config_command,
    handle_wiki_deps_command,
    handle_wiki_init_command,
    handle_wiki_list_command,
    handle_wiki_status_command,
    setup_wiki_cli,
)


def register(ctx) -> None:
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
        handler=tools.wiki_add,
        description="Ingest a file or directory into a Hermes wiki workspace.",
    )
    ctx.register_tool(
        name="wiki_status",
        toolset="hermes_wiki",
        schema=schemas.WIKI_STATUS,
        handler=tools.wiki_status,
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
        handler=tools.wiki_deps,
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
        handler=handle_wiki_add_command,
        description="Add a file or directory to the wiki workspace",
        args_hint="<path> [--workspace DIR] [--model MODEL] [--provider PROVIDER] [--language LANG]",
    )
    ctx.register_command(
        "wiki-status",
        handler=handle_wiki_status_command,
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
        handler=handle_wiki_deps_command,
        description="Inspect or install Hermes wiki runtime dependencies",
        args_hint="[--install core|pdf|office|all]",
    )
    ctx.register_cli_command(
        name="wiki",
        help="Manage Hermes wiki workspaces",
        description="Initialize, ingest, and inspect Hermes wiki workspaces",
        setup_fn=setup_wiki_cli,
        handler_fn=handle_wiki_cli,
    )

    skills_dir = Path(__file__).parent / "skills"
    for child in sorted(skills_dir.iterdir() if skills_dir.exists() else []):
        skill_md = child / "SKILL.md"
        if child.is_dir() and skill_md.exists():
            ctx.register_skill(child.name, skill_md)
