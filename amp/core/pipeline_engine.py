"""Pipeline mode - structured plan → solve → review → fix workflow.

4-stage LLM pipeline for complex structured tasks like code generation,
document creation, and step-by-step problem solving.
"""

from openai import AsyncOpenAI


async def _call(
    client: AsyncOpenAI,
    model: str,
    system: str,
    user: str,
    temperature: float = 0.7,
) -> str:
    """Single LLM call helper."""
    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
    )
    return response.choices[0].message.content or ""


async def run(query: str, context: list[dict], config: dict) -> dict:
    """Execute 4-stage pipeline: plan → solve → review → fix.

    Args:
        query: User's task request
        context: Conversation history
        config: amp configuration dict

    Returns:
        dict with keys: answer, mode, steps
    """
    client = AsyncOpenAI(api_key=config["llm"]["api_key"])
    model = config["llm"]["model"]

    # Build context summary for pipeline
    ctx_summary = ""
    if context:
        recent = context[-4:]  # last 2 exchanges
        ctx_summary = "\n".join(
            f"{m['role'].upper()}: {m['content'][:200]}" for m in recent
        )
        ctx_summary = f"\n\nConversation context:\n{ctx_summary}\n"

    steps = {}

    # Stage 1: Planner
    plan = await _call(
        client,
        model,
        "You are a precise task planner. Break complex tasks into clear, numbered steps. Be specific and actionable.",
        f"Break this task into detailed steps:{ctx_summary}\n\nTask: {query}",
        temperature=0.3,
    )
    steps["plan"] = plan

    # Stage 2: Solver
    solution = await _call(
        client,
        model,
        "You are an expert problem solver. Execute the given plan thoroughly and completely. Answer in the same language as the task.",
        f"Execute this plan to solve the original task.\n\nOriginal task: {query}\n\nPlan:\n{plan}\n\nProvide the complete solution:",
        temperature=0.7,
    )
    steps["solution"] = solution

    # Stage 3: Reviewer
    review = await _call(
        client,
        model,
        "You are a rigorous code and solution reviewer. Find all flaws, gaps, errors, and improvements. Be specific.",
        f"Review this solution for flaws, errors, or gaps.\n\nOriginal task: {query}\n\nSolution:\n{solution}\n\nList specific issues found:",
        temperature=0.3,
    )
    steps["review"] = review

    # Stage 4: Fixer
    fixed = await _call(
        client,
        model,
        "You are an expert who produces polished final solutions. Fix all identified issues and deliver a complete, correct answer. Answer in the same language as the original task.",
        f"Fix the solution based on review feedback. Produce the final, corrected version.\n\nOriginal task: {query}\n\nOriginal solution:\n{solution}\n\nIssues to fix:\n{review}\n\nFinal corrected solution:",
        temperature=0.7,
    )
    steps["fixed"] = fixed

    return {
        "answer": fixed,
        "mode": "pipeline",
        "steps": steps,
    }
