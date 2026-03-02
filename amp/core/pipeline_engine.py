"""Pipeline mode - structured plan → solve → review → fix workflow.

4-stage LLM pipeline for complex structured tasks like code generation,
document creation, and step-by-step problem solving.
"""

from amp.core.llm_factory import call_llm
from amp.core.emergent import _get_agent_cfg


def run(query: str, context: list[dict], config: dict) -> dict:
    """Execute 4-stage pipeline: plan → solve → review → fix.

    Args:
        query: User's task request
        context: Conversation history
        config: amp configuration dict

    Returns:
        dict with keys: answer, mode, steps
    """
    # config에서 provider/model 읽기 (agent_a 기준, fallback: openai)
    try:
        provider, model = _get_agent_cfg(config, "agent_a")
    except Exception:
        provider, model = "openai", "gpt-4o-mini"

    AMP_CONTEXT = (
        "You are amp — a local AI assistant running on the user's own machine. "
        "amp is a personal decision-support and coding assistant with 2-agent debate capability. "
        "amp has full access to the local filesystem, can execute shell commands, run scripts, "
        "spawn Claude Code or other tools, read/write files, and interact with local services. "
        "amp is orchestrated by OpenClaw (another local AI agent) and communicates via Telegram. "
        "When the user asks what amp can do, always answer based on these actual capabilities. "
        "Answer in the same language as the user's message."
    )

    def _call(prompt: str, system: str) -> str:
        full_system = f"{AMP_CONTEXT}\n\n{system}"
        return call_llm(prompt, system=full_system, provider=provider, model=model)

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
    plan = _call(
        f"Break this task into detailed steps:{ctx_summary}\n\nTask: {query}",
        system="You are a precise task planner. Break complex tasks into clear, numbered steps. Be specific and actionable.",
    )
    steps["plan"] = plan

    # Stage 2: Solver
    solution = _call(
        f"Execute this plan to solve the original task.\n\nOriginal task: {query}\n\nPlan:\n{plan}\n\nProvide the complete solution:",
        system="You are an expert problem solver. Execute the given plan thoroughly and completely. Answer in the same language as the task.",
    )
    steps["solution"] = solution

    # Stage 3: Reviewer
    review = _call(
        f"Review this solution for flaws, errors, or gaps.\n\nOriginal task: {query}\n\nSolution:\n{solution}\n\nList specific issues found:",
        system="You are a rigorous code and solution reviewer. Find all flaws, gaps, errors, and improvements. Be specific.",
    )
    steps["review"] = review

    # Stage 4: Fixer
    fixed = _call(
        f"Fix the solution based on review feedback. Produce the final, corrected version.\n\nOriginal task: {query}\n\nOriginal solution:\n{solution}\n\nIssues to fix:\n{review}\n\nFinal corrected solution:",
        system="You are an expert who produces polished final solutions. Fix all identified issues and deliver a complete, correct answer. Answer in the same language as the original task.",
    )
    steps["fixed"] = fixed

    return {
        "answer": fixed,
        "mode": "pipeline",
        "steps": steps,
    }
