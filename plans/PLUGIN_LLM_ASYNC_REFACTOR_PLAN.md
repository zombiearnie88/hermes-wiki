# Plugin LLM Async Refactor Plan

## Goal

Refactor Hermes Wiki generation from direct `run_agent.AIAgent` spawning to Hermes plugin LLM access through `ctx.llm`.

The target behavior is:

- use workspace `.hermeskb/config.yaml` `model` and `provider` as the generation route
- call `ctx.llm.acomplete()` for compiler generation
- pass `model=` and `provider=` explicitly to `ctx.llm`
- use bounded async concept generation with `asyncio.Semaphore`
- keep concept file writes, backlinks, related links, and index updates serial
- remove the direct `run_agent.AIAgent` runtime dependency

## Source References

- Hermes docs: `https://hermes-agent.nousresearch.com/docs/developer-guide/plugin-llm-access`
- Async plugin example: `https://github.com/NousResearch/hermes-example-plugins/tree/main/plugin-llm-async-example`
- Donor compiler: `code-donor/OpenKB/openkb/agent/compiler.py`
- Current runtime adapter: `hermes_wiki/runtime.py`
- Current compiler: `hermes_wiki/compiler.py`

## Design Decisions

### Workspace Routing Remains Source Of Truth

Hermes Wiki should continue to read `model` and `provider` from `.hermeskb/config.yaml` during `wiki add`.

This means generation calls should use:

```python
result = await ctx.llm.acomplete(
    messages=messages,
    provider=provider,
    model=model,
    temperature=0.0,
    purpose=purpose,
)
```

For any remaining synchronous helper:

```python
result = ctx.llm.complete(
    messages=messages,
    provider=provider,
    model=model,
    temperature=0.0,
    purpose=purpose,
)
```

### Trust Gate Is Required For Explicit Routing

Hermes allows plugins to pass `provider=` and `model=`, but those overrides are fail-closed unless the operator opts in.

Document required config:

```yaml
plugins:
  entries:
    hermes-wiki:
      llm:
        allow_provider_override: true
        allow_model_override: true
        allowed_providers:
          - openai-codex
        allowed_models:
          - gpt-5.4-mini
```

Development setups may use `allowed_providers: ["*"]` and `allowed_models: ["*"]`, but user-facing docs should prefer exact values.

### Async First

Use `ctx.llm.acomplete()` for compiler calls because concept generation is naturally fan-out work.

The async example registers an async slash command by binding `ctx` inside `register(ctx)`:

```python
def _make_handler(ctx):
    async def handler(raw_args: str) -> str:
        result = await ctx.llm.acomplete(...)
        return result.text
    return handler

def register(ctx):
    ctx.register_command(name="example", handler=_make_handler(ctx))
```

Hermes tools also support async handlers with `is_async=True`, so `wiki_add` should be registered as an async ctx-bound tool handler.

### Keep Prompt Flow Stable

Preserve the current OpenKB-style message prefix:

```text
system -> user summary request -> assistant summary -> user concept task
```

The runtime adapter should build OpenAI-style messages and return the existing `GenerationResult` shape to minimize compiler churn.

## Runtime Adapter

Replace the current `AIAgent` adapter with an async plugin LLM adapter.

Suggested shape:

```python
async def agenerate_conversation(
    llm,
    model: str,
    provider: str | None,
    user_message: str,
    *,
    system_message: str | None = None,
    conversation_history: list[dict] | None = None,
    purpose: str | None = None,
) -> GenerationResult:
    messages = [dict(message) for message in conversation_history or []]
    if not messages and system_message:
        messages.append({"role": "system", "content": system_message})
    messages.append({"role": "user", "content": user_message})

    result = await llm.acomplete(
        messages=messages,
        provider=provider,
        model=model,
        temperature=0.0,
        purpose=purpose,
    )
    text = (result.text or "").strip()
    if not text:
        raise HermesRuntimeError("Hermes plugin LLM returned an empty response.")
    return GenerationResult(
        final_response=text,
        messages=[*messages, {"role": "assistant", "content": text}],
    )
```

Error handling should wrap provider failures, timeouts, and trust-gate failures as `HermesRuntimeError` with actionable text.

If a `provider/model` trust failure occurs, include a short hint that `plugins.entries.hermes-wiki.llm.allow_provider_override` and `allow_model_override` must be enabled for workspace routing.

## Compiler Pipeline

### Summary Generation

Keep single-call behavior.

Inputs:

- `llm`
- `model`
- `provider`
- `system_prompt`
- `summary_user`

Call:

```python
summary_result = await _agenerate_conversation(
    llm,
    model,
    provider,
    summary_user,
    system_message=system_prompt,
    purpose=f"wiki.summary.{doc_name}",
)
```

Parse JSON and write summary as today.

### Concept Plan

Keep single-call behavior.

Build immutable base history:

```python
base_history = [
    {"role": "system", "content": system_prompt},
    {"role": "user", "content": summary_user},
    {"role": "assistant", "content": summary},
]
```

Call concept planning with the same prefix:

```python
plan_result = await _agenerate_conversation(
    llm,
    model,
    provider,
    plan_user,
    conversation_history=base_history,
    purpose=f"wiki.concepts.plan.{doc_name}",
)
```

Keep current JSON parsing and fallback behavior.

### Concept Page Generation

Convert concept generation from `ThreadPoolExecutor` to `asyncio.Semaphore` and `asyncio.gather()`.

Suggested shape:

```python
semaphore = asyncio.Semaphore(max_concurrency)

async def run_task(task: ConceptGenerationTask) -> ConceptGenerationResult:
    async with semaphore:
        return await _agenerate_concept_task(
            llm,
            task,
            doc_name=doc_name,
            model=model,
            provider=provider,
            base_history=base_history,
        )

results = await asyncio.gather(
    *(run_task(task) for task in tasks),
    return_exceptions=True,
)
```

Rules:

- preserve task ordering when consuming `results`
- log or collect individual concept failures
- if all concepts fail with the same runtime/trust error, raise that error
- otherwise skip failed concepts and continue
- do not write concept files inside concurrent tasks

### Serial Writes

After all LLM tasks finish, perform code-only mutations serially:

- `_write_concept()` for each successful create/update result
- `_add_related_link()` for related concepts
- `_backlink_summary()`
- `_backlink_concepts()`
- `_update_index()`

This mirrors OpenKB while avoiding file-write races.

## PageIndex Pipeline

Refactor PageIndex generation to accept the same plugin LLM adapter.

Affected functions:

- `pageindex_generate_text()` -> `pageindex_generate_text_async()`
- `pageindex_generate_json()` -> `pageindex_generate_json_async()` if needed
- `build_pageindex()` -> `build_pageindex_async()`
- `build_or_load_pageindex()` -> `build_or_load_pageindex_async()`

Initial implementation can keep PageIndex node summaries sequential to reduce patch size.

Future optimization can add a separate bounded semaphore for PageIndex node summary generation.

## Command And Tool Wiring

### Plugin Tool Registration

Register `wiki_add` with an async ctx-bound handler:

```python
def _make_wiki_add_tool(ctx):
    async def handler(args: dict, **kwargs) -> str:
        return await tools.wiki_add_async(args, llm=ctx.llm, **kwargs)
    return handler

ctx.register_tool(
    name="wiki_add",
    toolset="hermes_wiki",
    schema=schemas.WIKI_ADD,
    handler=_make_wiki_add_tool(ctx),
    is_async=True,
    description="Ingest a file or directory into a Hermes wiki workspace.",
)
```

Other non-generation tools can remain synchronous.

### Slash Command Registration

Register `/wiki-add` with an async ctx-bound handler:

```python
ctx.register_command(
    "wiki-add",
    handler=make_wiki_add_command_handler(ctx),
    description="Add a file or directory to the wiki workspace",
    args_hint="<path> [--workspace DIR] [--model MODEL] [--provider PROVIDER] [--language LANG]",
)
```

The handler should parse arguments exactly as today, then call the async add pipeline with `ctx.llm`.

### Plugin CLI Registration

The `ctx.register_cli_command()` handler is synchronous in current docs. Keep it synchronous and bridge into the async add pipeline with a runtime helper.

This path still has plugin `ctx.llm` because the handler can be registered as a closure around `ctx`.

### Standalone CLI

The standalone `hermes-wiki` executable has no plugin context and therefore no `ctx.llm`.

For generation commands:

- `hermes-wiki add` should fail clearly with a message that generation requires Hermes plugin runtime LLM access
- non-generation commands like `init`, `status`, `list`, `config`, and `deps` can continue to work

Do not add a fallback to direct `AIAgent` or LiteLLM.

## Dependency And Status Changes

Remove `run_agent` probing from `hermes_wiki/deps.py`.

Generation readiness should become context-sensitive:

- in plugin runtime with `ctx.llm`: generation can run if `json-repair` is installed
- outside plugin runtime: generation is unavailable because `ctx.llm` is unavailable

Suggested status wording:

```text
summary and concept generation: ready (plugin LLM access + json-repair)
```

Standalone status can report:

```text
summary and concept generation: blocked (plugin LLM access unavailable outside Hermes plugin runtime)
```

## Affected Files

Runtime and compiler:

- `hermes_wiki/runtime.py`
- `hermes_wiki/compiler.py`
- `hermes_wiki/pageindex/prompts.py`
- `hermes_wiki/pageindex/builder.py`

Command and plugin surfaces:

- `hermes_wiki/__init__.py`
- `hermes_wiki/tools.py`
- `hermes_wiki/commands.py`
- `hermes_wiki/cli.py`

Config, deps, docs, and guidance:

- `hermes_wiki/deps.py`
- `hermes_wiki/schemas.py`
- `README.md`
- `AGENTS.md`
- `hermes_wiki/skills/wiki-operator/SKILL.md`

Tests:

- `tests/test_runtime.py`
- `tests/test_compiler.py`
- `tests/test_pageindex_runtime.py`
- `tests/test_commands.py`
- `tests/test_tools.py`
- `tests/test_cli.py`
- `tests/test_plugin_registration.py`

## Test Plan

### Runtime Tests

- fake `ctx.llm.acomplete()` result object
- assert `messages` shape is correct
- assert `provider` and `model` are passed through
- assert `temperature=0.0`
- assert `purpose` is passed through
- assert empty response raises `HermesRuntimeError`
- assert trust-gate failures include config guidance

### Compiler Tests

- summary call receives system prompt and document content
- concept plan receives base history with parsed summary
- concept create/update calls receive the same base history
- concept generation uses bounded async fan-out
- writes happen after generation results are collected
- failures in one concept task do not prevent successful concept writes
- all-identical runtime failures are re-raised
- related links, backlinks, and index updates remain serial and correct

### PageIndex Tests

- PageIndex text generation passes `llm`, `model`, and `provider`
- PageIndex summaries preserve current prompt behavior
- PageIndex state writes remain unchanged

### Surface Tests

- `wiki_add` tool is registered with `is_async=True`
- `/wiki-add` command handler is async and ctx-bound
- plugin CLI handler uses ctx-bound LLM access
- standalone CLI `add` fails clearly without plugin LLM access
- non-generation commands still work standalone

### Dependency Tests

- remove `run_agent` expectations
- generation readiness depends on `json-repair` plus plugin LLM availability
- repair suggestions no longer mention installing Hermes as a Python library for `AIAgent`

## Verification Commands

Targeted tests first:

```bash
python -m pytest tests/test_runtime.py tests/test_compiler.py tests/test_pageindex_runtime.py
```

Then command/tool tests:

```bash
python -m pytest tests/test_commands.py tests/test_tools.py tests/test_cli.py tests/test_plugin_registration.py
```

Then full suite:

```bash
python -m pytest
```

If plugin Python code changes are deployed into the local Docker runtime, recreate containers so plugin registration and imports refresh:

```bash
docker compose -f docker/docker-compose.yml up -d --force-recreate hermes-agent hermes-webui
```

## Risks And Mitigations

### Trust Gate Misconfiguration

Risk: workspace `model`/`provider` calls fail because Hermes denies overrides.

Mitigation: catch trust errors and print exact `plugins.entries.hermes-wiki.llm` config guidance.

### Async Bridging Differences

Risk: slash commands, tools, and plugin CLI handlers have different async support.

Mitigation: use documented async slash command behavior, `is_async=True` for tools, and a small sync bridge only for CLI handlers.

### Concurrent Cost And Rate Limits

Risk: concept generation fan-out increases token spend and provider rate-limit pressure.

Mitigation: keep bounded `concept_generation_concurrency`, clamp values to `1..8`, and preserve serial writes.

### Standalone CLI Regression

Risk: users expect `hermes-wiki add` to generate outside Hermes.

Mitigation: fail clearly for generation commands and keep non-generation commands working.

## Deferred Work

- switch JSON-returning calls to `ctx.llm.acomplete_structured()` with explicit schemas
- add separate PageIndex node-summary concurrency
- surface token usage and provider/model attribution in operation logs
- add optional `allowed_models`/`allowed_providers` helper output to `wiki status`
