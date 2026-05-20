from __future__ import annotations

import asyncio
import json

from hermes_wiki.pageindex import prompts
from hermes_wiki.runtime import GenerationResult


def test_pageindex_generate_text_uses_async_runtime_helper(monkeypatch) -> None:
    calls = []

    async def fake_generate_conversation(
        llm,
        model: str,
        provider: str | None,
        user_message: str,
        *,
        system_message: str | None = None,
        conversation_history: list[dict] | None = None,
        purpose: str | None = None,
    ) -> GenerationResult:
        calls.append(
            {
                "llm": llm,
                "model": model,
                "provider": provider,
                "user_message": user_message,
                "system_message": system_message,
                "conversation_history": conversation_history,
                "purpose": purpose,
            }
        )
        return GenerationResult(final_response=" response ", messages=[])

    monkeypatch.setattr(prompts, "agenerate_conversation", fake_generate_conversation)

    result = asyncio.run(
        prompts.pageindex_generate_text_async("fake-llm", "test/model", "test-provider", "prompt", purpose="wiki.pageindex")
    )

    assert result == "response"
    assert len(calls) == 1
    assert calls[0]["llm"] == "fake-llm"
    assert calls[0]["model"] == "test/model"
    assert calls[0]["provider"] == "test-provider"
    assert calls[0]["conversation_history"] is None
    assert calls[0]["purpose"] == "wiki.pageindex"
    assert "PageIndex compiler" in calls[0]["system_message"]


def test_pageindex_generate_json_repairs_and_validates(monkeypatch) -> None:
    async def fake_generate_text(llm, model, provider, user_prompt, **kwargs):
        return json.dumps({"ok": True})

    monkeypatch.setattr(prompts, "pageindex_generate_text_async", fake_generate_text)

    parsed = asyncio.run(
        prompts.pageindex_generate_json_async(
            "fake-llm",
            "test/model",
            None,
            "prompt",
            validator=lambda value: isinstance(value, dict) and value.get("ok") is True,
        )
    )

    assert parsed == {"ok": True}
