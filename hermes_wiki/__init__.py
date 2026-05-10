from __future__ import annotations

from hermes_wiki.commands import (
    handle_wiki_add_command,
    handle_wiki_cli,
    handle_wiki_init_command,
    handle_wiki_status_command,
    setup_wiki_cli,
)


def register(ctx) -> None:
    ctx.register_command(
        "wiki-init",
        handler=handle_wiki_init_command,
        description="Initialize a Hermes wiki workspace",
        args_hint="[path] [--model MODEL] [--language LANG]",
    )
    ctx.register_command(
        "wiki-add",
        handler=handle_wiki_add_command,
        description="Add a file or directory to the wiki workspace",
        args_hint="<path> [--workspace DIR]",
    )
    ctx.register_command(
        "wiki-status",
        handler=handle_wiki_status_command,
        description="Show Hermes wiki workspace status",
        args_hint="[--workspace DIR]",
    )
    ctx.register_cli_command(
        name="wiki",
        help="Manage Hermes wiki workspaces",
        description="Initialize, ingest, and inspect Hermes wiki workspaces",
        setup_fn=setup_wiki_cli,
        handler_fn=handle_wiki_cli,
    )
