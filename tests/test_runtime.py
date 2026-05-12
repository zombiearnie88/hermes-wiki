from __future__ import annotations

import sys
import types

import pytest

from hermes_wiki.runtime import HermesRuntimeError, generate_conversation, generate_text


def test_generate_conversation_uses_run_agent_aiagent(monkeypatch) -> None:
    captured = {}

    class FakeAgent:
        def __init__(self, **kwargs):
            captured["kwargs"] = kwargs

        def run_conversation(self, **kwargs) -> dict:
            captured["conversation_kwargs"] = kwargs
            return {
                "final_response": " generated text ",
                "messages": [{"role": "assistant", "content": "generated text"}],
            }

    fake_module = types.SimpleNamespace(AIAgent=FakeAgent)
    monkeypatch.setitem(sys.modules, "run_agent", fake_module)

    history = [{"role": "user", "content": "prior"}]
    result = generate_conversation(
        "test/model",
        "test-provider",
        "user prompt",
        system_message="system prompt",
        conversation_history=history,
        task_id="task-1",
    )

    assert result.final_response == "generated text"
    assert result.messages == [{"role": "assistant", "content": "generated text"}]
    assert captured["kwargs"]["model"] == "test/model"
    assert captured["kwargs"]["provider"] == "test-provider"
    assert captured["kwargs"]["enabled_toolsets"] == []
    assert captured["kwargs"]["quiet_mode"] is True
    assert captured["kwargs"]["skip_memory"] is True
    assert captured["kwargs"]["skip_context_files"] is True
    assert captured["kwargs"]["ephemeral_system_prompt"] == "system prompt"
    assert "system_message" not in captured["conversation_kwargs"]
    assert captured["conversation_kwargs"]["user_message"] == "user prompt"
    assert captured["conversation_kwargs"]["conversation_history"] == history
    assert captured["conversation_kwargs"]["conversation_history"] is not history
    assert captured["conversation_kwargs"]["task_id"] == "task-1"


def test_generate_text_wraps_conversation(monkeypatch) -> None:
    captured = {}

    class FakeAgent:
        def __init__(self, **kwargs):
            captured["kwargs"] = kwargs

        def run_conversation(self, **kwargs) -> dict:
            captured["conversation_kwargs"] = kwargs
            return {"final_response": " generated text ", "messages": []}

    fake_module = types.SimpleNamespace(AIAgent=FakeAgent)
    monkeypatch.setitem(sys.modules, "run_agent", fake_module)

    result = generate_text("test/model", None, "system prompt", "user prompt")

    assert result == "generated text"
    assert "provider" not in captured["kwargs"]
    assert captured["kwargs"]["ephemeral_system_prompt"] == "system prompt"
    assert "system_message" not in captured["conversation_kwargs"]
    assert captured["conversation_kwargs"]["user_message"] == "user prompt"
    assert captured["conversation_kwargs"]["conversation_history"] is None


def test_generate_text_reports_missing_run_agent(monkeypatch) -> None:
    monkeypatch.delitem(sys.modules, "run_agent", raising=False)

    real_import = __import__

    def fake_import(name, *args, **kwargs):
        if name == "run_agent":
            raise ModuleNotFoundError("No module named 'run_agent'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)

    with pytest.raises(HermesRuntimeError) as exc_info:
        generate_text("test/model", "test-provider", "system", "user")

    assert "could not import run_agent.AIAgent" in str(exc_info.value)


def test_generate_text_reports_empty_response(monkeypatch) -> None:
    class FakeAgent:
        def __init__(self, **kwargs):
            pass

        def run_conversation(self, **kwargs) -> dict:
            return {"final_response": "  ", "messages": []}

    fake_module = types.SimpleNamespace(AIAgent=FakeAgent)
    monkeypatch.setitem(sys.modules, "run_agent", fake_module)

    with pytest.raises(HermesRuntimeError) as exc_info:
        generate_text("test/model", "test-provider", "system", "user")

    assert "empty response" in str(exc_info.value)


def test_generate_text_wraps_agent_errors(monkeypatch) -> None:
    class FakeAgent:
        def __init__(self, **kwargs):
            pass

        def run_conversation(self, **kwargs) -> dict:
            raise ValueError("boom")

    fake_module = types.SimpleNamespace(AIAgent=FakeAgent)
    monkeypatch.setitem(sys.modules, "run_agent", fake_module)

    with pytest.raises(HermesRuntimeError) as exc_info:
        generate_text("test/model", "test-provider", "system", "user")

    assert "Hermes generation failed: boom" in str(exc_info.value)


def test_generate_text_suggests_codex_model_without_openai_prefix(monkeypatch) -> None:
    class FakeAgent:
        def __init__(self, **kwargs):
            raise ValueError("model is not supported")

    fake_module = types.SimpleNamespace(AIAgent=FakeAgent)
    monkeypatch.setitem(sys.modules, "run_agent", fake_module)

    with pytest.raises(HermesRuntimeError) as exc_info:
        generate_text("openai/gpt-5.4-mini", "openai-codex", "system", "user")

    assert "model: gpt-5.4-mini, provider: openai-codex" in str(exc_info.value)
