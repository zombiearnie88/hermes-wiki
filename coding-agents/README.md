# Coding Agents

This directory contains reusable agent assets for operating Hermes Wiki from OpenCode and Codex.

## Included

- OpenCode skill source: `coding-agents/opencode/skills/hermes-wiki/`
- Codex skill source: `coding-agents/codex/skills/hermes-wiki/`
- Installer script: `coding-agents/install.sh`

## Quick Install Script

Use the installer when you want the copy and config-merge steps handled for you.

Examples:

```bash
./coding-agents/install.sh opencode repo /path/to/other-repo
./coding-agents/install.sh codex repo /path/to/other-repo
./coding-agents/install.sh all repo /path/to/other-repo
./coding-agents/install.sh opencode global
./coding-agents/install.sh codex global
./coding-agents/install.sh all global
```

The script:

- copies the skill files into the target location
- merges OpenCode `skills.paths` instead of overwriting `opencode.json`
- prints a restart reminder when done

For Codex installs, the script uses native Codex skill locations instead of plugins:

```text
.agents/skills/hermes-wiki/
```

## Install In Another OpenCode Repo

Copy the skill folder into the target repository:

```bash
mkdir -p /path/to/other-repo/.opencode/skills
cp -R ./coding-agents/opencode/skills/hermes-wiki /path/to/other-repo/.opencode/skills/
```

Then create or update `/path/to/other-repo/.opencode/opencode.json`:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "skills": {
    "paths": [
      "./.opencode/skills"
    ]
  }
}
```

If the target repo already has an `opencode.json`, merge the `skills.paths` entry instead of replacing the whole file.

After that:

1. Open the target repository in OpenCode.
2. Restart OpenCode so it reloads the config and skill files.
3. Ask OpenCode to use `hermes-wiki` or give it a Hermes Wiki task.

## Install In Global OpenCode Config

If you want the skill available across many repos, copy it to your global OpenCode skill directory:

```bash
mkdir -p ~/.config/opencode/skills
cp -R ./coding-agents/opencode/skills/hermes-wiki ~/.config/opencode/skills/
```

Then create or update `~/.config/opencode/opencode.json`:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "skills": {
    "paths": [
      "~/.config/opencode/skills"
    ]
  }
}
```

Restart OpenCode after saving the config.

## Install In Another Codex Repo

Copy the skill folder into the target repository:

```bash
mkdir -p /path/to/other-repo/.agents/skills
cp -R ./coding-agents/codex/skills/hermes-wiki /path/to/other-repo/.agents/skills/
```

After that:

1. Open the target repository in Codex.
2. Restart Codex so it rescans `.agents/skills`.
3. Start a new thread and invoke `hermes-wiki` explicitly or ask for a Hermes Wiki operation.

## Install In Global Codex Config

If you want the skill available outside a single repo, copy it into your local Codex skill area:

```bash
mkdir -p ~/.agents/skills
cp -R ./coding-agents/codex/skills/hermes-wiki ~/.agents/skills/
```

Restart Codex after copying the skill.

## Current Repo Codex Install

This repository already includes a repo-local Codex skill at:

```text
.agents/skills/hermes-wiki/SKILL.md
```

So for this repo, you do not need plugins or marketplaces. Restart Codex and use the skill directly.

## Requirements

These agent assets do not replace Hermes itself. They expect a working local Hermes Wiki setup.

Required:

- `hermes` installed on the machine
- `hermes-wiki` installed and enabled in Hermes
- a usable Hermes runtime for commands such as:

```bash
hermes wiki status --workspace <path>
hermes wiki add <path> --workspace <workspace>
```

## Notes

- The OpenCode and Codex assets are operator wrappers around `hermes wiki ...` commands.
- They do not re-implement summary or concept generation.
- Do not use standalone `hermes-wiki add`; use `hermes wiki add` through Hermes.
- If OpenCode already has config in the target repo or user profile, merge these entries carefully instead of overwriting unrelated settings.
