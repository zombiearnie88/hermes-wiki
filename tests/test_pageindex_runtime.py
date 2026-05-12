from __future__ import annotations

import json

from hermes_wiki.pageindex import prompts
from hermes_wiki.runtime import GenerationResult


def test_pageindex_generate_text_uses_fresh_runtime_helper(monkeypatch) -> None:
    calls = []

    def fake_generate_conversation(
        model: str,
        provider: str | None,
        user_message: str,
        *,
        system_message: str | None = None,
        conversation_history: list[dict] | None = None,
        task_id: str | None = None,
    ) -> GenerationResult:
        calls.append(
            {
                "model": model,
                "provider": provider,
                "user_message": user_message,
                "system_message": system_message,
                "conversation_history": conversation_history,
                "task_id": task_id,
            }
        )
        return GenerationResult(final_response=" response ", messages=[])

    monkeypatch.setattr(prompts, "generate_conversation", fake_generate_conversation)

    result = prompts.pageindex_generate_text("test/model", "test-provider", "prompt")

    assert result == "response"
    assert len(calls) == 1
    assert calls[0]["model"] == "test/model"
    assert calls[0]["provider"] == "test-provider"
    assert calls[0]["conversation_history"] is None
    assert "PageIndex compiler" in calls[0]["system_message"]


def test_pageindex_generate_json_repairs_and_validates(monkeypatch) -> None:
    monkeypatch.setattr(
        prompts,
        "pageindex_generate_text",
        lambda model, provider, user_prompt, **kwargs: json.dumps({"ok": True}),
    )

    parsed = prompts.pageindex_generate_json(
        "test/model",
        None,
        "prompt",
        validator=lambda value: isinstance(value, dict) and value.get("ok") is True,
    )

    assert parsed == {"ok": True}
