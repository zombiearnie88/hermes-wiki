# Run Conversation Compiler Plan

## Goal

Bring the Hermes short-document compiler closer to OpenKB's multi-step LLM pipeline while using Hermes-native `AIAgent.run_conversation()` instead of LiteLLM.

The key change is to reuse OpenAI-format message history as the prompt-cache prefix, not to reuse an `AIAgent` instance.

## Current Gap

The current compiler calls `generate_text(system_prompt, user_prompt)` for each step:

- summary generation receives the full source document
- concept planning receives only the generated summary text
- concept create/update receives only the generated summary text and local task details

This differs from OpenKB, which builds a stable base context:

```text
system schema/language prompt
user full-document summary request
assistant generated summary
user next compiler task
```

OpenKB repeats that message prefix for concept planning and concept page generation so provider prompt caching can reuse the full-document prefix.

## Design Principles

- Keep a fresh `AIAgent` per generation task.
- Do not share one `AIAgent` across concurrent tasks.
- Reuse `conversation_history` message lists for cache-friendly context reuse.
- Preserve OpenAI-compatible role alternation.
- Keep `quiet_mode=True`, `skip_memory=True`, `skip_context_files=True`, and tools disabled.
- Keep concept generation sequential for v1 unless concurrency is explicitly added later.

## Runtime Changes

Add a new runtime helper around `AIAgent.run_conversation()`.

Suggested shape:

```python
@dataclass
class GenerationResult:
    final_response: str
    messages: list[dict]


def generate_conversation(
    model: str,
    provider: str | None,
    user_message: str,
    *,
    system_message: str | None = None,
    conversation_history: list[dict] | None = None,
    task_id: str | None = None,
) -> GenerationResult:
    ...
```

Implementation notes:

- Instantiate `AIAgent` inside the helper for every call.
- Pass `provider` only when configured.
- Call `agent.run_conversation(...)`, not `agent.chat(...)`.
- Return `result["final_response"].strip()` and `result["messages"]`.
- Raise `HermesRuntimeError` when `run_agent.AIAgent` is unavailable, the response is empty, or the agent call fails.
- Keep existing `generate_text(...)` as a compatibility wrapper over `generate_conversation(...)`.

## Compiler Changes

Refactor `compile_short_doc(...)` to build and reuse message history.

### Step 1: Summary

- Build `system_prompt` from `wiki/SCHEMA.md` and configured language.
- Build `summary_user` with the document name and full source content.
- Call `generate_conversation(...)` with `system_message=system_prompt`, `user_message=summary_user`, and no prior history.
- Parse the response as JSON.
- Write the summary page as today.

### Step 2: Base History

Construct a reusable base history for later calls:

```python
base_history = [
    {"role": "system", "content": system_prompt},
    {"role": "user", "content": summary_user},
    {"role": "assistant", "content": summary},
]
```

Use the parsed summary Markdown as the assistant message content, not the raw JSON wrapper. This gives later steps a clean conversation state while keeping the same full-document prefix.

### Step 3: Concept Plan

- Change the concept-plan prompt to rely on the prior assistant summary instead of embedding the summary again.
- Include only the existing concept briefs and task instructions in the new user message.
- Call `generate_conversation(...)` with `conversation_history=base_history` and the concept-plan user message.
- Parse create/update/related items as today.

### Step 4: Concept Create/Update

For each concept item:

- Use the same `base_history`.
- Add one new user message for the concept creation or update task.
- For updates, include the existing concept page body in that user message.
- Parse JSON and write concept pages as today.

Do not mutate `base_history` between concepts.

### Step 5: Code-Only Updates

Keep existing non-LLM behavior:

- add related links
- backlink summary and concepts
- update index
- return `CompileResult`

## Prompt Adjustments

Change concept prompts toward OpenKB's message-history style.

Current concept-plan prompt embeds:

```text
Document summary:
{summary}
```

Replace with:

```text
Based on the summary above, decide how to update the wiki's concept pages.

Existing concept pages:
{concept_briefs}
```

Current concept create/update prompts embed the summary again. Remove that duplicated summary text and rely on the assistant summary already in `conversation_history`.

## Role Alternation Rules

The reusable base history must remain valid:

```text
system -> user -> assistant
```

Each new `run_conversation(...)` call appends one user message internally:

```text
system -> user -> assistant -> user -> assistant
```

Avoid manually appending the concept-plan assistant response to the history used for concept generation unless the next prompt requires it. OpenKB concept generation depends on the document summary, not necessarily on the raw plan response.

## Tests

Update `tests/test_runtime.py`:

- mock `AIAgent.run_conversation(...)` instead of `chat(...)`
- assert `system_message`, `user_message`, `conversation_history`, and agent kwargs are passed correctly
- assert empty `final_response` raises `HermesRuntimeError`
- keep the provider/model error hint test

Update `tests/test_compiler.py`:

- monkeypatch the new conversation helper where useful
- assert concept-plan calls receive `conversation_history` containing the full-document summary request
- assert concept create/update calls receive the same full-document base history
- assert concept prompts no longer duplicate the summary text in the user message
- keep existing assertions for summary, concepts, backlinks, sources, and index writes

## Verification

Run targeted tests first:

```bash
python -m pytest tests/test_runtime.py tests/test_compiler.py
```

Then run the full suite if targeted tests pass:

```bash
python -m pytest
```

## Deferred Work

- Concurrent concept generation using fresh agents and immutable `base_history`; see `plans/AIAGENT_CONCURRENT_CONCEPT_GENERATION_PLAN.md`.
- Long-document PageIndex parity.
- Usage/cache telemetry surfaced from Hermes result metadata, if available.
