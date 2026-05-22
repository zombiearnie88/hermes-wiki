from __future__ import annotations

import asyncio
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import load_config
from .pageindex.builder import build_or_load_pageindex_async
from .pageindex.tree import render_tree
from .runtime import GenerationResult, HermesRuntimeError, agenerate_conversation
from .schema import get_schema_md
from .workspace import WorkspacePaths

_SYSTEM_TEMPLATE = """\
You are Hermes Wiki's compilation agent for a personal knowledge base.

{schema_md}

Write all content in {language} language.
Use [[wikilinks]] only for pages the prompt explicitly asks you to link or pages that already exist in supplied wiki context.
"""

_SUMMARY_USER = """\
New document: {doc_name}

Full text:
{content}

Write a summary page for this document in Markdown.

Return a JSON object with two keys:
- "brief": A single sentence (under 100 chars) describing the document's main contribution
- "content": The full summary in Markdown. Include key concepts, findings, ideas, \
and [[wikilinks]] to concepts that could become cross-document concept pages

Return ONLY valid JSON, no fences.
"""

_PAGEINDEX_SUMMARY_USER = """\
This is a PageIndex summary for long document "{doc_name}" (page count: {page_count}):

{summary}

Based on this structured summary, write a concise overview that captures \
the key themes and findings. This will be used to generate concept pages.

Return ONLY the Markdown content (no frontmatter, no code fences).
"""

_CONCEPTS_PLAN_USER = """\
Document name: {doc_name}

Based on the summary above, decide how to update the wiki's concept pages.

Existing concept pages:
{concept_briefs}

Return a JSON object with three keys:

1. "create" — new concepts not covered by any existing page. Array of objects:
   {{"name": "concept-slug", "title": "Human-Readable Title"}}

2. "update" — existing concepts that have significant new information from \
this document worth integrating. Array of objects:
   {{"name": "existing-slug", "title": "Existing Title"}}

3. "related" — existing concepts tangentially related to this document but \
not needing content changes, just a cross-reference link. Array of slug strings.

Rules:
- For the first few documents, create 2-3 foundational concepts at most.
- Do NOT create a concept that overlaps with an existing one — use "update".
- Do NOT create concepts that are just the document topic itself.
- "related" is for lightweight cross-linking only, no content rewrite needed.

Return ONLY valid JSON, no fences, no explanation.
"""

_CONCEPT_PAGE_USER = """\
Write the concept page for: {title}

This concept relates to the document "{doc_name}" summarized above.

Return a JSON object with two keys:
- "brief": A single sentence (under 100 chars) defining this concept
- "content": The full concept page in Markdown. Include clear explanation, \
key details from the source document, and [[wikilinks]] to related concepts \
and [[summaries/{doc_name}]]

Return ONLY valid JSON, no fences.
"""

_CONCEPT_UPDATE_USER = """\
Update the concept page for: {title}

Current content of this page:
{existing_content}

New information from document "{doc_name}" (summarized above) should be \
integrated into this page. Rewrite the full page incorporating the new \
information naturally — do not just append. Maintain existing \
[[wikilinks]] and add new ones where appropriate.

Return a JSON object with two keys:
- "brief": A single sentence (under 100 chars) defining this concept (may differ from before)
- "content": The rewritten full concept page in Markdown

Return ONLY valid JSON, no fences.
"""

_SAFE_NAME_RE = re.compile(r"[^\w\-]")


@dataclass
class CompileResult:
    """Counts and document brief returned by one wiki compilation run."""

    doc_brief: str
    created_concepts: int
    updated_concepts: int
    related_concepts: int


@dataclass(frozen=True)
class ConceptGenerationTask:
    """Prepared concept creation or update request from a model plan."""

    action: str
    name: str
    safe_name: str
    title: str
    user_message: str


@dataclass(frozen=True)
class ConceptGenerationResult:
    """Parsed output for one generated concept page."""

    task: ConceptGenerationTask
    brief: str
    content: str


async def _agenerate_conversation(
    llm: Any,
    model: str,
    provider: str | None,
    user_message: str,
    *,
    system_message: str | None = None,
    conversation_history: list[dict] | None = None,
    purpose: str | None = None,
) -> GenerationResult:
    """Call the runtime generation adapter through a compiler-local seam."""
    return await agenerate_conversation(
        llm,
        model,
        provider,
        user_message,
        system_message=system_message,
        conversation_history=conversation_history,
        purpose=purpose,
    )


def _parse_json(text: str) -> list | dict:
    """Repair and parse model output expected to contain JSON."""
    try:
        from json_repair import repair_json
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "json-repair is required to parse compiler responses. Install json-repair in the runtime environment."
        ) from exc

    cleaned = text.strip()
    if cleaned.startswith("```"):
        first_newline = cleaned.find("\n")
        cleaned = cleaned[first_newline + 1 :] if first_newline != -1 else cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
    parsed = json.loads(repair_json(cleaned.strip()))
    if not isinstance(parsed, (dict, list)):
        raise ValueError(f"Expected JSON object or array, got {type(parsed).__name__}")
    return parsed


def _clean_frontmatter_value(value: str) -> str:
    """Collapse free-form model text for safe one-line frontmatter values."""
    return " ".join(value.split())


def _read_concept_briefs(wiki_dir: Path) -> str:
    """Render existing concept slugs and briefs for concept-planning prompts."""
    concepts_dir = wiki_dir / "concepts"
    if not concepts_dir.exists():
        return "(none yet)"

    markdown_files = sorted(concepts_dir.glob("*.md"))
    if not markdown_files:
        return "(none yet)"

    lines: list[str] = []
    for path in markdown_files:
        text = path.read_text(encoding="utf-8")
        brief = ""
        body = text
        if text.startswith("---"):
            end = text.find("---", 3)
            if end != -1:
                frontmatter = text[: end + 3]
                body = text[end + 3 :]
                for line in frontmatter.split("\n"):
                    if line.startswith("brief:"):
                        brief = line[len("brief:") :].strip()
                        break
        if not brief:
            brief = body.strip().replace("\n", " ")[:150]
        if brief:
            lines.append(f"- {path.stem}: {brief}")
    return "\n".join(lines) or "(none yet)"


def _write_summary(
    wiki_dir: Path,
    doc_name: str,
    summary: str,
    doc_type: str = "short",
    *,
    full_text: str | None = None,
    extra_frontmatter: dict[str, str | int] | None = None,
) -> None:
    """Write a summary page with code-owned frontmatter."""
    if summary.startswith("---"):
        end = summary.find("---", 3)
        if end != -1:
            summary = summary[end + 3 :].lstrip("\n")
    summaries_dir = wiki_dir / "summaries"
    summaries_dir.mkdir(parents=True, exist_ok=True)
    frontmatter_lines = [
        f"doc_type: {doc_type}",
        f"full_text: {full_text or f'sources/{doc_name}.md'}",
    ]
    for key, value in (extra_frontmatter or {}).items():
        frontmatter_lines.append(f"{key}: {value}")
    frontmatter = "---\n" + "\n".join(frontmatter_lines) + "\n---\n\n"
    (summaries_dir / f"{doc_name}.md").write_text(frontmatter + summary, encoding="utf-8")


def _sanitize_concept_name(name: str) -> str:
    """Normalize a model-proposed concept name into a safe file slug."""
    name = unicodedata.normalize("NFKC", name)
    sanitized = _SAFE_NAME_RE.sub("-", name).strip("-")
    return sanitized or "unnamed-concept"


def _write_concept(
    wiki_dir: Path,
    name: str,
    content: str,
    source_file: str,
    is_update: bool,
    brief: str = "",
) -> None:
    """Create or update a concept page while preserving managed metadata."""
    concepts_dir = wiki_dir / "concepts"
    concepts_dir.mkdir(parents=True, exist_ok=True)
    safe_name = _sanitize_concept_name(name)
    path = (concepts_dir / f"{safe_name}.md").resolve()
    if not path.is_relative_to(concepts_dir.resolve()):
        return

    brief = _clean_frontmatter_value(brief) if brief else ""
    if is_update and path.exists():
        # Step 1: ensure the updated concept frontmatter includes this source.
        existing = path.read_text(encoding="utf-8")
        if source_file not in existing:
            if existing.startswith("---"):
                end = existing.find("---", 3)
                if end != -1:
                    frontmatter = existing[: end + 3]
                    body = existing[end + 3 :]
                    if "sources:" in frontmatter:
                        frontmatter = frontmatter.replace("sources: [", f"sources: [{source_file}, ")
                    else:
                        frontmatter = frontmatter.replace("---\n", f"---\nsources: [{source_file}]\n", 1)
                    existing = frontmatter + body
            else:
                existing = f"---\nsources: [{source_file}]\n---\n\n" + existing

        # Step 2: replace the body with the model's full rewritten concept page.
        clean = content
        if clean.startswith("---"):
            end = clean.find("---", 3)
            if end != -1:
                clean = clean[end + 3 :].lstrip("\n")

        if existing.startswith("---"):
            end = existing.find("---", 3)
            if end != -1:
                existing = existing[: end + 3] + "\n\n" + clean
            else:
                existing = clean
        else:
            existing = clean

        # Step 3: update the concept brief if the model returned one.
        if brief and existing.startswith("---"):
            end = existing.find("---", 3)
            if end != -1:
                frontmatter = existing[: end + 3]
                body = existing[end + 3 :]
                if "brief:" in frontmatter:
                    frontmatter = re.sub(r"brief:.*", f"brief: {brief}", frontmatter)
                else:
                    frontmatter = frontmatter.replace("---\n", f"---\nbrief: {brief}\n", 1)
                existing = frontmatter + body
        path.write_text(existing, encoding="utf-8")
        return

    # Step 4: create new concept pages with fresh code-owned frontmatter.
    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            content = content[end + 3 :].lstrip("\n")
    frontmatter_lines = [f"sources: [{source_file}]"]
    if brief:
        frontmatter_lines.append(f"brief: {brief}")
    frontmatter = "---\n" + "\n".join(frontmatter_lines) + "\n---\n\n"
    path.write_text(frontmatter + content, encoding="utf-8")


def _read_existing_concept_content(wiki_dir: Path, safe_name: str) -> str:
    """Return existing concept body text for update prompts."""
    concept_path = wiki_dir / "concepts" / f"{safe_name}.md"
    if not concept_path.exists():
        return "(page not found - create from scratch)"

    raw_text = concept_path.read_text(encoding="utf-8")
    if raw_text.startswith("---"):
        parts = raw_text.split("---", 2)
        return parts[2].strip() if len(parts) >= 3 else raw_text
    return raw_text


def _prepare_concept_generation_tasks(
    wiki_dir: Path,
    doc_name: str,
    create_items: list,
    update_items: list,
) -> list[ConceptGenerationTask]:
    """Normalize model-planned create/update items into generation tasks."""
    tasks: list[ConceptGenerationTask] = []
    seen_slugs: set[str] = set()

    # Step 1: queue valid concept creations, de-duplicated by safe slug.
    for concept in create_items:
        if not isinstance(concept, dict) or "name" not in concept:
            continue
        name = str(concept["name"])
        safe_name = _sanitize_concept_name(name)
        if safe_name in seen_slugs:
            continue
        seen_slugs.add(safe_name)
        title = str(concept.get("title", name))
        tasks.append(
            ConceptGenerationTask(
                action="create",
                name=name,
                safe_name=safe_name,
                title=title,
                user_message=_CONCEPT_PAGE_USER.format(doc_name=doc_name, title=title),
            )
        )

    # Step 2: queue valid updates with the current page body included.
    for concept in update_items:
        if not isinstance(concept, dict) or "name" not in concept:
            continue
        name = str(concept["name"])
        safe_name = _sanitize_concept_name(name)
        if safe_name in seen_slugs:
            continue
        seen_slugs.add(safe_name)
        title = str(concept.get("title", name))
        existing_content = _read_existing_concept_content(wiki_dir, safe_name)
        tasks.append(
            ConceptGenerationTask(
                action="update",
                name=name,
                safe_name=safe_name,
                title=title,
                user_message=_CONCEPT_UPDATE_USER.format(
                    doc_name=doc_name,
                    title=title,
                    existing_content=existing_content,
                ),
            )
        )

    return tasks


def _parse_concept_page_response(raw: str) -> tuple[str, str]:
    """Extract brief and body from a concept-page model response."""
    try:
        parsed_page = _parse_json(raw)
        if isinstance(parsed_page, dict):
            return str(parsed_page.get("brief", "")), str(parsed_page.get("content", raw))
    except (json.JSONDecodeError, ValueError):
        pass
    return "", raw


async def _agenerate_concept_task(
    llm: Any,
    task: ConceptGenerationTask,
    *,
    doc_name: str,
    model: str,
    provider: str | None,
    base_history: list[dict],
) -> ConceptGenerationResult:
    """Generate one concept page from a prepared task."""
    result = await _agenerate_conversation(
        llm,
        model,
        provider,
        task.user_message,
        conversation_history=base_history,
        purpose=f"wiki.concepts.{task.action}.{doc_name}.{task.safe_name}",
    )
    brief, page_content = _parse_concept_page_response(result.final_response)
    return ConceptGenerationResult(task=task, brief=brief, content=page_content)


async def _agenerate_concept_tasks(
    llm: Any,
    tasks: list[ConceptGenerationTask],
    *,
    doc_name: str,
    model: str,
    provider: str | None,
    base_history: list[dict],
    max_concurrency: int,
) -> list[ConceptGenerationResult]:
    """Generate concept pages concurrently with bounded fan-out."""
    if not tasks:
        return []

    # Step 1: bound parallel model calls to the workspace-configured limit.
    max_concurrency = max(1, min(max_concurrency, len(tasks)))
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

    gathered = await asyncio.gather(
        *(run_task(task) for task in tasks),
        return_exceptions=True,
    )

    # Step 2: keep successful concept results while tracking generation errors.
    results: list[ConceptGenerationResult] = []
    errors: list[Exception] = []
    for item in gathered:
        if isinstance(item, Exception):
            errors.append(item)
        else:
            results.append(item)

    # Step 3: preserve fail-closed runtime errors when every task failed identically.
    if not results and errors and len(errors) == len(tasks):
        first = errors[0]
        if isinstance(first, HermesRuntimeError) and all(
            type(error) is type(first) and str(error) == str(first) for error in errors
        ):
            raise first
    return results


def _get_section_bounds(lines: list[str], heading: str) -> tuple[int, int] | None:
    """Return the line range belonging to a Markdown level-two section."""
    for index, line in enumerate(lines):
        if line == heading:
            start = index + 1
            end = len(lines)
            for probe in range(start, len(lines)):
                if lines[probe].startswith("## "):
                    end = probe
                    break
            return start, end
    return None


def _section_contains_link(lines: list[str], heading: str, link: str) -> bool:
    """Check whether an index section already contains a wikilink entry."""
    bounds = _get_section_bounds(lines, heading)
    if bounds is None:
        return False
    start, end = bounds
    prefix = f"- {link}"
    return any(line.startswith(prefix) for line in lines[start:end])


def _replace_section_entry(lines: list[str], heading: str, link: str, entry: str) -> bool:
    """Replace an existing Markdown list entry inside an index section."""
    bounds = _get_section_bounds(lines, heading)
    if bounds is None:
        return False
    start, end = bounds
    prefix = f"- {link}"
    for index in range(start, end):
        if lines[index].startswith(prefix):
            lines[index] = entry
            return True
    return False


def _insert_section_entry(lines: list[str], heading: str, entry: str) -> bool:
    """Insert a Markdown list entry at the top of an index section."""
    bounds = _get_section_bounds(lines, heading)
    if bounds is None:
        return False
    start, _ = bounds
    lines.insert(start, entry)
    return True


def _add_related_link(wiki_dir: Path, concept_slug: str, doc_name: str, source_file: str) -> None:
    """Attach a lightweight document cross-reference to an existing concept."""
    concepts_dir = wiki_dir / "concepts"
    path = concepts_dir / f"{concept_slug}.md"
    if not path.exists():
        return

    text = path.read_text(encoding="utf-8")
    link = f"[[summaries/{doc_name}]]"
    if link in text:
        return

    # Step 1: keep concept source metadata aligned with the related link.
    if source_file not in text:
        if text.startswith("---"):
            end = text.find("---", 3)
            if end != -1:
                frontmatter = text[: end + 3]
                body = text[end + 3 :]
                if "sources:" in frontmatter:
                    frontmatter = frontmatter.replace("sources: [", f"sources: [{source_file}, ")
                else:
                    frontmatter = frontmatter.replace("---\n", f"---\nsources: [{source_file}]\n", 1)
                text = frontmatter + body
        else:
            text = f"---\nsources: [{source_file}]\n---\n\n" + text

    # Step 2: append a simple related-document pointer without rewriting content.
    text += f"\n\nSee also: {link}"
    path.write_text(text, encoding="utf-8")


def _backlink_summary(wiki_dir: Path, doc_name: str, concept_slugs: list[str]) -> None:
    """Ensure a summary page links back to generated or related concepts."""
    summary_path = wiki_dir / "summaries" / f"{doc_name}.md"
    if not summary_path.exists():
        return

    text = summary_path.read_text(encoding="utf-8")
    missing = [slug for slug in concept_slugs if f"[[concepts/{slug}]]" not in text]
    if not missing:
        return

    new_links = "\n".join(f"- [[concepts/{slug}]]" for slug in missing)
    if "## Related Concepts" in text:
        text = text.replace("## Related Concepts\n", f"## Related Concepts\n{new_links}\n", 1)
    else:
        text += f"\n\n## Related Concepts\n{new_links}\n"
    summary_path.write_text(text, encoding="utf-8")


def _backlink_concepts(wiki_dir: Path, doc_name: str, concept_slugs: list[str]) -> None:
    """Ensure concept pages link back to the current summary page."""
    link = f"[[summaries/{doc_name}]]"
    concepts_dir = wiki_dir / "concepts"
    for slug in concept_slugs:
        path = concepts_dir / f"{slug}.md"
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        if link in text:
            continue
        if "## Related Documents" in text:
            text = text.replace("## Related Documents\n", f"## Related Documents\n- {link}\n", 1)
        else:
            text += f"\n\n## Related Documents\n- {link}\n"
        path.write_text(text, encoding="utf-8")


def _update_index(
    wiki_dir: Path,
    doc_name: str,
    concept_names: list[str],
    *,
    doc_brief: str = "",
    concept_briefs: dict[str, str] | None = None,
    doc_type: str = "short",
) -> None:
    """Add the compiled document and generated concepts to wiki/index.md."""
    concept_briefs = concept_briefs or {}
    index_path = wiki_dir / "index.md"
    if not index_path.exists():
        index_path.write_text(
            "# Knowledge Base Index\n\n## Documents\n\n## Concepts\n\n## Explorations\n",
            encoding="utf-8",
        )

    lines = index_path.read_text(encoding="utf-8").split("\n")

    # Step 1: register the document summary once, preserving existing entries.
    doc_link = f"[[summaries/{doc_name}]]"
    if not _section_contains_link(lines, "## Documents", doc_link):
        entry = f"- {doc_link} ({doc_type})"
        if doc_brief:
            entry += f" - {_clean_frontmatter_value(doc_brief)}"
        _insert_section_entry(lines, "## Documents", entry)

    # Step 2: upsert concept entries so refreshed briefs stay visible.
    for name in concept_names:
        concept_link = f"[[concepts/{name}]]"
        entry = f"- {concept_link}"
        if name in concept_briefs:
            entry += f" - {_clean_frontmatter_value(concept_briefs[name])}"
        if _section_contains_link(lines, "## Concepts", concept_link):
            if name in concept_briefs:
                _replace_section_entry(lines, "## Concepts", concept_link, entry)
        else:
            _insert_section_entry(lines, "## Concepts", entry)

    index_path.write_text("\n".join(lines), encoding="utf-8")


async def _compile_concepts_from_summary_async(
    llm: Any,
    doc_name: str,
    paths: WorkspacePaths,
    model: str,
    provider: str | None,
    *,
    system_prompt: str,
    summary_user: str,
    summary: str,
    doc_brief: str,
    doc_type: str,
    concept_generation_concurrency: int,
) -> CompileResult:
    """Plan, generate, write, and index concepts from a summary page."""
    wiki_dir = paths.wiki_dir

    # Step 1: seed concept planning with the exact summary conversation.
    base_history = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": summary_user},
        {"role": "assistant", "content": summary},
    ]

    # Step 2: ask the model which concept pages to create, update, or relate.
    concept_briefs_text = _read_concept_briefs(wiki_dir)
    plan_result = await _agenerate_conversation(
        llm,
        model,
        provider,
        _CONCEPTS_PLAN_USER.format(
            doc_name=doc_name,
            concept_briefs=concept_briefs_text,
        ),
        conversation_history=base_history,
        purpose=f"wiki.concepts.plan.{doc_name}",
    )
    plan_raw = plan_result.final_response
    try:
        parsed = _parse_json(plan_raw)
    except (json.JSONDecodeError, ValueError):
        _update_index(wiki_dir, doc_name, [], doc_brief=doc_brief, doc_type=doc_type)
        return CompileResult(doc_brief=doc_brief, created_concepts=0, updated_concepts=0, related_concepts=0)

    if isinstance(parsed, list):
        plan = {"create": parsed, "update": [], "related": []}
    else:
        plan = {
            "create": parsed.get("create", []),
            "update": parsed.get("update", []),
            "related": parsed.get("related", []),
        }

    # Step 3: normalize malformed plan fields into safe empty lists.
    create_items = plan["create"] if isinstance(plan["create"], list) else []
    update_items = plan["update"] if isinstance(plan["update"], list) else []
    related_items = plan["related"] if isinstance(plan["related"], list) else []
    if not create_items and not update_items and not related_items:
        _update_index(wiki_dir, doc_name, [], doc_brief=doc_brief, doc_type=doc_type)
        return CompileResult(doc_brief=doc_brief, created_concepts=0, updated_concepts=0, related_concepts=0)

    source_file = f"summaries/{doc_name}.md"
    concept_names: list[str] = []
    concept_briefs_map: dict[str, str] = {}
    created_count = 0
    updated_count = 0

    # Step 4: run concept page generation concurrently, but serialize writes.
    concept_tasks = _prepare_concept_generation_tasks(wiki_dir, doc_name, create_items, update_items)
    concept_results = await _agenerate_concept_tasks(
        llm,
        concept_tasks,
        doc_name=doc_name,
        model=model,
        provider=provider,
        base_history=base_history,
        max_concurrency=concept_generation_concurrency,
    )

    for concept_result in concept_results:
        task = concept_result.task
        is_update = task.action == "update"
        _write_concept(wiki_dir, task.name, concept_result.content, source_file, is_update, brief=concept_result.brief)
        concept_names.append(task.safe_name)
        if is_update:
            updated_count += 1
        else:
            created_count += 1
        if concept_result.brief:
            concept_briefs_map[task.safe_name] = concept_result.brief

    # Step 5: apply lightweight related links and bidirectional backlinks.
    sanitized_related = [_sanitize_concept_name(str(item)) for item in related_items]
    for slug in sanitized_related:
        _add_related_link(wiki_dir, slug, doc_name, source_file)

    all_concept_slugs = concept_names + sanitized_related
    if all_concept_slugs:
        _backlink_summary(wiki_dir, doc_name, all_concept_slugs)
        _backlink_concepts(wiki_dir, doc_name, all_concept_slugs)

    # Step 6: refresh the index after all content writes are complete.
    _update_index(
        wiki_dir,
        doc_name,
        concept_names,
        doc_brief=doc_brief,
        concept_briefs=concept_briefs_map,
        doc_type=doc_type,
    )
    return CompileResult(
        doc_brief=doc_brief,
        created_concepts=created_count,
        updated_concepts=updated_count,
        related_concepts=len(sanitized_related),
    )


async def compile_short_doc_async(
    llm: Any,
    doc_name: str,
    source_path: Path,
    paths: WorkspacePaths,
    model: str,
    provider: str | None,
    *,
    language_override: str | None = None,
) -> CompileResult:
    """Compile a short source document into summary and concept pages."""
    # Step 1: load deterministic workspace settings and source text.
    config = load_config(paths.config_path)
    language = language_override or str(config.get("language", "en"))
    wiki_dir = paths.wiki_dir
    schema_md = get_schema_md(wiki_dir)
    content = source_path.read_text(encoding="utf-8")
    system_prompt = _SYSTEM_TEMPLATE.format(schema_md=schema_md, language=language)

    # Step 2: generate the summary page body and brief.
    summary_user = _SUMMARY_USER.format(doc_name=doc_name, content=content)
    summary_result = await _agenerate_conversation(
        llm,
        model,
        provider,
        summary_user,
        system_message=system_prompt,
        purpose=f"wiki.summary.{doc_name}",
    )
    summary_raw = summary_result.final_response

    # Step 3: tolerate imperfect JSON and still preserve the raw summary text.
    try:
        summary_parsed = _parse_json(summary_raw)
        if isinstance(summary_parsed, dict):
            doc_brief = str(summary_parsed.get("brief", ""))
            summary = str(summary_parsed.get("content", summary_raw))
        else:
            doc_brief = ""
            summary = summary_raw
    except (json.JSONDecodeError, ValueError):
        doc_brief = ""
        summary = summary_raw
    _write_summary(wiki_dir, doc_name, summary)

    # Step 4: reuse the summary conversation to plan and write concept pages.
    return await _compile_concepts_from_summary_async(
        llm,
        doc_name,
        paths,
        model,
        provider,
        system_prompt=system_prompt,
        summary_user=summary_user,
        summary=summary,
        doc_brief=doc_brief,
        doc_type="short",
        concept_generation_concurrency=int(config.get("concept_generation_concurrency", 1)),
    )


def compile_short_doc(
    doc_name: str,
    source_path: Path,
    paths: WorkspacePaths,
    model: str,
    provider: str | None,
    *,
    language_override: str | None = None,
) -> CompileResult:
    """Reject sync compilation because generation requires Hermes runtime LLM access."""
    del doc_name, source_path, paths, model, provider, language_override
    raise HermesRuntimeError(
        "compile_short_doc requires Hermes plugin LLM access. Use compile_short_doc_async(..., llm=ctx.llm) "
        "from plugin runtime instead."
    )


def _brief_from_description(description: str) -> str:
    """Trim a PageIndex description into the summary/index brief length."""
    cleaned = _clean_frontmatter_value(description)
    return cleaned[:97].rstrip() + "..." if len(cleaned) > 100 else cleaned


def _render_pageindex_summary(doc_name: str, page_count: int, description: str, structure: list[dict]) -> str:
    """Render the compact long-document summary stored in wiki/summaries/."""
    rendered_tree = render_tree(structure)
    return "\n".join(
        [
            "# Summary",
            "",
            description.strip(),
            "",
            "## PageIndex Structure",
            "",
            rendered_tree or "- (No structure available)",
            "",
            "## Retrieval Notes",
            "",
            f'Use `get_document_structure("{doc_name}")` for the complete tree and `get_page_content("{doc_name}", "5-8")` for details.',
            f"Fetch tight page ranges only. This PageIndex document has {page_count} pages.",
            "",
        ]
    )


async def compile_pageindex_doc_async(
    llm: Any,
    doc_name: str,
    raw_path: Path,
    paths: WorkspacePaths,
    model: str,
    provider: str | None,
    *,
    language_override: str | None = None,
) -> CompileResult:
    """Compile a long PDF through PageIndex into wiki summary and concepts."""
    # Step 1: load workspace compiler settings and schema guidance.
    config = load_config(paths.config_path)
    language = language_override or str(config.get("language", "en"))
    wiki_dir = paths.wiki_dir
    schema_md = get_schema_md(wiki_dir)
    system_prompt = _SYSTEM_TEMPLATE.format(schema_md=schema_md, language=language)

    # Step 2: build or load PageIndex state and render a compact summary.
    pageindex = await build_or_load_pageindex_async(llm, doc_name, raw_path, paths, model, provider, language=language)
    summary = _render_pageindex_summary(
        doc_name,
        pageindex.page_count,
        pageindex.doc_description,
        pageindex.structure,
    )
    doc_brief = _brief_from_description(pageindex.doc_description)

    # Step 3: write a pageindex summary that points full_text to source JSONL.
    _write_summary(
        wiki_dir,
        doc_name,
        summary,
        "pageindex",
        full_text=f"sources/{doc_name}.jsonl",
        extra_frontmatter={"pageindex_id": doc_name, "page_count": pageindex.page_count},
    )

    # Step 4: use the PageIndex summary as concept-generation context.
    summary_user = _PAGEINDEX_SUMMARY_USER.format(
        doc_name=doc_name,
        page_count=pageindex.page_count,
        summary=summary,
    )
    return await _compile_concepts_from_summary_async(
        llm,
        doc_name,
        paths,
        model,
        provider,
        system_prompt=system_prompt,
        summary_user=summary_user,
        summary=summary,
        doc_brief=doc_brief,
        doc_type="pageindex",
        concept_generation_concurrency=int(config.get("concept_generation_concurrency", 1)),
    )


def compile_pageindex_doc(
    doc_name: str,
    raw_path: Path,
    paths: WorkspacePaths,
    model: str,
    provider: str | None,
    *,
    language_override: str | None = None,
) -> CompileResult:
    """Reject sync PageIndex compilation because Hermes LLM access is async-only."""
    del doc_name, raw_path, paths, model, provider, language_override
    raise HermesRuntimeError(
        "compile_pageindex_doc requires Hermes plugin LLM access. Use compile_pageindex_doc_async(..., llm=ctx.llm) "
        "from plugin runtime instead."
    )
