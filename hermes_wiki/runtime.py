from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class HermesRuntimeError(RuntimeError):
    """Raised when Hermes plugin LLM generation is unavailable or fails."""


@dataclass
class GenerationResult:
    final_response: str
    messages: list[dict]


_TRUST_GATE_HINT = (
    " Enable plugins.entries.hermes-wiki.llm.allow_provider_override and "
    "allow_model_override, and include the workspace provider/model in "
    "allowed_providers and allowed_models."
)


def _plugin_llm_unavailable_message() -> str:
    return (
        "Hermes plugin LLM access is unavailable. Run generation inside the Hermes plugin runtime "
        "with ctx.llm; the standalone hermes-wiki executable cannot generate wiki content."
    )


def _extract_text(result: Any) -> str:
    if isinstance(result, str):
        return result.strip()
    if isinstance(result, dict):
        return str(result.get("text") or result.get("final_response") or "").strip()
    return str(getattr(result, "text", "") or "").strip()


def _format_generation_error(exc: Exception, model: str, provider: str | None) -> str:
    detail = f"Hermes plugin LLM generation failed: {exc}"
    lowered = str(exc).lower()
    trust_markers = (
        "allow_provider_override",
        "allow_model_override",
        "allowed_providers",
        "allowed_models",
        "provider override",
        "model override",
        "provider_override",
        "model_override",
        "not allowed",
        "denied",
        "trust",
    )
    if any(marker in lowered for marker in trust_markers):
        detail += _TRUST_GATE_HINT
    if provider == "openai-codex" and model.startswith("openai/"):
        detail += (
            " For openai-codex, store the unprefixed model ID in .hermeskb/config.yaml "
            "(for example: model: gpt-5.4-mini, provider: openai-codex)."
        )
    return detail


async def agenerate_conversation(
    llm: Any,
    model: str,
    provider: str | None,
    user_message: str,
    *,
    system_message: str | None = None,
    conversation_history: list[dict] | None = None,
    purpose: str | None = None,
) -> GenerationResult:
    if llm is None:
        raise HermesRuntimeError(_plugin_llm_unavailable_message())

    messages = [dict(message) for message in conversation_history or []]
    if not messages and system_message:
        messages.append({"role": "system", "content": system_message})
    messages.append({"role": "user", "content": user_message})

    try:
        result = await llm.acomplete(
            messages=messages,
            provider=provider,
            model=model,
            temperature=0.0,
            purpose=purpose,
        )
    except HermesRuntimeError:
        raise
    except Exception as exc:
        raise HermesRuntimeError(_format_generation_error(exc, model, provider)) from exc

    text = _extract_text(result)
    if not text:
        raise HermesRuntimeError("Hermes plugin LLM returned an empty response.")
    return GenerationResult(
        final_response=text,
        messages=[*messages, {"role": "assistant", "content": text}],
    )


def generate_conversation(
    llm: Any,
    model: str,
    provider: str | None,
    user_message: str,
    *,
    system_message: str | None = None,
    conversation_history: list[dict] | None = None,
    purpose: str | None = None,
) -> GenerationResult:
    if llm is None:
        raise HermesRuntimeError(_plugin_llm_unavailable_message())

    messages = [dict(message) for message in conversation_history or []]
    if not messages and system_message:
        messages.append({"role": "system", "content": system_message})
    messages.append({"role": "user", "content": user_message})

    try:
        result = llm.complete(
            messages=messages,
            provider=provider,
            model=model,
            temperature=0.0,
            purpose=purpose,
        )
    except HermesRuntimeError:
        raise
    except Exception as exc:
        raise HermesRuntimeError(_format_generation_error(exc, model, provider)) from exc

    text = _extract_text(result)
    if not text:
        raise HermesRuntimeError("Hermes plugin LLM returned an empty response.")
    return GenerationResult(
        final_response=text,
        messages=[*messages, {"role": "assistant", "content": text}],
    )


async def agenerate_text(
    llm: Any,
    model: str,
    provider: str | None,
    system_prompt: str,
    user_prompt: str,
    *,
    purpose: str | None = None,
) -> str:
    return (
        await agenerate_conversation(
            llm,
            model,
            provider,
            user_prompt,
            system_message=system_prompt,
            purpose=purpose,
        )
    ).final_response


def generate_text(
    llm: Any,
    model: str,
    provider: str | None,
    system_prompt: str,
    user_prompt: str,
    *,
    purpose: str | None = None,
) -> str:
    return generate_conversation(
        llm,
        model,
        provider,
        user_prompt,
        system_message=system_prompt,
        purpose=purpose,
    ).final_response
