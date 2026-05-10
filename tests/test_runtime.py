from __future__ import annotations

import sys
import types

import pytest

from hermes_wiki.runtime import HermesRuntimeError, generate_text


def test_generate_text_uses_run_agent_aiagent(monkeypatch) -> None:
    captured = {}

    class FakeAgent:
        def __init__(self, **kwargs):
            captured["kwargs"] = kwargs

        def chat(self, user_prompt: str) -> str:
            captured["user_prompt"] = user_prompt
            return " generated text "

    fake_module = types.SimpleNamespace(AIAgent=FakeAgent)
    monkeypatch.setitem(sys.modules, "run_agent", fake_module)

    result = generate_text("test/model", "system prompt", "user prompt")

    assert result == "generated text"
    assert captured["kwargs"]["model"] == "test/model"
    assert captured["kwargs"]["ephemeral_system_prompt"] == "system prompt"
    assert captured["kwargs"]["enabled_toolsets"] == []
    assert captured["user_prompt"] == "user prompt"


def test_generate_text_reports_missing_run_agent(monkeypatch) -> None:
    monkeypatch.delitem(sys.modules, "run_agent", raising=False)

    real_import = __import__

    def fake_import(name, *args, **kwargs):
        if name == "run_agent":
            raise ModuleNotFoundError("No module named 'run_agent'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)

    with pytest.raises(HermesRuntimeError) as exc_info:
        generate_text("test/model", "system", "user")

    assert "could not import run_agent.AIAgent" in str(exc_info.value)


def test_generate_text_reports_empty_response(monkeypatch) -> None:
    class FakeAgent:
        def __init__(self, **kwargs):
            pass

        def chat(self, user_prompt: str) -> str:
            return "  "

    fake_module = types.SimpleNamespace(AIAgent=FakeAgent)
    monkeypatch.setitem(sys.modules, "run_agent", fake_module)

    with pytest.raises(HermesRuntimeError) as exc_info:
        generate_text("test/model", "system", "user")

    assert "empty response" in str(exc_info.value)
