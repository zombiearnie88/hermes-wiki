# Domain-Aware Wiki Init Patch Plan

## Goal

Mimic the `LLM_WIKI_SKILL.md` initialization mechanism in Hermes Wiki:

- When creating a new wiki, the agent should ask what domain the wiki covers and ask for a specific answer.
- `wiki/SCHEMA.md` should be customized to that domain.
- Existing Hermes Wiki layout and compiler behavior must remain the source of truth.

## Current State

- `init_workspace()` writes static `DEFAULT_SCHEMA_MD` to `wiki/SCHEMA.md`.
- `init_workspace()` writes static `DEFAULT_AGENTS_MD` to root `AGENTS.md`.
- `compile_short_doc()` and `compile_pageindex_doc()` already read `wiki/SCHEMA.md` at compile time through `get_schema_md()`.
- `DEFAULT_AGENTS_MD` currently duplicates schema-like content instead of acting as agent operating guidance.
- `DEFAULT_SCHEMA_MD` is the correct place for domain, conventions, page thresholds, taxonomy, and update policy.

## Design

Use a deterministic template builder instead of model generation during init.

Rationale:

- Workspace initialization should not depend on Hermes runtime or model availability.
- Domain customization can be tested with simple file assertions.
- The agent can still ask the user before calling `wiki_init`; the tool receives the answer as a `domain` argument.

## Proposed Behavior

For plugin tool usage:

```json
{
  "path": "./my-wiki",
  "domain": "AI safety evaluations for frontier language models"
}
```

For CLI usage:

```bash
hermes wiki init ./my-wiki --domain "AI safety evaluations for frontier language models"
```

For slash command usage:

```text
/wiki-init ./my-wiki --domain "AI safety evaluations for frontier language models"
```

If `domain` is omitted, initialization should still succeed and write a clear placeholder:

```markdown
## Domain
Unspecified. Ask the user to clarify the wiki domain before major ingest.
```

## Patch Steps

### 1. Refactor Schema Builders

File: `hermes_wiki/schema.py`

Add:

```python
def build_schema_md(domain: str | None = None) -> str:
    ...

def build_agents_md() -> str:
    ...
```

Then define:

```python
DEFAULT_SCHEMA_MD = build_schema_md()
DEFAULT_AGENTS_MD = build_agents_md()
```

Keep the generated schema deterministic and ASCII-only.

### 2. Rewrite `DEFAULT_AGENTS_MD` As Operating Guidance

Root `AGENTS.md` should not duplicate the full schema. It should tell agents:

- The authoritative wiki content contract is `wiki/SCHEMA.md`.
- Before wiki work, read `wiki/SCHEMA.md`, `wiki/index.md`, and recent `wiki/log.md`.
- Answer only from wiki content.
- Use `wiki/index.md` to discover summaries and concepts.
- For detailed content, follow summary frontmatter `full_text`.
- For PageIndex documents, use `get_document_structure` and `get_page_content` with tight page ranges.

Remove or soften the `get_image` instruction unless a registered image tool exists.

### 3. Expand `DEFAULT_SCHEMA_MD` With Domain Rules

The schema should include the current Hermes Wiki layout and compiler expectations, plus the useful `LLM_WIKI_SKILL.md` concepts adapted to this repo.

Recommended sections:

- `## Domain`
- `## Directory Structure`
- `## Special Files`
- `## Page Types`
- `## Summary Frontmatter`
- `## PageIndex Summary Rules`
- `## Content Rules`
- `## Tag Taxonomy`
- `## Page Thresholds`
- `## Summary Pages`
- `## Concept Pages`
- `## Index Rules`
- `## Log Rules`
- `## Update Policy`

### Domain-Aware `SCHEMA.md` Template

`build_schema_md(domain)` should render this deterministic template:

```markdown
# Wiki Schema

## Domain
{domain}

## Domain Scope
- In scope: source material, concepts, claims, and relationships directly relevant to {domain}.
- Out of scope: passing mentions, unrelated background, and topics that do not help explain {domain}.
- When unsure, prefer summarizing the source document but do not create new concept pages unless the concept is central.

## Directory Structure
- sources/ - Document content for ingested files. Do not edit directly unless repairing conversion output.
- sources/images/ - Extracted or copied images referenced by source markdown.
- summaries/ - One summary page per source document.
- concepts/ - Cross-document concept pages synthesized over time.
- explorations/ - Saved analyses and ad hoc writeups worth keeping.
- reports/ - Generated reports and maintenance output.

## Special Files
- index.md - Main catalog of documents, concepts, and explorations.
- log.md - Append-only record of ingest operations and maintenance events.

## Page Types
- Summary pages describe one source document.
- PageIndex summary pages describe one long document and point detailed retrieval to PageIndex tools.
- Concept pages synthesize ideas across multiple documents.
- Index page lists pages with short descriptions.
- Log page records operations chronologically.

## Summary Frontmatter
- Short-document summaries use `doc_type: short` and `full_text: sources/{doc_name}.md`.
- PageIndex summaries use `doc_type: pageindex`, `pageindex_id: {doc_name}`, `full_text: pageindex/{doc_name}`, and `page_count`.

## PageIndex Summary Rules
- Include a concise model-generated document overview.
- Include compact page ranges and section titles so agents can choose retrieval ranges.
- Do not include full long-document text in summary pages.
- Mention `get_document_structure("{doc_name}")` and `get_page_content("{doc_name}", "5-8")` retrieval patterns.

## Content Rules
- Use [[wikilinks]] when linking to wiki pages.
- Keep pages focused and easy to scan.
- Do not emit YAML frontmatter in model output. Code manages frontmatter.
- Prefer explicit headings and concise bullets over long prose when possible.
- Ground summaries and concepts in the source material.
- Avoid creating broad generic concept pages unless they are central to {domain}.

## Tag Taxonomy
Define domain-specific tags here before using them.

Suggested starter categories for {domain}:
- core-concept
- method
- system
- dataset
- benchmark
- person
- organization
- finding
- limitation
- open-question

Rule: every tag on a page should appear in this taxonomy. Add new tags here before using them.

## Page Thresholds
- Create a concept page when a concept appears in 2+ sources or is central to one important source.
- Update an existing concept page when a new source adds meaningful information.
- Do not create concept pages for passing mentions or minor details.
- Split long concept pages when they become hard to scan.

## Summary Pages
Each summary page should include:
- What the source is about.
- Main claims, findings, or contributions.
- Important entities and concepts.
- Links to relevant concept pages.

## Concept Pages
Each concept page should include:
- Definition or explanation.
- Why it matters for {domain}.
- Current state of knowledge.
- Open questions, debates, or limitations.
- Related summaries and concepts using [[wikilinks]].

## Index Rules
- Add every ingested summary under `## Documents`.
- Add every concept page under `## Concepts`.
- Keep entries short: wikilink plus one-line description when available.

## Log Rules
- Append every ingest or maintenance operation to `log.md`.
- Keep the log chronological and append-only.

## Update Policy
When new information conflicts with existing content:
1. Check source dates and context.
2. Preserve both claims if the conflict is real.
3. Note uncertainty clearly.
4. Prefer explicit caveats over silently overwriting prior synthesis.
```

Important adaptation:

- Use this repo layout: `raw/`, `wiki/sources/`, `wiki/summaries/`, `wiki/concepts/`, `wiki/explorations/`, `wiki/reports/`, `.hermeskb/`.
- Do not introduce `entities/`, `comparisons/`, `queries/`, or `wiki/AGENTS.md` as v1 runtime requirements.
- Keep "code manages frontmatter; model output should not" because compiler prompts rely on that.

### 4. Add Domain Parameter To Workspace Init

File: `hermes_wiki/workspace.py`

Change:

```python
def init_workspace(..., long_doc_threshold: int) -> WorkspacePaths:
```

to:

```python
def init_workspace(..., long_doc_threshold: int, domain: str | None = None) -> WorkspacePaths:
```

Then write:

```python
paths.schema_path.write_text(build_schema_md(domain), encoding="utf-8")
paths.agents_path.write_text(build_agents_md(), encoding="utf-8")
```

### 5. Add Domain Parameter To Command Surfaces

Files:

- `hermes_wiki/commands.py`
- `hermes_wiki/cli.py`
- `hermes_wiki/tools.py`
- `hermes_wiki/schemas.py`

Add optional `domain` everywhere init arguments are accepted.

Update tool schema description to instruct the agent:

```text
When initializing a new wiki and domain is not already known, ask the user what domain the wiki covers. Ask for a specific answer, then pass it as domain.
```

Do not make `domain` required at the JSON schema level so non-interactive CLI and tests remain compatible.

### 6. Update Bundled Skill Guidance

File: `hermes_wiki/skills/wiki-operator/SKILL.md`

Under initialization guidance, add:

- Resolve the workspace path.
- Ask the user what domain the wiki covers, unless already specified.
- Ask for specificity, for example: `AI safety evals for frontier LLMs`, not just `AI`.
- Call `wiki_init` with `domain`.

This is the closest Hermes-native equivalent to the `LLM_WIKI_SKILL.md` mechanism because the agent handles clarification and the tool performs deterministic file creation.

### 7. Review `get_agents_md()`

File: `hermes_wiki/schema.py`

Current behavior checks `wiki/AGENTS.md`, but init writes root `AGENTS.md` and repo guidance says not to introduce `wiki/AGENTS.md`.

Options:

- If unused, leave it but note it is legacy.
- Prefer changing it to inspect the workspace root if callers need runtime agent guidance.
- Do not create or read `wiki/AGENTS.md` as a new convention.

## Test Plan

Add or update tests in:

- `tests/test_commands.py`
- `tests/test_cli.py`
- `tests/test_tools.py`
- `tests/test_plugin_registration.py`
- optionally `tests/test_schema.py`

Required assertions:

- `commands._run_init(..., domain="...")` creates `wiki/SCHEMA.md` containing the domain.
- Existing `_run_init(...)` without `domain` still works.
- CLI parser accepts `--domain` for `init`.
- Slash command parser accepts `--domain` for `/wiki-init`.
- `wiki_init` tool forwards `domain` to `_run_init`.
- `schemas.WIKI_INIT` exposes a `domain` property.
- Root `AGENTS.md` points agents to `wiki/SCHEMA.md` instead of duplicating the full schema.
- `wiki/SCHEMA.md` keeps PageIndex summary rules and `doc_type` frontmatter rules.

Run:

```bash
pytest
```

## Non-Goals

- Do not call `AIAgent` during `wiki init`.
- Do not import `LLM_WIKI_SKILL.md` at runtime.
- Do not change the workspace layout to the skill's `entities/`, `comparisons/`, or `queries/` layout.
- Do not introduce `wiki/AGENTS.md`.
- Do not make `domain` mandatory for non-interactive initialization.

## Expected Outcome

New wikis get a useful domain-aware `wiki/SCHEMA.md`, agents are instructed to ask for a specific domain before initialization, and schema wording has one authoritative home instead of being duplicated between `DEFAULT_AGENTS_MD` and `DEFAULT_SCHEMA_MD`.
