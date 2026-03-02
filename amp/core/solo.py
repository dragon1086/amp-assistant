"""Solo mode - single LLM call for simple queries."""

from amp.core.llm_factory import call_llm
from amp.core.emergent import _get_agent_cfg


def run(query: str, context: list[dict], config: dict) -> dict:
    """Execute a single LLM call using the configured provider.

    Args:
        query: User's question or request
        context: Conversation history [{role, content}, ...]
        config: amp configuration dict

    Returns:
        dict with keys: answer, mode, confidence
    """
    system = (
        "You are amp, a helpful personal assistant. "
        "Be concise, accurate, and helpful. "
        "Answer in the same language as the user's question."
    )

    # Include recent context in the prompt
    ctx_summary = ""
    if context:
        recent = context[-4:]
        ctx_summary = "\n\nConversation context:\n" + "\n".join(
            f"{m['role'].upper()}: {m['content'][:200]}" for m in recent
        )

    prompt = f"{ctx_summary}\n\nUser: {query}" if ctx_summary else query

    # config에서 provider/model 읽기 (agent_a 기준 — 기본값: anthropic_oauth)
    try:
        provider, model = _get_agent_cfg(config, "agent_a")
    except Exception:
        provider, model = "anthropic_oauth", "claude-sonnet-4-6"

    # OAuth fallback: 미로그인 시 openai로 자동 전환
    from amp.core.llm_factory import OAuthNotAvailableError
    fallback_model = config.get("llm", {}).get("model", "gpt-4o-mini")
    try:
        answer = call_llm(prompt, system=system, provider=provider, model=model)
        used_provider = provider
    except OAuthNotAvailableError:
        answer = call_llm(prompt, system=system, provider="openai", model=fallback_model)
        used_provider = "openai"

    return {
        "answer": answer,
        "mode": "solo",
        "model": f"{used_provider}/{model}",
        "confidence": None,
    }
