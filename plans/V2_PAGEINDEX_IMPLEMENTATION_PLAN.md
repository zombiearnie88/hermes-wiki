# V2 PageIndex Long-Doc Implementation Plan

## Goal

Add Hermes-native long-document support to the wiki plugin by cloning the useful PageIndex workflow into repo-owned code and replacing every LiteLLM generation path with Hermes `AIAgent`.

V2 should let `wiki add <long-pdf>` produce a normal wiki summary, concept updates, index entries, and retrievable page-level source content instead of returning the v1 unsupported-long-document message.

## Locked Decisions

- New runtime code lives under `hermes_wiki/`, not under `code-donor/PageIndex/`.
- `code-donor/PageIndex/` remains a reference donor only.
- Generation uses Hermes `AIAgent`, never LiteLLM.
- Keep the current schema layout:
  - root `AGENTS.md` guides Hermes agents at runtime.
  - `wiki/SCHEMA.md` defines wiki page structure and compiler output rules.
- Do not introduce `wiki/AGENTS.md`.
- V2.0 targets long PDFs first.
- Long Markdown and MarkItDown-backed long documents can follow after PDF support is stable.
- Retrieval is through Hermes wiki tools, not a separate PageIndex chat/query surface.

## Workspace Layout

The workspace should remain:

```text
AGENTS.md
raw/
wiki/
  SCHEMA.md
  index.md
  log.md
  sources/
  summaries/
  concepts/
  explorations/
  reports/
.hermeskb/
  config.yaml
  hashes.json
  pageindex/
```

Long-document PageIndex metadata should live in `.hermeskb/pageindex/{doc_name}/`:

```text
.hermeskb/pageindex/{doc_name}/
  index.json
  audit.json
```

- `index.json`: metadata, page count, document description, and tree structure without heavy page text.
- `audit.json`: optional diagnostics for build stage status, retries, failures, and model settings.
- `wiki/sources/{doc_name}.jsonl`: one source record per page with `page` and `content`, including extracted image references.

## Schema Roles

### Root `AGENTS.md`

This file is for Hermes agents answering user questions from the wiki. It should explain:

- Read `wiki/index.md` first.
- Read relevant `wiki/summaries/*.md` and `wiki/concepts/*.md` next.
- For `doc_type: short`, follow the summary `full_text` frontmatter to `wiki/sources/*.md`.
- For `doc_type: pageindex`, use `get_document_structure` and `get_page_content`.
- Fetch tight page ranges only.
- Never fetch a whole long document through `get_page_content`.
- Cite or mention the wiki pages and page ranges used when helpful.

### `wiki/SCHEMA.md`

This file is for compiler prompts and wiki content rules. It should define:

- Directory structure.
- Page types.
- Frontmatter fields.
- Wikilink conventions.
- Summary page format.
- Concept page format.
- PageIndex summary expectations.

The compiler should read `wiki/SCHEMA.md`, not root `AGENTS.md`, when generating summaries and concepts.

## Proposed Package Layout

Add a PageIndex package inside `hermes_wiki/`:

```text
hermes_wiki/
  pageindex/
    __init__.py
    builder.py
    config.py
    prompts.py
    retrieve.py
    store.py
    tree.py
    types.py
```

Suggested responsibilities:

- `builder.py`: orchestrates PDF tree construction and node summary generation.
- `config.py`: resolves PageIndex settings from `.hermeskb/config.yaml`.
- `prompts.py`: keeps donor-derived prompt templates in one place.
- `retrieve.py`: implements document structure and page-content retrieval helpers.
- `store.py`: reads and writes `.hermeskb/pageindex/{doc_name}/` metadata plus `wiki/sources/{doc_name}.jsonl` page content.
- `tree.py`: tree normalization, rendering, node IDs, page ranges, text attachment, and text stripping.
- `types.py`: small dataclasses for PageIndex build results and retrieval records.

## Runtime Adapter

Create a thin PageIndex generation adapter over `hermes_wiki.runtime.generate_conversation()`.

Rules:

- Instantiate a fresh `AIAgent` per generation task through the existing runtime helper.
- Use `quiet_mode=True`, `skip_memory=True`, `skip_context_files=True`, and disabled tools via the runtime helper.
- Parse JSON with the existing `json-repair` based parser pattern.
- Do not share one `AIAgent` across concurrent tasks.
- Start with sequential PageIndex generation unless concurrency is explicitly added and guarded.

LiteLLM replacement details:

- Replace `llm_completion(...)` with `pageindex_generate_text(...)` and `pageindex_generate_json(...)`.
- Replace `llm_acompletion(...)` with sequential sync calls first. Async can be added later if Hermes runtime behavior is proven safe for many fresh agents.
- Replace LiteLLM token counting with a conservative local estimate, for example `max(1, len(text) // 4)`, unless a tokenizer dependency is intentionally added later.
- Replace finish-reason continuation loops with validation and retry loops. Hermes `AIAgent.run_conversation()` does not currently expose LiteLLM-style finish reasons in this repo.

## Long-PDF Build Flow

The first V2 target is long PDFs that cross `long_doc_threshold`.

High-level flow:

1. `wiki add` detects a PDF with `page_count >= long_doc_threshold`.
2. The file is copied into `raw/` as today.
3. The PageIndex builder extracts per-page text and image references with PyMuPDF.
4. The builder detects or derives document structure.
5. The builder assigns page ranges and node IDs.
6. The builder generates node summaries and a document description with `AIAgent`.
7. The PageIndex store writes `index.json`, optional `audit.json`, and `wiki/sources/{doc_name}.jsonl`.
8. The wiki compiler writes a `doc_type: pageindex` summary page.
9. Existing concept planning and concept write/update logic runs against the generated long-doc summary.
10. `wiki/index.md` is updated with a `(pageindex)` document entry.
11. The operation log records the ingest.
12. The hash registry is updated only after all required writes succeed.

## Compiler Integration

Add a new function near `compile_short_doc()`:

```python
def compile_pageindex_doc(
    doc_name: str,
    raw_path: Path,
    paths: WorkspacePaths,
    model: str,
    provider: str | None,
    *,
    language_override: str | None = None,
) -> CompileResult:
    ...
```

`compile_pageindex_doc()` should:

- Read `wiki/SCHEMA.md` for compiler rules.
- Build or load PageIndex state.
- Render a compact summary page from PageIndex metadata and tree structure.
- Use `doc_type: pageindex` in summary frontmatter.
- Include enough tree structure for agents to choose page ranges.
- Avoid embedding full long-document text in summary pages.
- Reuse the existing concept planning, creation, update, backlink, and index helpers where practical.

Recommended PageIndex summary frontmatter:

```yaml
---
doc_type: pageindex
pageindex_id: {doc_name}
full_text: sources/{doc_name}.jsonl
page_count: 128
---
```

Recommended summary body:

```markdown
# Summary

<model-generated document overview>

## PageIndex Structure

- [1-4] Executive Summary: ...
- [5-18] Business Overview: ...
- [19-42] Risk Factors: ...

## Retrieval Notes

Use `get_document_structure("{doc_name}")` for the complete tree and `get_page_content("{doc_name}", "5-8")` for details.
```

## Command Integration

Change `_run_add()` long-PDF behavior:

Current v1 behavior:

```text
UNSUPPORTED file.pdf: long documents are not supported yet
```

V2 behavior:

```text
OK file.pdf: pageindex summary written (128 pages), created 2, updated 1, related 0
```

Implementation notes:

- Keep short-doc behavior unchanged.
- Keep file hash dedupe behavior unchanged.
- Keep directory ingest behavior unchanged.
- Continue after a single-file failure during directory ingest.
- Do not register a hash for failed PageIndex builds.

## Tool Integration

Register retrieval tools in the plugin:

- `get_document_structure`
- `get_page_content`
- Optional `get_document`

Tool behavior:

- Accept `doc_name` and optional `workspace`.
- Resolve the workspace with the existing workspace discovery helper.
- Load PageIndex state from `.hermeskb/pageindex/{doc_name}/`.
- Return JSON strings, matching the style of existing plugin tools.
- Return clear error JSON for unknown documents, invalid page syntax, or missing PageIndex files.

`get_page_content` should enforce guardrails:

- Support `5`, `5-7`, and `3,8`.
- Reject page ranges outside the document.
- Reject requests above `pageindex_max_pages_per_tool_call`.
- Default max pages per call should be around 8 to 10.
- Never provide a convenience mode that returns the whole document.

## Config

Add PageIndex config keys to `.hermeskb/config.yaml` defaults:

```yaml
pageindex_toc_check_pages: 20
pageindex_max_pages_per_node: 10
pageindex_max_tokens_per_node: 20000
pageindex_summary_token_threshold: 200
pageindex_max_pages_per_tool_call: 8
```

Expose these through `wiki config` only if needed. It is acceptable to keep advanced PageIndex settings config-file-only in the first patch, as long as defaults are documented.

## Dependencies

Do not add LiteLLM.

Preferred dependencies for V2.0:

- Existing `json-repair` for JSON parsing.
- Existing `pymupdf` for PDF extraction.
- Existing `markitdown[all]` remains for short docs and later long non-PDF conversion.

Avoid adding PyPDF2 unless there is a concrete reason. The current plugin already uses PyMuPDF for PDF ingest.

## Testing Plan

Add targeted tests before broad integration tests.

Unit tests:

- Page range parsing accepts `5`, `5-7`, and `3,8`.
- Page range parsing rejects invalid, reversed, out-of-range, and too-large requests.
- PageIndex store writes and reloads `index.json` and `wiki/sources/{doc_name}.jsonl`.
- Tree rendering omits full text but includes titles, node IDs, summaries, and page ranges.
- Runtime adapter calls Hermes generation through fresh `AIAgent` helper calls.

Compiler tests:

- `compile_pageindex_doc()` writes a `doc_type: pageindex` summary.
- PageIndex summary does not include full document text.
- Index entry renders `(pageindex)`.
- Concept planning and updates still run from the generated summary.

Command tests:

- Long PDFs route to PageIndex instead of unsupported output.
- Failed PageIndex builds do not update `hashes.json`.
- Directory ingest continues after one long-doc failure.
- `wiki list` shows PageIndex documents with the correct type.

Tool tests:

- `get_document_structure` returns structure for a PageIndex document.
- `get_page_content` returns selected pages only.
- Unknown document and missing workspace cases return structured failures.

Suggested verification commands:

```bash
python -m pytest tests/test_pageindex_*.py
python -m pytest tests/test_commands.py tests/test_compiler.py tests/test_tools.py
python -m pytest
```

## Implementation Phases

### Phase 1: Schema And Config Cleanup

- Confirm workspace init writes root `AGENTS.md` and `wiki/SCHEMA.md`.
- Make compiler prompts read `wiki/SCHEMA.md` instead of looking for `wiki/AGENTS.md`.
- Update default root `AGENTS.md` to include PageIndex retrieval guidance.
- Add PageIndex config defaults.

### Phase 2: PageIndex Store And Retrieval

- Add `.hermeskb/pageindex/{doc_name}/` path helpers.
- Implement PageIndex store read/write helpers.
- Implement page range parser and retrieval helpers.
- Add `get_document_structure` and `get_page_content` plugin tools.
- Test retrieval without running the full PageIndex builder.

### Phase 3: AIAgent PageIndex Adapter

- Add PageIndex prompt adapter functions.
- Port JSON/text generation helpers from donor behavior to Hermes runtime calls.
- Add retry and validation behavior around JSON responses.
- Keep calls sequential initially.

### Phase 4: Long-PDF Builder

- Port PDF page extraction using PyMuPDF.
- Port donor tree-building logic in small pieces.
- Port TOC detection and TOC-to-tree flows.
- Port fallback no-TOC structure generation.
- Port node summary and document description generation.
- Write PageIndex build artifacts to the store.

### Phase 5: Wiki Compiler Integration

- Add `compile_pageindex_doc()`.
- Render compact PageIndex summaries.
- Reuse existing concept update/index helpers.
- Add command routing from long PDFs to PageIndex compile.
- Update user-facing command output.

### Phase 6: Docs And Operator Guidance

- Update README usage and capability docs.
- Update the bundled `wiki-operator` skill.
- Update plugin schemas and `plugin.yaml` for new retrieval tools.
- Document PageIndex config keys and retrieval guardrails.

### Phase 7: Hardening

- Add audit output for failed build stages.
- Add clear errors for image-only or low-text PDFs.
- Add conservative limits for pages, retries, and generated JSON size.
- Add smoke tests with a tiny generated PDF fixture.

## Risks And Mitigations

- Donor PageIndex expects LiteLLM finish reasons. Mitigate by replacing continuation loops with validation/retry flows.
- Long PDFs may trigger many LLM calls. Mitigate by starting sequentially and keeping tree/node summary defaults conservative.
- PDF text extraction quality may be poor. Mitigate with clear errors and defer OCR-specific work.
- PageIndex summaries can become too large. Mitigate by rendering only compact tree outlines in wiki summaries.
- Retrieval tools could expose too much content. Mitigate with strict page-count limits.

## Definition Of Done

- `wiki add` successfully ingests a long PDF above `long_doc_threshold`.
- The long PDF produces PageIndex state under `.hermeskb/pageindex/{doc_name}/`.
- The wiki has a `doc_type: pageindex` summary for the document.
- The wiki index lists the document as `(pageindex)`.
- Concepts can be created or updated from the long-doc summary.
- `get_document_structure` and `get_page_content` work for the ingested document.
- The generation path contains no LiteLLM dependency.
- Root `AGENTS.md` remains agent-facing and `wiki/SCHEMA.md` remains compiler/content-facing.
