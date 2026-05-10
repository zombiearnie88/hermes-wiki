from __future__ import annotations


class HermesRuntimeError(RuntimeError):
    """Raised when Hermes runtime generation is unavailable or fails."""


def generate_text(model: str, system_prompt: str, user_prompt: str) -> str:
    try:
        from run_agent import AIAgent
    except ModuleNotFoundError as exc:
        raise HermesRuntimeError(
            "Hermes runtime is unavailable: could not import run_agent.AIAgent. "
            "Run this plugin inside a Hermes environment or install Hermes as a Python library."
        ) from exc

    try:
        agent = AIAgent(
            model=model,
            quiet_mode=True,
            skip_memory=True,
            skip_context_files=True,
            ephemeral_system_prompt=system_prompt,
            enabled_toolsets=[],
            max_iterations=1,
        )
        response = agent.chat(user_prompt)
    except Exception as exc:
        raise HermesRuntimeError(f"Hermes generation failed: {exc}") from exc

    text = (response or "").strip()
    if not text:
        raise HermesRuntimeError("Hermes generation returned an empty response.")
    return text
