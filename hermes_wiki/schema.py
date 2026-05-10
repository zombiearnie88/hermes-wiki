from __future__ import annotations

from pathlib import Path

DEFAULT_AGENTS_MD = """\
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
"""


def get_agents_md(wiki_dir: Path) -> str:
    agents_file = wiki_dir / "AGENTS.md"
    if agents_file.exists():
        return agents_file.read_text(encoding="utf-8")
    return DEFAULT_AGENTS_MD
