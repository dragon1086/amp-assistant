"""Solo mode - single LLM call for simple queries."""

from amp.core.emergent import _call_claude


def run(query: str, context: list[dict], config: dict) -> dict:
    """Execute a single LLM call via Claude OAuth.

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

    answer = _call_claude(f"{ctx_summary}\n\nUser: {query}" if ctx_summary else query, system=system)

    return {
        "answer": answer,
        "mode": "solo",
        "model": "claude-oauth",
        "confidence": None,
    }
