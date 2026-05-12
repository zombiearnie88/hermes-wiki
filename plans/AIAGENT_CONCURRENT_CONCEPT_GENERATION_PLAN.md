# AIAgent Concurrent Concept Generation Plan

## Goal

Add an OpenKB-style bounded concurrency mechanism for concept page generation while keeping Hermes-native `AIAgent` isolation rules intact.

The target behavior is:

- summary generation remains single-call and deterministic
- concept planning remains single-call and deterministic
- concept create/update LLM calls can run concurrently
- concept file writes, backlink updates, and index updates remain serial

## Background

OpenKB uses `asyncio.Semaphore` around concurrent LiteLLM calls after the concept plan is produced. That works because the donor compiler calls low-level async completion primitives directly.

Hermes Wiki uses `AIAgent.run_conversation()` through `hermes_wiki.runtime.generate_conversation()`. The Hermes batch-processing guidance recommends a different shape: create a fresh `AIAgent` per thread or task and run those isolated agent instances in a bounded executor.

This means the concurrency mechanism should mirror OpenKB at the pipeline level, not at the object-sharing level.

## Current State

`hermes_wiki/runtime.py` already creates a fresh `AIAgent` per generation call with the required isolation flags:

- `quiet_mode=True`
- `skip_memory=True`
- `skip_context_files=True`
- `enabled_toolsets=[]`
- `max_iterations=1`

`hermes_wiki/compiler.py` already builds a reusable `base_history` for concept planning and concept generation:

```python
base_history = [
    {"role": "system", "content": system_prompt},
    {"role": "user", "content": summary_user},
    {"role": "assistant", "content": summary},
]
```

Concept create/update calls currently loop sequentially, then the compiler performs code-only related-link, backlink, and index updates.

## Design Decision

Use `concurrent.futures.ThreadPoolExecutor` for the initial implementation.

Reasons:

- `AIAgent.run_conversation()` is synchronous in the current runtime adapter.
- Hermes docs show `ThreadPoolExecutor` for custom batch processing.
- It avoids introducing an async public compiler API or nested event-loop handling in command paths.
- It keeps the patch smaller than converting the compiler back to `asyncio`.

Do not use Hermes `batch_runner.py` as a subprocess. That tool is useful for standalone JSONL prompt batches, but the compiler needs in-process access to parsed plans, existing concept page bodies, write helpers, and index state.

## Configuration

Add a workspace config key:

```yaml
concept_generation_concurrency: 1
```

Initial default should be `1` to preserve current v1 behavior. Users can opt in by setting a value greater than `1`.

Clamp runtime values to a small safe range:

- minimum: `1`
- suggested maximum: `8`
- recommended opt-in value: `3`

Rationale:

- `AIAgent` instances are heavier than raw provider completion calls.
- Providers may rate-limit concurrent requests.
- A conservative default avoids surprising cost and quota changes.

The implementation can later raise the default after smoke testing in Hermes runtime environments.

## Pipeline

### Step 1: Generate Summary

No change.

Call `_generate_conversation()` once with `system_message=system_prompt`, parse JSON, and write `wiki/summaries/{doc_name}.md`.

### Step 2: Generate Concept Plan

No concurrency.

Call `_generate_conversation()` once with `conversation_history=base_history`, parse the `create`, `update`, and `related` arrays, and normalize invalid shapes as today.

### Step 3: Prepare Concept Tasks

Convert plan entries into explicit in-memory tasks before dispatch.

Suggested internal shape:

```python
@dataclass(frozen=True)
class ConceptGenerationTask:
    action: str
    name: str
    safe_name: str
    title: str
    user_message: str
```

For create tasks:

- require a dict with `name`
- sanitize `name` with `_sanitize_concept_name()`
- build `_CONCEPT_PAGE_USER`
- skip duplicate sanitized slugs

For update tasks:

- require a dict with `name`
- sanitize `name` with `_sanitize_concept_name()`
- read the existing concept body before dispatch
- build `_CONCEPT_UPDATE_USER`
- skip duplicate sanitized slugs already used by create tasks

Related-only items stay code-only and should not enter the executor.

### Step 4: Run Bounded Concurrent Generation

Suggested helper:

```python
def _generate_concept_task(
    task: ConceptGenerationTask,
    *,
    doc_name: str,
    model: str,
    provider: str | None,
    base_history: list[dict],
) -> ConceptGenerationResult:
    result = _generate_conversation(
        model,
        provider,
        task.user_message,
        conversation_history=base_history,
        task_id=f"wiki:{doc_name}:concept:{task.action}:{task.safe_name}",
    )
    ...
```

Use a fresh `AIAgent` indirectly through `_generate_conversation()` for every task. Never share an `AIAgent` instance between workers.

Suggested executor shape:

```python
with ThreadPoolExecutor(max_workers=max_concurrency) as executor:
    futures = [executor.submit(_generate_concept_task, task, ...) for task in tasks]
    for future in futures:
        ...
```

Use the submitted task order when collecting results so index ordering remains deterministic. If a future raises, skip that concept and continue compiling the rest of the document.

### Step 5: Serial Writes And Index Updates

After all LLM futures resolve, perform writes in one thread:

- call `_write_concept()` for each successful create/update result
- collect `concept_names` and `concept_briefs_map`
- apply `_add_related_link()` for related items
- call `_backlink_summary()` and `_backlink_concepts()` once
- call `_update_index()` once
- return `CompileResult`

This keeps the file-write behavior close to today and avoids races between workers writing the same wiki files.

## Failure Handling

Concept generation failure should be isolated per concept.

Rules:

- if one concept worker raises, log or collect the error and continue with other concept results
- if response JSON parsing fails, keep current fallback behavior and write the raw response as page content
- if the concept plan itself fails to parse, keep current behavior and update only the document index entry
- do not fail the entire document compile because one concept page fails unless every concept task fails due to the same runtime setup error

For user-facing output, avoid noisy per-thread progress. The existing command result can report created, updated, and related counts. A later enhancement can expose skipped concept counts.

## Prompt Cache Behavior

Each worker should receive the same immutable `base_history` content:

```text
system -> user full-document summary request -> assistant summary -> user concept task
```

`generate_conversation()` already copies `conversation_history`, so workers should not mutate the shared list. This preserves the cache-friendly prefix from the run-conversation compiler plan while still using isolated agents.

## Tests

Add targeted tests before enabling a default greater than `1`.

### Config Tests

- default config includes `concept_generation_concurrency: 1`
- invalid or missing values fall back to `1`
- values below `1` clamp to `1`
- values above the maximum clamp to the maximum

### Compiler Tests

- multiple create items call `_generate_conversation()` with unique `task_id` values
- update items include the existing concept body in each task prompt
- concept writes happen after generation results are collected
- returned `CompileResult` counts successful create/update tasks only
- duplicate sanitized slugs are generated at most once
- related links, backlinks, and index updates remain correct
- a failing concept generation future does not prevent successful concept pages from being written

### Runtime Isolation Tests

- the runtime helper still constructs a new `AIAgent` per call
- `conversation_history` is copied before passing into `run_conversation()`
- `quiet_mode`, `skip_memory`, `skip_context_files`, `enabled_toolsets`, and `max_iterations` remain unchanged

## Verification

Run targeted tests:

```bash
python -m pytest tests/test_runtime.py tests/test_compiler.py tests/test_config.py
```

Run the full suite:

```bash
python -m pytest
```

Manual smoke test with opt-in concurrency:

Set `concept_generation_concurrency: 3` in `.hermeskb/config.yaml`, then run:

```bash
hermes-wiki add ./sample-docs --workspace .
```

## Rollout

1. Add the config key with default `1`.
2. Extract concept task preparation without changing runtime behavior.
3. Add the executor helper and keep serial write behavior.
4. Add tests with monkeypatched generation calls.
5. Document opt-in concurrency in `README.md` after implementation lands.
6. Consider raising the default to `3` only after Hermes runtime smoke tests pass reliably.

## Risks

- Provider rate limits may increase with concurrent requests.
- More concurrent `AIAgent` instances may increase memory and network usage.
- Existing concept pages are read before generation, so external edits during generation can still be overwritten by the final serial write.
- Prompt caching benefits depend on provider behavior and may vary by configured model/provider.

## Non-Goals

- Do not share a single `AIAgent` across concept tasks.
- Do not introduce LiteLLM or OpenKB async completion calls.
- Do not make backlink or index writes concurrent.
- Do not integrate PageIndex node-summary concurrency in this patch.
