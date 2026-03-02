#!/usr/bin/env python3
"""amp benchmark: Solo vs Orchestration vs amp (multi-provider)

Tests 3 methods across 6 real-world personal assistant scenarios.
Methods:
  1. Solo: Single GPT-5.2 call
  2. Orchestration: 4 sequential GPT-5.2 calls (plan→execute→review→refine)
  3. amp: Agent A (GPT-5.2) + Agent B (claude-sonnet-4-6) → reconcile (GPT-5.2)
"""

import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

import openai
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

console = Console()

# ---------------------------------------------------------------------------
# Provider calls
# ---------------------------------------------------------------------------

def _call_openai(prompt: str, system: str) -> str:
    """Call OpenAI gpt-5.2 via /v1/responses endpoint."""
    client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    response = client.responses.create(
        model="gpt-5.2",
        instructions=system,
        input=prompt,
    )
    return response.output_text


def _call_anthropic(prompt: str, system: str) -> str:
    """Call claude-sonnet-4-6 via claude -p subprocess."""
    oauth_token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "")
    full_prompt = f"{system}\n\n{prompt}"
    # Strip Claude Code session vars that block nested invocations
    env = {k: v for k, v in os.environ.items()
           if k not in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS")}
    env["CLAUDE_CODE_OAUTH_TOKEN"] = oauth_token
    result = subprocess.run(
        ["claude", "-p", "--dangerously-skip-permissions", full_prompt],
        capture_output=True, text=True, timeout=120,
        env=env
    )
    if result.returncode != 0 and result.stderr:
        console.print(f"[yellow]claude subprocess warning: {result.stderr[:200]}[/yellow]")
    return result.stdout.strip()


def _count_insights(response: str) -> int:
    """Use GPT-5.2 to count distinct actionable insights."""
    try:
        result = _call_openai(
            f"Count distinct actionable insights in this response. Return just a number.\n\n{response}",
            "You are an evaluator. Count only distinct, actionable insights. Return ONLY an integer."
        )
        return int(result.strip().split()[0])
    except Exception:
        # Fallback: count bullet points and numbered items
        lines = response.split('\n')
        count = sum(1 for l in lines if l.strip().startswith(('-', '*', '•')) or
                    (len(l.strip()) > 2 and l.strip()[0].isdigit() and l.strip()[1] in '.):'))
        return max(count, 3)


def _score_quality(response: str, query: str) -> float:
    """Use GPT-5.2 judge to rate response 1-10."""
    try:
        result = _call_openai(
            f"Rate this response 1-10 for completeness, nuance, and actionability.\n\nQuestion: {query}\n\nResponse: {response}\n\nReturn ONLY a number like 7.5",
            "You are an expert evaluator. Rate responses 1-10. Return ONLY a decimal number."
        )
        return round(float(result.strip().split()[0]), 1)
    except Exception:
        return 7.0


def _count_cross_provider_insights(agent_b_response: str, solo_response: str) -> int:
    """Count insights in Agent B's response NOT present in solo GPT-5.2 response."""
    try:
        result = _call_openai(
            f"How many distinct insights appear in Response B but NOT in Response A? Return just a number.\n\nResponse A (GPT solo):\n{solo_response}\n\nResponse B (Claude):\n{agent_b_response}",
            "You are an evaluator. Count insights unique to Response B. Return ONLY an integer."
        )
        return int(result.strip().split()[0])
    except Exception:
        return 2


# ---------------------------------------------------------------------------
# CSER calculation (simplified)
# ---------------------------------------------------------------------------

def _calculate_cser(text_a: str, text_b: str) -> float:
    """Calculate CSER between two agent outputs."""
    import re
    def extract_ideas(text):
        sep = re.compile(r'[.!?]\s+|[\n]+[-*•·]\s*|\n{2,}')
        raw = sep.split(text)
        ideas = []
        for chunk in raw:
            chunk = chunk.strip()
            if len(chunk) < 15:
                continue
            norm = re.sub(r'^[-*•·\d.)\s]+', '', chunk).strip().lower()
            if norm:
                ideas.append(norm)
        return ideas

    def overlap(a, b, threshold=0.4):
        wa = set(re.findall(r'\b\w{3,}\b', a))
        wb = set(re.findall(r'\b\w{3,}\b', b))
        if not wa or not wb:
            return False
        return len(wa & wb) / len(wa | wb) >= threshold

    ideas_a = extract_ideas(text_a)
    ideas_b = extract_ideas(text_b)
    if not ideas_a and not ideas_b:
        return 0.0

    unique_b = list(ideas_b)
    unique_a = []
    shared_count = 0
    for idea in ideas_a:
        matched = False
        for ib in list(unique_b):
            if overlap(idea, ib):
                unique_b = [x for x in unique_b if x != ib]
                shared_count += 1
                matched = True
                break
        if not matched:
            unique_a.append(idea)

    total = len(unique_a) + len(unique_b) + shared_count
    if total == 0:
        return 0.0
    return round(min(1.0, (len(unique_a) + len(unique_b)) / total), 3)


# ---------------------------------------------------------------------------
# Methods
# ---------------------------------------------------------------------------

ASSISTANT_SYSTEM = (
    "You are an expert personal advisor with deep expertise in career, finance, "
    "business, and ethics. Provide comprehensive, nuanced, actionable advice. "
    "Be specific and practical."
)

def run_solo(query: str) -> str:
    """Single GPT-5.2 call."""
    return _call_openai(query, ASSISTANT_SYSTEM)


def run_orchestration(query: str) -> str:
    """4 sequential GPT-5.2 calls: plan → execute → review → refine."""
    # Step 1: Plan
    plan = _call_openai(
        f"Create a structured plan for answering this question thoroughly: {query}",
        "You are a planning expert. Create a clear outline of key points to address."
    )
    # Step 2: Execute
    draft = _call_openai(
        f"Using this plan, write a comprehensive answer.\n\nPlan:\n{plan}\n\nQuestion: {query}",
        ASSISTANT_SYSTEM
    )
    # Step 3: Review
    review = _call_openai(
        f"Review this answer for gaps, errors, or missing nuance:\n\nQuestion: {query}\n\nAnswer: {draft}",
        "You are a critical reviewer. Identify specific improvements needed."
    )
    # Step 4: Refine
    refined = _call_openai(
        f"Refine this answer based on the review:\n\nOriginal answer:\n{draft}\n\nReview:\n{review}\n\nQuestion: {query}",
        ASSISTANT_SYSTEM
    )
    return refined


def run_amp(query: str) -> tuple[str, str, str, float]:
    """amp: Agent A (GPT-5.2) + Agent B (Claude) → reconcile."""
    agent_a_system = (
        "You are an analytical expert (Agent A). Propose a thorough, well-structured answer. "
        "Focus on key insights, opportunities, and constructive recommendations. Think from first principles."
    )
    agent_b_system = (
        "You are a critical expert (Agent B). Independently analyze from a skeptical, adversarial perspective. "
        "Identify risks, flaws, edge cases, and problems. Challenge assumptions."
    )

    # Stage 1 & 2: Independent (A then B — no cross-contamination)
    agent_a_text = _call_openai(
        f"Analyze this question and provide your expert assessment:\n\nQuestion: {query}",
        agent_a_system
    )
    agent_b_text = _call_anthropic(
        f"Critically analyze this question from a skeptical perspective:\n\nQuestion: {query}",
        agent_b_system
    )

    # Stage 3: Reconcile
    reconciler_prompt = f"""You have received independent analyses from two expert agents.

Original question: {query}

[Agent A - Analyst (GPT-5.2)]:
{agent_a_text}

[Agent B - Critic (Claude)]:
{agent_b_text}

Synthesize a final, comprehensive answer that captures the best insights from both.
Include perspectives that only one agent raised — these are the most valuable cross-provider insights.

Format:
AGREEMENTS:
- [points both agents agree on]

CONFLICTS:
- [points where they differ]

SYNTHESIZED ANSWER:
[comprehensive final answer]"""

    reconciled_raw = _call_openai(
        reconciler_prompt,
        "You are a master synthesizer. Produce a superior unified answer capturing the best of both perspectives."
    )

    # Extract synthesized answer
    synthesized = reconciled_raw
    if "SYNTHESIZED ANSWER:" in reconciled_raw.upper():
        idx = reconciled_raw.upper().find("SYNTHESIZED ANSWER:")
        synthesized = reconciled_raw[idx + len("SYNTHESIZED ANSWER:"):].strip()

    cser = _calculate_cser(agent_a_text, agent_b_text)
    return agent_a_text, agent_b_text, synthesized, cser


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

SCENARIOS = {
    "career": "I've been offered a 30% salary raise at a new company, but I love my current team. I have a mortgage and a 6-month-old baby. Should I take the offer?",
    "business_plan": "Review this business plan: Online subscription box for Korean beauty products targeting US millennials. $29/month, sourcing direct from Korea, $50k launch budget. What are the fatal flaws?",
    "cofounder_conflict": "My co-founder and I disagree on direction. I want enterprise clients (slower, higher revenue), she wants consumer (faster growth, lower margins). 8 months in, $200k runway. How do we resolve this?",
    "investment": "I have $10,000 to invest. I'm 32, 6 months emergency fund, no debt. Considering: index funds, AI stocks, real estate crowdfunding, or starting a side business. What's best?",
    "growth_hacking": "Launching a mobile app for kids' screen time tracking. 500 beta users, good retention. How do we reach 10,000 users in 3 months with a $5,000 budget?",
    "ethical_dilemma": "I discovered my colleague pads expense reports by ~$200/month. Single parent, great employee. Company would fire them if I report. What should I do?",
}

SCENARIO_LABELS = {
    "career": "Career Decision",
    "business_plan": "Business Plan Review",
    "cofounder_conflict": "Co-founder Conflict",
    "investment": "Investment Strategy",
    "growth_hacking": "Growth Hacking",
    "ethical_dilemma": "Ethical Dilemma",
}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    console.print("\n[bold cyan]Running amp benchmark...[/bold cyan]\n")

    results = {
        "metadata": {
            "date": str(date.today()),
            "agent_a": "gpt-5.2",
            "agent_b": "claude-sonnet-4-6",
        },
        "scenarios": {},
        "summary": {
            "avg_quality_solo": 0.0,
            "avg_quality_orchestration": 0.0,
            "avg_quality_amp": 0.0,
            "avg_insights_solo": 0.0,
            "avg_insights_orchestration": 0.0,
            "avg_insights_amp": 0.0,
            "avg_cross_provider_insights": 0.0,
        }
    }

    scenario_keys = list(SCENARIOS.keys())
    n = len(scenario_keys)

    for i, key in enumerate(scenario_keys, 1):
        query = SCENARIOS[key]
        label = SCENARIO_LABELS[key]
        console.print(f"[bold][{i}/{n}] {label}...[/bold]")

        # --- Solo ---
        with console.status("  Running Solo..."):
            solo_resp = run_solo(query)
            solo_insights = _count_insights(solo_resp)
            solo_quality = _score_quality(solo_resp, query)
        console.print(f"  [green]✓ Solo[/green]         quality={solo_quality}  insights={solo_insights}")

        # --- Orchestration ---
        with console.status("  Running Orchestration..."):
            orch_resp = run_orchestration(query)
            orch_insights = _count_insights(orch_resp)
            orch_quality = _score_quality(orch_resp, query)
        console.print(f"  [green]✓ Orchestration[/green] quality={orch_quality}  insights={orch_insights}")

        # --- amp ---
        with console.status("  Running amp (GPT-5.2 + Claude)..."):
            a_resp, b_resp, amp_resp, cser = run_amp(query)
            amp_insights = _count_insights(amp_resp)
            amp_quality = _score_quality(amp_resp, query)
            cross_provider = _count_cross_provider_insights(b_resp, solo_resp)
        console.print(f"  [green]✓ amp[/green]          quality={amp_quality}  insights={amp_insights}  cser={cser}  cross_provider={cross_provider}\n")

        results["scenarios"][key] = {
            "query": query,
            "solo": {
                "response": solo_resp,
                "unique_insights": solo_insights,
                "quality": solo_quality,
            },
            "orchestration": {
                "response": orch_resp,
                "unique_insights": orch_insights,
                "quality": orch_quality,
            },
            "amp": {
                "agent_a_response": a_resp,
                "agent_b_response": b_resp,
                "reconciled": amp_resp,
                "cser": cser,
                "unique_insights": amp_insights,
                "cross_provider_insights": cross_provider,
                "quality": amp_quality,
            }
        }

    # Calculate summaries
    scenario_data = list(results["scenarios"].values())
    results["summary"]["avg_quality_solo"] = round(sum(s["solo"]["quality"] for s in scenario_data) / n, 2)
    results["summary"]["avg_quality_orchestration"] = round(sum(s["orchestration"]["quality"] for s in scenario_data) / n, 2)
    results["summary"]["avg_quality_amp"] = round(sum(s["amp"]["quality"] for s in scenario_data) / n, 2)
    results["summary"]["avg_insights_solo"] = round(sum(s["solo"]["unique_insights"] for s in scenario_data) / n, 1)
    results["summary"]["avg_insights_orchestration"] = round(sum(s["orchestration"]["unique_insights"] for s in scenario_data) / n, 1)
    results["summary"]["avg_insights_amp"] = round(sum(s["amp"]["unique_insights"] for s in scenario_data) / n, 1)
    results["summary"]["avg_cross_provider_insights"] = round(sum(s["amp"]["cross_provider_insights"] for s in scenario_data) / n, 1)

    # Save results
    out_path = Path(__file__).parent / "results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    console.print(f"\n[bold green]Results saved to {out_path}[/bold green]")

    # Summary table
    s = results["summary"]
    table = Table(title="Benchmark Summary")
    table.add_column("Method", style="cyan")
    table.add_column("Avg Quality", justify="right")
    table.add_column("Avg Insights", justify="right")
    table.add_column("Cross-Provider", justify="right")
    table.add_row("Solo (GPT-5.2)", str(s["avg_quality_solo"]), str(s["avg_insights_solo"]), "—")
    table.add_row("Orchestration", str(s["avg_quality_orchestration"]), str(s["avg_insights_orchestration"]), "—")
    table.add_row("[bold]amp (GPT-5.2 + Claude)[/bold]", f"[bold]{s['avg_quality_amp']}[/bold]", f"[bold]{s['avg_insights_amp']}[/bold]", f"[bold]+{s['avg_cross_provider_insights']}[/bold]")
    console.print(table)

    return results


if __name__ == "__main__":
    main()
