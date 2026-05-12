from __future__ import annotations

from pathlib import Path

DEFAULT_AGENTS_MD = """\

You are Hermes-Wiki, a knowledge-base Q&A agent. You answer questions by searching the wiki.

# Wiki Schema

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
- Concept pages synthesize ideas across multiple documents.
- Index page lists pages with short descriptions.
- Log page records operations chronologically.

## Content Rules
- Use [[wikilinks]] when linking to wiki pages.
- Keep pages focused and easy to scan.
- Do not emit YAML frontmatter in model output. Code manages frontmatter.
- Prefer explicit headings and concise bullets over long prose when possible.

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
   - PageIndex documents (doc_type: pageindex): use get_document_structure(doc_name)
     to inspect the complete tree, then use get_page_content(doc_name, pages)
     with tight page ranges. Never fetch the whole document.
5. Source content may reference images (e.g. ![image](sources/images/doc/file.png)).
   Use the get_image tool to view them when needed.
6. Synthesize a clear, concise, well-cited answer grounded in wiki content.

Answer based only on wiki content. Be concise.
Before each tool call, output one short sentence explaining the reason.

If you cannot find relevant information, say so clearly.
"""

DEFAULT_SCHEMA_MD = """\
# Wiki Schema

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
"""


def get_schema_md(wiki_dir: Path) -> str:
    schema_file = wiki_dir / "SCHEMA.md"
    if schema_file.exists():
        return schema_file.read_text(encoding="utf-8")
    return DEFAULT_SCHEMA_MD


def get_agents_md(wiki_dir: Path) -> str:
    agents_file = wiki_dir / "AGENTS.md"
    if agents_file.exists():
        return agents_file.read_text(encoding="utf-8")
    return DEFAULT_AGENTS_MD
