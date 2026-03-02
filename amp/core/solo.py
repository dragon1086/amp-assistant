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

    # config에서 provider/model 읽기 (agent_a 기준, fallback: openai)
    try:
        provider, model = _get_agent_cfg(config, "agent_a")
    except Exception:
        provider, model = "openai", "gpt-4o-mini"

    answer = call_llm(prompt, system=system, provider=provider, model=model)

    return {
        "answer": answer,
        "mode": "solo",
        "model": f"{provider}/{model}",
        "confidence": None,
    }
