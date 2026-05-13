from __future__ import annotations

import unicodedata
from pathlib import Path


UNSPECIFIED_DOMAIN = "Unspecified. Ask the user to clarify the wiki domain before major ingest."


def _clean_domain(domain: str | None) -> str:
    if domain is None:
        return ""
    normalized = unicodedata.normalize("NFKD", " ".join(str(domain).split()))
    without_marks = "".join(char for char in normalized if not unicodedata.combining(char))
    return without_marks.encode("ascii", "xmlcharrefreplace").decode("ascii")


def build_schema_md(domain: str | None = None) -> str:
    domain_text = _clean_domain(domain) or UNSPECIFIED_DOMAIN
    domain_reference = _clean_domain(domain) or "the wiki domain once clarified"
    return f"""\
# Wiki Schema

## Domain
{domain_text}

## Domain Scope
- In scope: source material, concepts, claims, and relationships directly relevant to {domain_reference}.
- Out of scope: passing mentions, unrelated background, and topics that do not help explain {domain_reference}.
- When unsure, prefer summarizing the source document but do not create new concept pages unless the concept is central.

## Directory Structure
- raw/ - Local copies of ingested source files.
- wiki/sources/ - Document content for ingested files. Do not edit directly unless repairing conversion output.
- wiki/sources/images/ - Extracted or copied images referenced by source markdown.
- wiki/summaries/ - One summary page per source document.
- wiki/concepts/ - Cross-document concept pages synthesized over time.
- wiki/explorations/ - Saved analyses and ad hoc writeups worth keeping.
- wiki/reports/ - Generated reports and maintenance output.
- .hermeskb/ - Workspace config, hash registry, and runtime indexes. Do not edit unless repairing state.

## Special Files
- wiki/index.md - Main catalog of documents, concepts, and explorations.
- wiki/log.md - Append-only record of ingest operations and maintenance events.

## Page Types
- Summary pages describe one source document.
- PageIndex summary pages describe one long document and point detailed retrieval to PageIndex tools.
- Concept pages synthesize ideas across multiple documents.
- Index page lists pages with short descriptions.
- Log page records operations chronologically.

## Summary Frontmatter
- Short-document summaries use `doc_type: short` and `full_text: sources/{{doc_name}}.md`.
- PageIndex summaries use `doc_type: pageindex`, `pageindex_id: {{doc_name}}`, `full_text: pageindex/{{doc_name}}`, and `page_count`.

## PageIndex Summary Rules
- Include a concise model-generated document overview.
- Include compact page ranges and section titles so agents can choose retrieval ranges.
- Do not include full long-document text in summary pages.
- Mention `get_document_structure("{{doc_name}}")` and `get_page_content("{{doc_name}}", "5-8")` retrieval patterns.

## Content Rules
- Use [[wikilinks]] when linking to wiki pages.
- Keep pages focused and easy to scan.
- Do not emit YAML frontmatter in model output. Code manages frontmatter.
- Prefer explicit headings and concise bullets over long prose when possible.
- Ground summaries and concepts in the source material.
- Avoid creating broad generic concept pages unless they are central to {domain_reference}.

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
- Why it matters for {domain_reference}.
- Current state of knowledge.
- Open questions, debates, or limitations.
- Related summaries and concepts using [[wikilinks]].

"""


def build_agents_md() -> str:
    return """\
# Hermes Wiki Agent Guidance

You are operating over a Hermes Wiki workspace, a knowledge-base Q&A agent.
You answer questions by searching the wiki.

## Wiki Schema 
- The authoritative wiki content contract is `wiki/SCHEMA.md`.

## Search strategy
1. Read wiki/index.md to see all documents and concepts with brief summaries.
   Each document is marked (short) or (pageindex) to indicate its type.
2. Read relevant summary pages (summaries/) for document overviews.
   Summaries may omit details — if you need more, follow the summary's
   `full_text` frontmatter field to the source (see step 4).
3. Read concept pages (concepts/) for cross-document synthesis.
4. When you need detailed source document content, each summary page has a
   `full_text` frontmatter field with the path to the original document content:
   - Short documents (doc_type: short): read_file with that path.
   - PageIndex documents (doc_type: pageindex): use get_page_content(doc_name, pages)
     with tight page ranges. The summary shows document tree structure with page
     ranges to help you target. Never fetch the whole document.
5. Source content may reference images (e.g. ![image](sources/images/doc/file.png)).
    Use an image-viewing tool only if the current Hermes runtime registered one.
6. Synthesize a clear, concise, well-cited answer grounded in wiki content.

## Answering
- Ground answers in wiki summaries, concepts, and source content.
- Be concise and cite relevant wikilinks when helpful.
- Do not answer from outside knowledge unless the user explicitly asks for non-wiki context.
- If you cannot find relevant information, say so clearly.
"""


DEFAULT_SCHEMA_MD = build_schema_md()
DEFAULT_AGENTS_MD = build_agents_md()


def get_schema_md(wiki_dir: Path) -> str:
    schema_file = wiki_dir / "SCHEMA.md"
    if schema_file.exists():
        return schema_file.read_text(encoding="utf-8")
    return DEFAULT_SCHEMA_MD


def get_agents_md(wiki_dir: Path) -> str:
    workspace_root = wiki_dir.parent if wiki_dir.name == "wiki" else wiki_dir
    agents_file = workspace_root / "AGENTS.md"
    if agents_file.exists():
        return agents_file.read_text(encoding="utf-8")
    return DEFAULT_AGENTS_MD
