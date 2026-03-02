"""Solo mode - single LLM call for simple queries."""

from openai import AsyncOpenAI


async def run(query: str, context: list[dict], config: dict) -> dict:
    """Execute a single LLM call.

    Args:
        query: User's question or request
        context: Conversation history [{role, content}, ...]
        config: amp configuration dict

    Returns:
        dict with keys: answer, mode, confidence
    """
    client = AsyncOpenAI(api_key=config["llm"]["api_key"])
    model = config["llm"]["model"]

    messages = [
        {
            "role": "system",
            "content": (
                "You are amp, a helpful personal assistant. "
                "Be concise, accurate, and helpful. "
                "Answer in the same language as the user's question."
            ),
        },
        *context,
        {"role": "user", "content": query},
    ]

    response = await client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.7,
    )

    answer = response.choices[0].message.content or ""

    return {
        "answer": answer,
        "mode": "solo",
        "confidence": None,
    }
