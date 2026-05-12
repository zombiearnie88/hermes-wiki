# Wiki Operator Model Patch Plan

## Goal

Update the `wiki-operator` skill so agents configure the workspace model/provider once and let normal ingest calls use `.hermeskb/config.yaml`.

## Why This Patch Is Needed

- The wiki runtime supports persisted model settings in workspace config.
- Docker ChatGPT/Codex sessions also need a separate provider value such as `openai-codex`.
- Passing model values on every `wiki_add` is noisy and can preserve incompatible provider/model strings.

## Current State

- `hermes_wiki/schemas.py` exposes `model` and `provider` parameters for config-aware surfaces.
- `hermes_wiki/tools.py` forwards optional model/provider overrides into the command layer.
- `hermes_wiki/commands.py` and `hermes_wiki/cli.py` accept `--model` and `--provider` for `init`, `add`, and `config`.
- `wiki_status` and `wiki_list` do not need a model argument.
- `/wiki-add` uses workspace config by default and only needs model/provider for one-off overrides.

## Patch Scope

### 1. Update Skill Instructions

File: `hermes_wiki/skills/wiki-operator/SKILL.md`

Update the `## Model Selection` section after `## Preferred Surfaces` with these rules:

- Store generation routing in `.hermeskb/config.yaml` via `wiki_config`.
- Do not pass model/provider to `wiki_add` unless the user explicitly asks for a one-off override.
- For Docker ChatGPT/Codex sessions, use `model: gpt-5.4-mini` and `provider: openai-codex`.
- Do not use `openai/gpt-*` model IDs with `provider: openai-codex`.

### 2. Update Examples in the Skill

File: `hermes_wiki/skills/wiki-operator/SKILL.md`

Adjust command examples so model/provider configuration happens separately from ingest:

```bash
hermes wiki init <path>
hermes wiki config --workspace <path> --model gpt-5.4-mini --provider openai-codex ...
hermes wiki add <path> --workspace <workspace>

hermes-wiki init <path>
hermes-wiki config --workspace <path> --model gpt-5.4-mini --provider openai-codex ...
hermes-wiki add <path> --workspace <workspace>
```

Use `gpt-5.4-mini`/`openai-codex` as the Docker Codex example, not as a universal provider default.

### 3. Fix Slash Usage Text

File: `hermes_wiki/commands.py`

Update the `/wiki-add` usage string so it matches the actual parser surface:

```text
Usage: /wiki-add <path> [--workspace DIR] [--model MODEL] [--provider PROVIDER] [--language LANG]
```

This is a small discoverability fix and keeps the documented skill behavior aligned with the slash command help text.

## Out of Scope

- No runtime model-resolution feature should be added in this patch.
- No change is needed to `wiki_status` or `wiki_list`.
- No change is needed to the core plugin tool schemas unless naming or descriptions are later refined.

## Validation Checklist

1. Read `hermes_wiki/skills/wiki-operator/SKILL.md` and confirm the new section clearly defines config-based model/provider behavior.
2. Confirm skill examples show `wiki_config` for model/provider and plain `wiki_add` for ingest.
3. Run a quick check of `/wiki-init`, `/wiki-add`, and `/wiki-config` usage/help strings in `hermes_wiki/commands.py`.
4. Verify `/wiki-add` usage text now includes optional `--model`, `--provider`, and `--language`.
5. Confirm no unrelated command behavior changed.

## Notes

- This patch is primarily documentation and operator-guidance work.
- The runtime should use persisted workspace config by default and reserve per-call model/provider arguments for explicit overrides.
