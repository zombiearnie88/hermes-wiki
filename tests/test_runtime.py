from __future__ import annotations

import asyncio
import types

import pytest

from hermes_wiki.runtime import HermesRuntimeError, agenerate_conversation, generate_text


def test_agenerate_conversation_calls_plugin_llm_acomplete() -> None:
    captured = {}

    class FakeLLM:
        async def acomplete(self, **kwargs):
            captured.update(kwargs)
            return types.SimpleNamespace(text=" generated text ")

    result = asyncio.run(
        agenerate_conversation(
            FakeLLM(),
            "test/model",
            "test-provider",
            "user prompt",
            system_message="system prompt",
            purpose="wiki.summary.doc",
        )
    )

    assert result.final_response == "generated text"
    assert result.messages == [
        {"role": "system", "content": "system prompt"},
        {"role": "user", "content": "user prompt"},
        {"role": "assistant", "content": "generated text"},
    ]
    assert captured["model"] == "test/model"
    assert captured["provider"] == "test-provider"
    assert captured["temperature"] == 0.0
    assert captured["purpose"] == "wiki.summary.doc"
    assert captured["messages"] == [
        {"role": "system", "content": "system prompt"},
        {"role": "user", "content": "user prompt"},
    ]


def test_agenerate_conversation_uses_copied_history() -> None:
    captured = {}

    class FakeLLM:
        async def acomplete(self, **kwargs):
            captured.update(kwargs)
            return types.SimpleNamespace(text="response")

    history = [{"role": "system", "content": "base"}]

    result = asyncio.run(
        agenerate_conversation(
            FakeLLM(),
            "test/model",
            None,
            "next",
            system_message="ignored",
            conversation_history=history,
        )
    )

    assert result.final_response == "response"
    assert captured["messages"] == [
        {"role": "system", "content": "base"},
        {"role": "user", "content": "next"},
    ]
    assert captured["messages"] is not history


def test_generate_text_wraps_sync_plugin_llm_complete() -> None:
    captured = {}

    class FakeLLM:
        def complete(self, **kwargs):
            captured.update(kwargs)
            return types.SimpleNamespace(text=" generated text ")

    result = generate_text(FakeLLM(), "test/model", None, "system prompt", "user prompt", purpose="wiki.pageindex")

    assert result == "generated text"
    assert captured["messages"] == [
        {"role": "system", "content": "system prompt"},
        {"role": "user", "content": "user prompt"},
    ]
    assert captured["provider"] is None
    assert captured["model"] == "test/model"
    assert captured["temperature"] == 0.0
    assert captured["purpose"] == "wiki.pageindex"


def test_agenerate_conversation_reports_missing_plugin_llm() -> None:
    with pytest.raises(HermesRuntimeError) as exc_info:
        asyncio.run(agenerate_conversation(None, "test/model", "test-provider", "user"))

    assert "plugin LLM access is unavailable" in str(exc_info.value)
    assert "standalone hermes-wiki" in str(exc_info.value)


def test_agenerate_conversation_reports_empty_response() -> None:
    class FakeLLM:
        async def acomplete(self, **kwargs):
            return types.SimpleNamespace(text="  ")

    with pytest.raises(HermesRuntimeError) as exc_info:
        asyncio.run(agenerate_conversation(FakeLLM(), "test/model", "test-provider", "user"))

    assert "empty response" in str(exc_info.value)


def test_agenerate_conversation_wraps_trust_gate_errors() -> None:
    class FakeLLM:
        async def acomplete(self, **kwargs):
            raise ValueError("provider override is not allowed")

    with pytest.raises(HermesRuntimeError) as exc_info:
        asyncio.run(agenerate_conversation(FakeLLM(), "test/model", "test-provider", "user"))

    message = str(exc_info.value)
    assert "Hermes plugin LLM generation failed" in message
    assert "allow_provider_override" in message
    assert "allow_model_override" in message


def test_agenerate_conversation_suggests_codex_model_without_openai_prefix() -> None:
    class FakeLLM:
        async def acomplete(self, **kwargs):
            raise ValueError("model is not supported")

    with pytest.raises(HermesRuntimeError) as exc_info:
        asyncio.run(agenerate_conversation(FakeLLM(), "openai/gpt-5.4-mini", "openai-codex", "user"))

    assert "model: gpt-5.4-mini, provider: openai-codex" in str(exc_info.value)
