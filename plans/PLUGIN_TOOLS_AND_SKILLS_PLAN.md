# Hermes Wiki Tools And Skills Plan

## Goal

Add first-class Hermes plugin tools to `hermes-wiki` while preserving the existing slash-command and CLI workflow, and make the bundled skill explicitly loadable, portable, and documented.

## Desired End State

- Hermes can load `hermes-wiki` as a general plugin through the existing pip entry point.
- The plugin registers real tools in `register(ctx)` in addition to the current slash commands and CLI command tree.
- The plugin continues to use the existing command implementation as the shared business-logic layer.
- The bundled skill remains plugin-scoped and is loadable as `hermes-wiki:wiki-operator`.
- The skill stops depending on one local Docker path layout and defaults to public plugin surfaces first.
- Docs and tests cover the tool-registration path, the enablement step, and the plugin skill load path.

## Locked Decisions

- Keep the current five-surface command model instead of introducing a single umbrella `wiki_manage` tool.
- Reuse `hermes_wiki.commands` as the core implementation layer.
- Keep existing slash commands:
  - `/wiki-init`
  - `/wiki-add`
  - `/wiki-status`
  - `/wiki-config`
  - `/wiki-list`
- Keep the existing Hermes CLI subcommand tree:
  - `hermes wiki init`
  - `hermes wiki add`
  - `hermes wiki status`
  - `hermes wiki config`
  - `hermes wiki list`
- Add tools that mirror those same operations.
- Keep plugin skill registration via `ctx.register_skill(...)`.
- Do not move business logic into the skill. The skill should orchestrate the plugin surfaces, not replace them.

## Tool Surface

Register these Hermes tools under the `hermes_wiki` toolset:

- `wiki_init`
- `wiki_add`
- `wiki_status`
- `wiki_config`
- `wiki_list`

Why this shape:

- It matches the current command structure and avoids a broad refactor.
- It gives the model narrow, easy-to-select tools with clear intent.
- It keeps slash commands, CLI commands, and tools aligned around one implementation.

## File Changes

### New files

- `hermes_wiki/schemas.py`
  - tool schemas the model reads
- `hermes_wiki/tools.py`
  - JSON-returning Hermes tool handlers

### Updated files

- `hermes_wiki/__init__.py`
  - register the five tools
  - keep existing slash-command registration
  - keep existing CLI command registration
  - keep skill registration loop
- `hermes_wiki/commands.py`
  - optionally add a small shared helper for success or failure classification so CLI and tool wrappers agree
- `hermes_wiki/cli.py`
  - reuse shared failure classification helper if extracted
- `hermes_wiki/skills/wiki-operator/SKILL.md`
  - add proper Hermes skill frontmatter
  - rewrite instructions to prefer plugin surfaces over Docker-specific fallbacks
- `README.md`
  - document plugin enablement after install
  - document explicit plugin skill loading
- `hermes_wiki/plugin.yaml`
  - optionally declare `provides_tools` for directory-plugin parity and clearer manifest metadata

## Tool Schema Plan

Each tool schema should include:

- a precise description of when to use the tool
- a minimal JSON schema for arguments
- required fields only where they are truly required

### `wiki_init`

Arguments:

- `path`: string, optional, defaults to `.`
- `model`: string, optional
- `language`: string, optional
- `long_doc_threshold`: integer, optional

### `wiki_add`

Arguments:

- `path`: string, required
- `workspace`: string, optional
- `model`: string, optional
- `language`: string, optional

### `wiki_status`

Arguments:

- `workspace`: string, optional

### `wiki_config`

Arguments:

- `workspace`: string, optional
- `model`: string, optional
- `language`: string, optional
- `long_doc_threshold`: integer, optional

### `wiki_list`

Arguments:

- `workspace`: string, optional

## Tool Handler Plan

Each handler in `hermes_wiki/tools.py` should follow Hermes tool rules:

- signature: `def handler(args: dict, **kwargs) -> str`
- always return a JSON string
- never raise uncaught exceptions
- delegate all real work to the existing `_run_*` command functions

Recommended response envelope:

```json
{"ok": true, "output": "..."}
```

Failure envelope:

```json
{"ok": false, "error": "..."}
```

Optional richer fields if useful:

- `action`
- `workspace`
- `path`

Do not build a second formatting layer for the same underlying operation. The tool should preserve the existing user-facing output text inside `output` when possible.

## Shared Logic Plan

The command layer already contains the canonical operations:

- `_run_init(...)`
- `_run_add(...)`
- `_run_status(...)`
- `_run_config(...)`
- `_run_list(...)`

The new tool handlers should call those functions directly.

Minimal refactor only:

- keep `commands.py` as the source of truth for operation behavior
- optionally extract a small helper that decides whether a returned text payload represents failure
- avoid moving parsing or workspace logic into `tools.py`

## Registration Plan

Update `hermes_wiki/__init__.py` so `register(ctx)` does all of the following:

- register five tools with `ctx.register_tool(...)`
- register the existing five slash commands with `ctx.register_command(...)`
- register the existing `wiki` CLI command tree with `ctx.register_cli_command(...)`
- register bundled skills from `hermes_wiki/skills/*/SKILL.md`

Recommended `ctx.register_tool(...)` fields:

- `name`: one of the five tool names
- `toolset`: `hermes_wiki`
- `schema`: from `hermes_wiki.schemas`
- `handler`: from `hermes_wiki.tools`
- `description`: short explicit summary

## Skill Plan

The bundled skill should remain plugin-scoped and explicit-load only.

Qualified skill name:

- `hermes-wiki:wiki-operator`

Important behavior to document:

- plugin skills are not part of Hermes' normal available-skills index
- plugin skills do not override bare skill names
- users or agents must explicitly load the namespaced skill

### `wiki-operator` content changes

Rewrite the skill to follow standard Hermes skill structure:

- YAML frontmatter
- `name`
- `description`
- optional metadata tags
- clear "when to use"
- clear primary command path
- lightweight fallback section
- verification guidance

### Preferred execution order inside the skill

1. Use slash commands when the session supports them.
2. Use `hermes wiki ...` subcommands when terminal access is the better path.
3. Use standalone `hermes-wiki ...` only as a development fallback.
4. Avoid private `_run_*` helper calls except as repo-local emergency instructions.

### Portability rules for the skill

- remove `/opt/hermes-wiki` as the default path
- remove `/workspace/...` as the default workspace example
- if Docker-specific examples remain, mark them clearly as repo-local examples
- prefer placeholders and public command surfaces over hardcoded mount assumptions

## Documentation Plan

### README updates

Document the real installation flow:

```bash
pip install -e .
hermes plugins enable hermes-wiki
```

Document skill loading:

```python
skill_view("hermes-wiki:wiki-operator")
```

Document key behavior:

- plugin discovery via `hermes_agent.plugins`
- plugin enablement is still required for general plugins
- bundled plugin skills are explicit-load only

### Optional manifest update

If `hermes_wiki/plugin.yaml` is the directory-plugin source of truth, ensure it declares tool metadata clearly:

```yaml
provides_tools:
  - wiki_init
  - wiki_add
  - wiki_status
  - wiki_config
  - wiki_list
```

## Test Plan

Add focused tests for registration and tool wrappers.

### Registration tests

- `register(ctx)` registers five tools
- `register(ctx)` registers five slash commands
- `register(ctx)` registers the `wiki` CLI command tree
- `register(ctx)` registers `wiki-operator` as a plugin skill

Use a fake context object that records calls.

### Tool handler tests

- each tool handler returns valid JSON
- success path returns `ok: true`
- failure path returns `ok: false`
- handlers do not raise on invalid input
- `wiki_add` preserves current behavior for unsupported types and missing paths

### Skill-related tests

- verify the bundled skill file exists at the expected packaged path
- optionally assert the skill frontmatter remains present

## Implementation Order

1. Add `hermes_wiki/schemas.py`.
2. Add `hermes_wiki/tools.py`.
3. Update `hermes_wiki/__init__.py` to register the five tools.
4. Add registration tests with a fake plugin context.
5. Add tool-handler JSON wrapper tests.
6. Rewrite `hermes_wiki/skills/wiki-operator/SKILL.md` with standard metadata and portable instructions.
7. Update `README.md` for enablement and skill loading.
8. Optionally update `hermes_wiki/plugin.yaml` to declare `provides_tools`.

## Non-Goals

- Do not replace slash commands with tools.
- Do not collapse all operations into one multi-action tool.
- Do not move wiki business logic into the skill.
- Do not introduce long-doc support as part of this work.
- Do not add a custom Hermes model-provider plugin.

## Definition Of Done

- Hermes loads `hermes-wiki` and exposes five real tools.
- Existing slash commands and CLI commands still work.
- Tool handlers are thin JSON wrappers around existing command logic.
- The bundled skill is loadable as `hermes-wiki:wiki-operator`.
- The skill uses Hermes-standard metadata and portable instructions.
- README explains both plugin enablement and explicit skill loading.
- Tests cover registration and tool-handler behavior.
