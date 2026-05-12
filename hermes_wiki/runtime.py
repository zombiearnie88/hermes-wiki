from __future__ import annotations

from dataclasses import dataclass


class HermesRuntimeError(RuntimeError):
    """Raised when Hermes runtime generation is unavailable or fails."""


@dataclass
class GenerationResult:
    final_response: str
    messages: list[dict]


def generate_conversation(
    model: str,
    provider: str | None,
    user_message: str,
    *,
    system_message: str | None = None,
    conversation_history: list[dict] | None = None,
    task_id: str | None = None,
) -> GenerationResult:
    try:
        from run_agent import AIAgent
    except ModuleNotFoundError as exc:
        raise HermesRuntimeError(
            "Hermes runtime is unavailable: could not import run_agent.AIAgent. "
            "Run this plugin inside a Hermes environment or install Hermes as a Python library."
        ) from exc

    try:
        agent_kwargs = {
            "model": model,
            "quiet_mode": True,
            "skip_memory": True,
            "skip_context_files": True,
            "enabled_toolsets": [],
            "max_iterations": 1,
        }
        if system_message:
            agent_kwargs["ephemeral_system_prompt"] = system_message
        if provider:
            agent_kwargs["provider"] = provider
        agent = AIAgent(**agent_kwargs)
        history = [dict(message) for message in conversation_history] if conversation_history is not None else None
        result = agent.run_conversation(
            user_message=user_message,
            conversation_history=history,
            task_id=task_id,
        )
    except Exception as exc:
        detail = f"Hermes generation failed: {exc}"
        if provider == "openai-codex" and model.startswith("openai/"):
            detail += (
                " For openai-codex, store the unprefixed model ID in .hermeskb/config.yaml "
                "(for example: model: gpt-5.4-mini, provider: openai-codex)."
            )
        raise HermesRuntimeError(detail) from exc

    response = result.get("final_response") if isinstance(result, dict) else None
    text = (response or "").strip()
    if not text:
        raise HermesRuntimeError("Hermes generation returned an empty response.")
    messages = result.get("messages", []) if isinstance(result, dict) else []
    return GenerationResult(final_response=text, messages=list(messages or []))


def generate_text(model: str, provider: str | None, system_prompt: str, user_prompt: str) -> str:
    return generate_conversation(
        model,
        provider,
        user_prompt,
        system_message=system_prompt,
    ).final_response
