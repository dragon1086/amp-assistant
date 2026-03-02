"""Emergent mode - 2-agent independent analysis with reconciliation.

The killer feature of amp: two agents independently analyze a query,
then a reconciler synthesizes agreements and conflicts into a better answer
than either agent could produce alone.

Key invariant: Agent A and Agent B MUST NOT see each other's output.
This independence is what creates emergence.
"""

import os
import subprocess

from amp.core.metrics import calculate_cser


def _call_openai(prompt: str, system: str) -> str:
    """Single LLM call via OpenAI API."""
    import openai as _openai
    client = _openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    response = client.responses.create(
        model="gpt-5.2",
        instructions=system,
        input=prompt,
    )
    return response.output_text


def _call_anthropic(prompt: str, system: str) -> str:
    """Single LLM call via claude CLI subprocess."""
    oauth_token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "")
    full_prompt = f"{system}\n\n{prompt}"
    # Strip Claude Code session vars that block nested invocations
    env = {k: v for k, v in os.environ.items()
           if k not in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS")}
    env["CLAUDE_CODE_OAUTH_TOKEN"] = oauth_token
    result = subprocess.run(
        ["claude", "-p", "--dangerously-skip-permissions", full_prompt],
        capture_output=True, text=True, timeout=60,
        env=env
    )
    return result.stdout.strip()


def run(query: str, context: list[dict], config: dict) -> dict:
    """Execute emergent 2-agent analysis.

    Stages:
      1. Agent A (analyst)  — OpenAI
      2. Agent B (critic)   — Anthropic (does NOT see A's output)
      3. Reconciler sees both → synthesizes (OpenAI)
      4. Verifier checks logic consistency (OpenAI)

    Args:
        query: User's question or request
        context: Conversation history
        config: amp configuration dict

    Returns:
        dict with keys: answer, mode, agent_a, agent_b, cser, confidence,
                        agreements, conflicts
    """
    # Build context summary (shared background, NOT agent outputs)
    ctx_summary = ""
    if context:
        recent = context[-4:]
        ctx_summary = "\n\nConversation context:\n" + "\n".join(
            f"{m['role'].upper()}: {m['content'][:300]}" for m in recent
        )

    agent_a_system = (
        "You are an analytical expert (Agent A). Your role is to propose a thorough, "
        "well-structured answer. Focus on identifying key insights, opportunities, "
        "and constructive recommendations. Think from first principles. "
        "Answer in the same language as the user's question."
    )

    agent_b_system = (
        "You are a critical expert (Agent B). Your role is to independently analyze "
        "the question from a skeptical, adversarial perspective. Identify risks, "
        "flaws, edge cases, and potential problems. Challenge assumptions. "
        "Answer in the same language as the user's question."
    )

    agent_a_prompt = f"Analyze this question and provide your expert assessment:{ctx_summary}\n\nQuestion: {query}"
    agent_b_prompt = f"Critically analyze this question from a skeptical perspective:{ctx_summary}\n\nQuestion: {query}"

    # Stage 1: Agent A via OpenAI
    agent_a_text = _call_openai(agent_a_prompt, agent_a_system)

    # Stage 2: Agent B via Anthropic (does NOT see A's output)
    agent_b_text = _call_anthropic(agent_b_prompt, agent_b_system)

    # Stage 3: Reconciler sees both outputs
    cser_data = calculate_cser(agent_a_text, agent_b_text)

    reconciler_prompt = f"""You have received independent analyses from two expert agents on the same question.

Original question: {query}

[Agent A - Analyst]:
{agent_a_text}

[Agent B - Critic]:
{agent_b_text}

Your task:
1. Identify points where both agents AGREE (list as agreements)
2. Identify points where they DISAGREE or have different perspectives (list as conflicts)
3. Synthesize a final, balanced answer that captures the best insights from both

Format your response as:
AGREEMENTS:
- [agreement points]

CONFLICTS:
- [conflict points]

SYNTHESIZED ANSWER:
[your final synthesized answer in the same language as the original question]"""

    reconciled_raw = _call_openai(
        reconciler_prompt,
        "You are a master synthesizer. You receive two independent expert analyses and produce a superior unified answer that captures the best of both perspectives. Answer in the same language as the original question.",
    )

    # Parse reconciler output
    agreements, conflicts, synthesized = _parse_reconciliation(reconciled_raw)

    # Stage 4: Verifier checks logical consistency
    verifier_prompt = f"""Check the following answer for logical consistency, completeness, and accuracy.

Original question: {query}

Answer to verify:
{synthesized}

If the answer is logically consistent and complete, output it as-is with "VERIFIED: " prefix.
If you find issues, output the corrected version with "CORRECTED: " prefix.
Answer in the same language as the original question."""

    verified_raw = _call_openai(
        verifier_prompt,
        "You are a logical consistency checker. Verify answers for correctness. Answer in the same language as the original question.",
    )

    # Extract final answer
    final_answer = _extract_verified(verified_raw, synthesized)

    return {
        "answer": final_answer,
        "mode": "emergent",
        "agent_a": agent_a_text,
        "agent_b": agent_b_text,
        "cser": cser_data["cser"],
        "confidence": cser_data["confidence"],
        "agreements": agreements,
        "conflicts": conflicts,
    }


def _parse_reconciliation(text: str) -> tuple[list[str], list[str], str]:
    """Parse reconciler output into agreements, conflicts, and synthesized answer."""
    agreements = []
    conflicts = []
    synthesized = text  # fallback

    lines = text.split("\n")
    current_section = None

    for line in lines:
        stripped = line.strip()
        upper = stripped.upper()

        if "AGREEMENTS:" in upper or "AGREEMENT:" in upper:
            current_section = "agreements"
        elif "CONFLICTS:" in upper or "CONFLICT:" in upper:
            current_section = "conflicts"
        elif "SYNTHESIZED ANSWER:" in upper or "FINAL ANSWER:" in upper or "SYNTHESIS:" in upper:
            current_section = "synthesis"
            synthesized = ""
        elif current_section == "agreements" and stripped.startswith("-"):
            item = stripped.lstrip("- ").strip()
            if item:
                agreements.append(item)
        elif current_section == "conflicts" and stripped.startswith("-"):
            item = stripped.lstrip("- ").strip()
            if item:
                conflicts.append(item)
        elif current_section == "synthesis" and stripped:
            synthesized += line + "\n"

    synthesized = synthesized.strip()
    if not synthesized:
        # Fallback: use full text
        synthesized = text

    return agreements, conflicts, synthesized


def _extract_verified(verified_raw: str, fallback: str) -> str:
    """Extract the final answer from verifier output."""
    for prefix in ("VERIFIED:", "CORRECTED:", "VERIFIED: ", "CORRECTED: "):
        if verified_raw.upper().startswith(prefix.upper()):
            return verified_raw[len(prefix):].strip()

    # If verifier didn't use expected format, return its full response
    if len(verified_raw.strip()) > 50:
        return verified_raw.strip()

    return fallback
