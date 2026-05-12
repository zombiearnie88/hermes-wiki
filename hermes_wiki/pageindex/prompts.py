from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from ..runtime import generate_conversation


_SYSTEM_PROMPT = """\
You are Hermes Wiki's PageIndex compiler for long documents.
Write deterministic, concise output grounded only in the provided page text or structure.
Do not invent sections or facts that are not supported by the input.
"""


def _parse_json(text: str) -> list[Any] | dict[str, Any]:
    try:
        from json_repair import repair_json
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "json-repair is required to parse PageIndex responses. Install json-repair in the runtime environment."
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


def pageindex_generate_text(
    model: str,
    provider: str | None,
    user_prompt: str,
    *,
    system_prompt: str = _SYSTEM_PROMPT,
    conversation_history: list[dict] | None = None,
    retries: int = 2,
) -> str:
    last_error: Exception | None = None
    for _ in range(max(1, retries)):
        try:
            return generate_conversation(
                model,
                provider,
                user_prompt,
                system_message=system_prompt,
                conversation_history=conversation_history,
            ).final_response.strip()
        except Exception as exc:
            last_error = exc
    assert last_error is not None
    raise last_error


def pageindex_generate_json(
    model: str,
    provider: str | None,
    user_prompt: str,
    *,
    system_prompt: str = _SYSTEM_PROMPT,
    validator: Callable[[list[Any] | dict[str, Any]], bool] | None = None,
    retries: int = 2,
) -> list[Any] | dict[str, Any]:
    last_error: Exception | None = None
    for _ in range(max(1, retries)):
        try:
            parsed = _parse_json(pageindex_generate_text(model, provider, user_prompt, system_prompt=system_prompt, retries=1))
            if validator is None or validator(parsed):
                return parsed
            last_error = ValueError("PageIndex JSON response failed validation.")
        except Exception as exc:
            last_error = exc
    assert last_error is not None
    raise last_error


def node_summary_prompt(title: str, start_page: int, end_page: int, text: str, language: str) -> str:
    return f"""\
Document section: {title}
Page range: {start_page}-{end_page}

Section text:
{text}

Write a concise summary of the main points covered in this section.
Use {language} language.
Return only the summary text, with no Markdown fence.
"""


def document_description_prompt(doc_name: str, rendered_tree: str, language: str) -> str:
    return f"""\
Document name: {doc_name}

PageIndex structure with section summaries:
{rendered_tree}

Write a concise overview of the whole document in {language} language.
Mention the document's main subject, scope, and notable sections.
Return only Markdown body content suitable under a '# Summary' heading.
"""
