from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from .config import load_config
from .pageindex.builder import build_or_load_pageindex
from .pageindex.tree import render_tree
from .runtime import GenerationResult, generate_conversation, generate_text
from .schema import get_schema_md
from .workspace import WorkspacePaths

_SYSTEM_TEMPLATE = """\
You are Hermes Wiki's compilation agent for a personal knowledge base.

{schema_md}

Write all content in {language} language.
Use [[wikilinks]] to connect related pages such as [[concepts/attention]].
"""

_SUMMARY_USER = """\
New document: {doc_name}

Full text:
{content}

Write a summary page for this document in Markdown.

Return a JSON object with two keys:
- "brief": A single sentence under 100 characters describing the document's main contribution
- "content": The full summary in Markdown. Include key concepts, findings, and [[wikilinks]] to concepts that could become concept pages

Return ONLY valid JSON, no fences.
"""

_PAGEINDEX_SUMMARY_USER = """\
New long document: {doc_name}
Page count: {page_count}

Generated PageIndex summary:
{summary}

Based on this PageIndex summary and structure, decide concept updates. Do not assume access to full long-document text.
"""

_CONCEPTS_PLAN_USER = """\
Document name: {doc_name}

Based on the summary above, decide how to update the wiki's concept pages.

Existing concept pages:
{concept_briefs}

Return a JSON object with three keys:

1. "create" - new concepts not covered by any existing page. Array of objects:
   {{"name": "concept-slug", "title": "Human-Readable Title"}}

2. "update" - existing concepts that have significant new information from this document worth integrating. Array of objects:
   {{"name": "existing-slug", "title": "Existing Title"}}

3. "related" - existing concepts tangentially related to this document but not needing content changes. Array of slug strings.

Rules:
- For the first few documents, create at most 2-3 foundational concepts.
- Do not create a concept that overlaps with an existing one. Use "update" instead.
- Do not create concepts that are just the document topic itself.
- "related" is for lightweight cross-linking only.

Return ONLY valid JSON, no fences, no explanation.
"""

_CONCEPT_PAGE_USER = """\
Document name: {doc_name}

Based on the summary above, write the concept page for: {title}

Return a JSON object with two keys:
- "brief": A single sentence under 100 characters defining this concept
- "content": The full concept page in Markdown. Include clear explanation, key details from the source document, and [[wikilinks]] to related concepts and [[summaries/{doc_name}]]

Return ONLY valid JSON, no fences.
"""

_CONCEPT_UPDATE_USER = """\
Document name: {doc_name}

Based on the summary above, update the concept page for: {title}

Current content of this page:
{existing_content}

Integrate the new information naturally and rewrite the full page. Do not just append. Maintain existing [[wikilinks]] and add new ones where appropriate.

Return a JSON object with two keys:
- "brief": A single sentence under 100 characters defining this concept
- "content": The rewritten full concept page in Markdown

Return ONLY valid JSON, no fences.
"""

_SAFE_NAME_RE = re.compile(r"[^\w\-]")


@dataclass
class CompileResult:
    doc_brief: str
    created_concepts: int
    updated_concepts: int
    related_concepts: int


def _generate_text(model: str, provider: str | None, system_prompt: str, user_prompt: str) -> str:
    return generate_text(model, provider, system_prompt, user_prompt)


def _generate_conversation(
    model: str,
    provider: str | None,
    user_message: str,
    *,
    system_message: str | None = None,
    conversation_history: list[dict] | None = None,
    task_id: str | None = None,
) -> GenerationResult:
    return generate_conversation(
        model,
        provider,
        user_message,
        system_message=system_message,
        conversation_history=conversation_history,
        task_id=task_id,
    )


def _parse_json(text: str) -> list | dict:
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
    return " ".join(value.split())


def _read_concept_briefs(wiki_dir: Path) -> str:
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
    concepts_dir = wiki_dir / "concepts"
    concepts_dir.mkdir(parents=True, exist_ok=True)
    safe_name = _sanitize_concept_name(name)
    path = (concepts_dir / f"{safe_name}.md").resolve()
    if not path.is_relative_to(concepts_dir.resolve()):
        return

    brief = _clean_frontmatter_value(brief) if brief else ""
    if is_update and path.exists():
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

    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            content = content[end + 3 :].lstrip("\n")
    frontmatter_lines = [f"sources: [{source_file}]"]
    if brief:
        frontmatter_lines.append(f"brief: {brief}")
    frontmatter = "---\n" + "\n".join(frontmatter_lines) + "\n---\n\n"
    path.write_text(frontmatter + content, encoding="utf-8")


def _get_section_bounds(lines: list[str], heading: str) -> tuple[int, int] | None:
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
    bounds = _get_section_bounds(lines, heading)
    if bounds is None:
        return False
    start, end = bounds
    prefix = f"- {link}"
    return any(line.startswith(prefix) for line in lines[start:end])


def _replace_section_entry(lines: list[str], heading: str, link: str, entry: str) -> bool:
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
    bounds = _get_section_bounds(lines, heading)
    if bounds is None:
        return False
    start, _ = bounds
    lines.insert(start, entry)
    return True


def _add_related_link(wiki_dir: Path, concept_slug: str, doc_name: str, source_file: str) -> None:
    concepts_dir = wiki_dir / "concepts"
    path = concepts_dir / f"{concept_slug}.md"
    if not path.exists():
        return

    text = path.read_text(encoding="utf-8")
    link = f"[[summaries/{doc_name}]]"
    if link in text:
        return

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

    text += f"\n\nSee also: {link}"
    path.write_text(text, encoding="utf-8")


def _backlink_summary(wiki_dir: Path, doc_name: str, concept_slugs: list[str]) -> None:
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
    concept_briefs = concept_briefs or {}
    index_path = wiki_dir / "index.md"
    if not index_path.exists():
        index_path.write_text(
            "# Knowledge Base Index\n\n## Documents\n\n## Concepts\n\n## Explorations\n",
            encoding="utf-8",
        )

    lines = index_path.read_text(encoding="utf-8").split("\n")
    doc_link = f"[[summaries/{doc_name}]]"
    if not _section_contains_link(lines, "## Documents", doc_link):
        entry = f"- {doc_link} ({doc_type})"
        if doc_brief:
            entry += f" - {_clean_frontmatter_value(doc_brief)}"
        _insert_section_entry(lines, "## Documents", entry)

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


def _compile_concepts_from_summary(
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
) -> CompileResult:
    wiki_dir = paths.wiki_dir
    base_history = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": summary_user},
        {"role": "assistant", "content": summary},
    ]

    concept_briefs_text = _read_concept_briefs(wiki_dir)
    plan_result = _generate_conversation(
        model,
        provider,
        _CONCEPTS_PLAN_USER.format(
            doc_name=doc_name,
            concept_briefs=concept_briefs_text,
        ),
        conversation_history=base_history,
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

    create_items = plan["create"]
    update_items = plan["update"]
    related_items = plan["related"]
    if not create_items and not update_items and not related_items:
        _update_index(wiki_dir, doc_name, [], doc_brief=doc_brief, doc_type=doc_type)
        return CompileResult(doc_brief=doc_brief, created_concepts=0, updated_concepts=0, related_concepts=0)

    source_file = f"summaries/{doc_name}.md"
    concept_names: list[str] = []
    concept_briefs_map: dict[str, str] = {}
    created_count = 0
    updated_count = 0

    for concept in create_items:
        if not isinstance(concept, dict) or "name" not in concept:
            continue
        name = str(concept["name"])
        title = str(concept.get("title", name))
        result = _generate_conversation(
            model,
            provider,
            _CONCEPT_PAGE_USER.format(doc_name=doc_name, title=title),
            conversation_history=base_history,
        )
        raw = result.final_response
        try:
            parsed_page = _parse_json(raw)
            if isinstance(parsed_page, dict):
                brief = str(parsed_page.get("brief", ""))
                page_content = str(parsed_page.get("content", raw))
            else:
                brief = ""
                page_content = raw
        except (json.JSONDecodeError, ValueError):
            brief = ""
            page_content = raw
        _write_concept(wiki_dir, name, page_content, source_file, False, brief=brief)
        safe_name = _sanitize_concept_name(name)
        concept_names.append(safe_name)
        created_count += 1
        if brief:
            concept_briefs_map[safe_name] = brief

    for concept in update_items:
        if not isinstance(concept, dict) or "name" not in concept:
            continue
        name = str(concept["name"])
        title = str(concept.get("title", name))
        concept_path = wiki_dir / "concepts" / f"{_sanitize_concept_name(name)}.md"
        if concept_path.exists():
            raw_text = concept_path.read_text(encoding="utf-8")
            if raw_text.startswith("---"):
                parts = raw_text.split("---", 2)
                existing_content = parts[2].strip() if len(parts) >= 3 else raw_text
            else:
                existing_content = raw_text
        else:
            existing_content = "(page not found - create from scratch)"

        result = _generate_conversation(
            model,
            provider,
            _CONCEPT_UPDATE_USER.format(
                doc_name=doc_name,
                title=title,
                existing_content=existing_content,
            ),
            conversation_history=base_history,
        )
        raw = result.final_response
        try:
            parsed_page = _parse_json(raw)
            if isinstance(parsed_page, dict):
                brief = str(parsed_page.get("brief", ""))
                page_content = str(parsed_page.get("content", raw))
            else:
                brief = ""
                page_content = raw
        except (json.JSONDecodeError, ValueError):
            brief = ""
            page_content = raw
        _write_concept(wiki_dir, name, page_content, source_file, True, brief=brief)
        safe_name = _sanitize_concept_name(name)
        concept_names.append(safe_name)
        updated_count += 1
        if brief:
            concept_briefs_map[safe_name] = brief

    sanitized_related = [_sanitize_concept_name(str(item)) for item in related_items]
    for slug in sanitized_related:
        _add_related_link(wiki_dir, slug, doc_name, source_file)

    all_concept_slugs = concept_names + sanitized_related
    if all_concept_slugs:
        _backlink_summary(wiki_dir, doc_name, all_concept_slugs)
        _backlink_concepts(wiki_dir, doc_name, all_concept_slugs)

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


def compile_short_doc(
    doc_name: str,
    source_path: Path,
    paths: WorkspacePaths,
    model: str,
    provider: str | None,
    *,
    language_override: str | None = None,
) -> CompileResult:
    config = load_config(paths.config_path)
    language = language_override or str(config.get("language", "en"))
    wiki_dir = paths.wiki_dir
    schema_md = get_schema_md(wiki_dir)
    content = source_path.read_text(encoding="utf-8")
    system_prompt = _SYSTEM_TEMPLATE.format(schema_md=schema_md, language=language)

    summary_user = _SUMMARY_USER.format(doc_name=doc_name, content=content)
    summary_result = _generate_conversation(
        model,
        provider,
        summary_user,
        system_message=system_prompt,
    )
    summary_raw = summary_result.final_response
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
    return _compile_concepts_from_summary(
        doc_name,
        paths,
        model,
        provider,
        system_prompt=system_prompt,
        summary_user=summary_user,
        summary=summary,
        doc_brief=doc_brief,
        doc_type="short",
    )


def _brief_from_description(description: str) -> str:
    cleaned = _clean_frontmatter_value(description)
    return cleaned[:97].rstrip() + "..." if len(cleaned) > 100 else cleaned


def _render_pageindex_summary(doc_name: str, page_count: int, description: str, structure: list[dict]) -> str:
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


def compile_pageindex_doc(
    doc_name: str,
    raw_path: Path,
    paths: WorkspacePaths,
    model: str,
    provider: str | None,
    *,
    language_override: str | None = None,
) -> CompileResult:
    config = load_config(paths.config_path)
    language = language_override or str(config.get("language", "en"))
    wiki_dir = paths.wiki_dir
    schema_md = get_schema_md(wiki_dir)
    system_prompt = _SYSTEM_TEMPLATE.format(schema_md=schema_md, language=language)

    pageindex = build_or_load_pageindex(doc_name, raw_path, paths, model, provider, language=language)
    summary = _render_pageindex_summary(
        doc_name,
        pageindex.page_count,
        pageindex.doc_description,
        pageindex.structure,
    )
    doc_brief = _brief_from_description(pageindex.doc_description)
    _write_summary(
        wiki_dir,
        doc_name,
        summary,
        "pageindex",
        full_text=f"pageindex/{doc_name}",
        extra_frontmatter={"pageindex_id": doc_name, "page_count": pageindex.page_count},
    )
    summary_user = _PAGEINDEX_SUMMARY_USER.format(
        doc_name=doc_name,
        page_count=pageindex.page_count,
        summary=summary,
    )
    return _compile_concepts_from_summary(
        doc_name,
        paths,
        model,
        provider,
        system_prompt=system_prompt,
        summary_user=summary_user,
        summary=summary,
        doc_brief=doc_brief,
        doc_type="pageindex",
    )
