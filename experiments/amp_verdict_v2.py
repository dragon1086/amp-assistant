#!/usr/bin/env python3
"""amp_verdict_v2: Blind A/B benchmark comparing amp ON vs amp OFF.

amp ON  = GPT-5.2 (Analyst) + Claude (Critic) → Reconcile (GPT-5.2)
amp OFF = Single GPT-5.2 call

Judge: gemini-3-flash-preview (blind A/B — labels randomized per question)
N: 30 questions across career, business, emotion, relationship, strategy,
   resource_allocation, and ethics domains.

Output: experiments/amp_verdict_v2.json
Summary fields: ab_win_rate_on, ab_win_rate_off, n_questions, p_value
"""

import json
import os
import random
import subprocess
from datetime import date
from math import comb
from pathlib import Path

from google import genai as genai_client
import openai
from rich.console import Console
from rich.table import Table

console = Console()

# ─── Config ──────────────────────────────────────────────────────────────────

MODEL_MAIN = "gpt-5.2-chat-latest"
MODEL_JUDGE = "gemini-3-flash-preview"

# ─── LLM calls ───────────────────────────────────────────────────────────────


def _call_openai(prompt: str, system: str) -> str:
    client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    try:
        resp = client.chat.completions.create(
            model=MODEL_MAIN,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        )
        return resp.choices[0].message.content.strip()
    except Exception:
        # Fallback to responses API with base model name
        resp = client.responses.create(
            model="gpt-5.2",
            instructions=system,
            input=prompt,
        )
        return resp.output_text


def _call_claude(prompt: str, system: str) -> str:
    oauth_token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "")
    full_prompt = f"{system}\n\n{prompt}"
    env = {k: v for k, v in os.environ.items()
           if k not in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT",
                        "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS")}
    env["CLAUDE_CODE_OAUTH_TOKEN"] = oauth_token
    result = subprocess.run(
        ["claude", "-p", "--dangerously-skip-permissions", full_prompt],
        capture_output=True, text=True, timeout=120, env=env,
    )
    if result.returncode != 0 and result.stderr:
        console.print(f"[yellow]claude warning: {result.stderr[:200]}[/yellow]")
    return result.stdout.strip()


def _call_gemini_judge(question: str, resp_a: str, resp_b: str) -> str:
    """Blind judge: returns 'A', 'B', or 'TIE'."""
    client = genai_client.Client(api_key=os.environ["GEMINI_API_KEY"])
    prompt = (
        "You are an expert evaluator. Compare two responses to the same question.\n"
        "Evaluate for: completeness, nuance, actionability, and insight quality.\n\n"
        f"Question: {question}\n\n"
        f"Response A:\n{resp_a[:2000]}\n\n"
        f"Response B:\n{resp_b[:2000]}\n\n"
        "Which response is better overall? Reply with ONLY one word: A, B, or TIE."
    )
    try:
        result = client.models.generate_content(model=MODEL_JUDGE, contents=prompt)
        text = result.text.strip().upper()
        # Parse first token
        first = text.split()[0] if text.split() else "TIE"
        if first.startswith("A") and not first.startswith("AB"):
            return "A"
        if first.startswith("B") and not first.startswith("BA"):
            return "B"
        return "TIE"
    except Exception as e:
        console.print(f"[yellow]Gemini judge error: {e}[/yellow]")
        return "TIE"


# ─── amp conditions ───────────────────────────────────────────────────────────

SYSTEM_ADVISOR = (
    "You are an expert personal advisor with deep knowledge in career, finance, "
    "relationships, strategy, and ethics. Provide comprehensive, nuanced, "
    "actionable advice. Be specific and practical."
)
SYSTEM_ANALYST = (
    "You are an analytical expert (Agent A). Propose a thorough, well-structured answer. "
    "Focus on key insights, opportunities, and constructive recommendations. Think from first principles."
)
SYSTEM_CRITIC = (
    "You are a critical expert (Agent B). Independently analyze from a skeptical, adversarial perspective. "
    "Identify risks, flaws, edge cases, and problems. Challenge assumptions."
)


def run_amp_off(question: str) -> str:
    """amp OFF: single GPT call."""
    return _call_openai(question, SYSTEM_ADVISOR)


def run_amp_on(question: str) -> str:
    """amp ON: GPT (Analyst) + Claude (Critic) → Reconcile (GPT)."""
    agent_a = _call_openai(
        f"Analyze this question and provide your expert assessment:\n\n{question}",
        SYSTEM_ANALYST,
    )
    agent_b = _call_claude(
        f"Critically analyze this question from a skeptical perspective:\n\n{question}",
        SYSTEM_CRITIC,
    )
    reconcile_prompt = (
        f"You received independent analyses from two expert agents.\n\n"
        f"Original question: {question}\n\n"
        f"[Agent A - Analyst (GPT-5.2)]:\n{agent_a}\n\n"
        f"[Agent B - Critic (Claude)]:\n{agent_b}\n\n"
        "Synthesize a final, comprehensive answer capturing the best insights from both.\n"
        "Include perspectives only one agent raised — these are the most valuable.\n\n"
        "SYNTHESIZED ANSWER:"
    )
    reconciled = _call_openai(
        reconcile_prompt,
        "You are a master synthesizer. Produce a superior unified answer.",
    )
    if "SYNTHESIZED ANSWER:" in reconciled.upper():
        idx = reconciled.upper().find("SYNTHESIZED ANSWER:")
        reconciled = reconciled[idx + len("SYNTHESIZED ANSWER:"):].strip()
    return reconciled


# ─── Statistical helper ───────────────────────────────────────────────────────


def _binomial_p_value(k: int, n: int, p0: float = 0.5) -> float:
    """One-sided p-value: P(X >= k) under H0: p = p0."""
    if n == 0:
        return 1.0
    p = sum(
        comb(n, i) * (p0 ** i) * ((1 - p0) ** (n - i))
        for i in range(k, n + 1)
    )
    return round(min(p, 1.0), 4)


# ─── Questions (N=30) ─────────────────────────────────────────────────────────

QUESTIONS = [
    # ── 기존 시나리오 6개 (career, business, strategy, resource_allocation, ethics) ──
    {
        "id": "career_existing_1",
        "domain": "career",
        "question": (
            "I've been offered a 30% salary raise at a new company, but I love my current team. "
            "I have a mortgage and a 6-month-old baby. Should I take the offer?"
        ),
    },
    {
        "id": "business_existing_1",
        "domain": "business",
        "question": (
            "Review this business plan: Online subscription box for Korean beauty products targeting "
            "US millennials. $29/month, sourcing direct from Korea, $50k launch budget. What are the fatal flaws?"
        ),
    },
    {
        "id": "strategy_existing_1",
        "domain": "strategy",
        "question": (
            "My co-founder and I disagree on direction. I want enterprise clients (slower, higher revenue), "
            "she wants consumer (faster growth, lower margins). 8 months in, $200k runway. How do we resolve this?"
        ),
    },
    {
        "id": "resource_existing_1",
        "domain": "resource_allocation",
        "question": (
            "I have $10,000 to invest. I'm 32, 6 months emergency fund, no debt. "
            "Considering: index funds, AI stocks, real estate crowdfunding, or starting a side business. What's best?"
        ),
    },
    {
        "id": "strategy_existing_2",
        "domain": "strategy",
        "question": (
            "Launching a mobile app for kids' screen time tracking. 500 beta users, good retention. "
            "How do we reach 10,000 users in 3 months with a $5,000 budget?"
        ),
    },
    {
        "id": "ethics_existing_1",
        "domain": "ethics",
        "question": (
            "I discovered my colleague pads expense reports by ~$200/month. "
            "Single parent, great employee. Company would fire them if I report. What should I do?"
        ),
    },
    # ── 감정 (Emotion) — 4 new questions ──
    {
        "id": "emotion_1",
        "domain": "emotion",
        "question": (
            "I feel deeply resentful toward my father for missing most of my childhood due to work. "
            "He's now retired and wants a closer relationship. I want to forgive him but I can't seem to let go. "
            "How do I actually process this?"
        ),
    },
    {
        "id": "emotion_2",
        "domain": "emotion",
        "question": (
            "After a miscarriage, I feel emotionally numb and disconnected from my partner. "
            "We grieve differently — I need to talk; they go silent. "
            "How do we stay close without forcing each other's process?"
        ),
    },
    {
        "id": "emotion_3",
        "domain": "emotion",
        "question": (
            "I'm a high performer at work but privately suffer from intense impostor syndrome. "
            "Every promotion makes it worse, not better. What actually works to address this at the root?"
        ),
    },
    {
        "id": "emotion_4",
        "domain": "emotion",
        "question": (
            "I've been experiencing chronic loneliness for 3 years despite having friends and a partner. "
            "I feel deeply unknown by everyone around me. What am I missing and what should I change?"
        ),
    },
    # ── 관계 (Relationship) — 4 new questions ──
    {
        "id": "relationship_1",
        "domain": "relationship",
        "question": (
            "My best friend of 15 years has become increasingly negative and draining. "
            "Conversations always center on their problems; they rarely ask about me. "
            "How do I address this without losing the friendship?"
        ),
    },
    {
        "id": "relationship_2",
        "domain": "relationship",
        "question": (
            "My partner and I have different views on having children — I want them, they're unsure. "
            "We've been together 4 years and love each other deeply. "
            "At what point does this become a dealbreaker, and how do we navigate it?"
        ),
    },
    {
        "id": "relationship_3",
        "domain": "relationship",
        "question": (
            "I'm in a new relationship and my partner earns 4x what I make. "
            "Money dynamics feel uncomfortable: they pay for everything, I feel inferior, they seem unbothered. "
            "How do we build a healthy financial dynamic?"
        ),
    },
    {
        "id": "relationship_4",
        "domain": "relationship",
        "question": (
            "My adult sibling borrowed $8,000 from me 2 years ago with promises to repay. "
            "They haven't mentioned it since. Asking for it back feels awkward and could damage the relationship. "
            "What's the right move?"
        ),
    },
    # ── 전략 (Strategy) — 4 new questions ──
    {
        "id": "strategy_new_1",
        "domain": "strategy",
        "question": (
            "I'm a solo consultant who hit $180k revenue last year but feel stuck at a ceiling. "
            "Every attempt to scale hits one bottleneck: me. What's the strategic shift I need to break through?"
        ),
    },
    {
        "id": "strategy_new_2",
        "domain": "strategy",
        "question": (
            "My startup has two customer segments that both want our product but have conflicting needs. "
            "Serving both dilutes the product; choosing one kills 40% of current revenue. How do I decide?"
        ),
    },
    {
        "id": "strategy_new_3",
        "domain": "strategy",
        "question": (
            "I work at a mid-level manager position and want to become a VP within 3 years without changing companies. "
            "What's the most effective political and strategic path, avoiding naive advice?"
        ),
    },
    {
        "id": "strategy_new_4",
        "domain": "strategy",
        "question": (
            "Our SaaS product has strong retention (95% annual) but terrible new customer acquisition "
            "(CAC tripled in 18 months). Do we double down on acquisition or shift to expansion revenue?"
        ),
    },
    # ── 자원배분 (Resource Allocation) — 4 new questions ──
    {
        "id": "resource_new_1",
        "domain": "resource_allocation",
        "question": (
            "I have 4 equally promising projects competing for my limited attention. "
            "I can only do one justice at a time. "
            "What framework should I use to decide where to focus, and how do I avoid regret?"
        ),
    },
    {
        "id": "resource_new_2",
        "domain": "resource_allocation",
        "question": (
            "As a startup founder with 6 months runway, I must choose: "
            "hire a strong engineer (extend runway 2 months, build faster) or "
            "hire a strong salesperson (uncertain ROI, might save the company). How do I decide?"
        ),
    },
    {
        "id": "resource_new_3",
        "domain": "resource_allocation",
        "question": (
            "My aging parents need more support. I have two siblings: one is closer geographically but has young kids, "
            "the other is farther but has more money. "
            "How should we fairly divide responsibility without building resentment?"
        ),
    },
    {
        "id": "resource_new_4",
        "domain": "resource_allocation",
        "question": (
            "I have $50,000 to allocate across: paying off student loans (4.5%), "
            "maxing retirement accounts, buying a rental property, and building a 12-month emergency fund. "
            "I can only fully fund 2 of these. What's the optimal allocation?"
        ),
    },
    # ── 윤리 (Ethics) — 4 new questions ──
    {
        "id": "ethics_new_1",
        "domain": "ethics",
        "question": (
            "My company is profitable but our product is clearly contributing to smartphone addiction in teenagers. "
            "Management won't address it. I'm a product manager with influence but not authority. "
            "What's my ethical obligation?"
        ),
    },
    {
        "id": "ethics_new_2",
        "domain": "ethics",
        "question": (
            "I found out a close friend got their job through nepotism and is clearly underperforming, "
            "but is well-liked. They're occupying a role a more qualified colleague deserved. "
            "Do I say anything, and to whom?"
        ),
    },
    {
        "id": "ethics_new_3",
        "domain": "ethics",
        "question": (
            "I'm a doctor and a terminally ill patient has asked me to prescribe a lethal dose of painkillers "
            "they plan to use to end their life. It's illegal in my jurisdiction but they're suffering greatly. "
            "What should I do?"
        ),
    },
    {
        "id": "ethics_new_4",
        "domain": "ethics",
        "question": (
            "I work at an AI company. We discovered our model generates subtly biased hiring recommendations "
            "that disadvantage certain demographics. Fixing it will delay our launch by 6 months and risk our funding. "
            "What's the right course of action?"
        ),
    },
    # ── 추가 4개 (career×2, emotion×1, relationship×1) — 총 30개 ──
    {
        "id": "career_new_1",
        "domain": "career",
        "question": (
            "I'm 38 and have spent 12 years in a stable but unfulfilling corporate job. "
            "I want to switch to something meaningful but have a family depending on my income. "
            "How do I make a realistic mid-career pivot without blowing up my life?"
        ),
    },
    {
        "id": "career_new_2",
        "domain": "career",
        "question": (
            "My manager takes credit for my work in leadership meetings and I have no way to prove it. "
            "HR is friendly with them. I've been passed over for promotion twice. "
            "What's my most effective path forward — escalate, work around it, or leave?"
        ),
    },
    {
        "id": "emotion_5",
        "domain": "emotion",
        "question": (
            "I've recently realized I've been a people-pleaser my entire adult life — "
            "saying yes when I mean no, shrinking myself in groups, feeling anxious when anyone is upset with me. "
            "I want to change but don't know where to start. What's the most effective approach?"
        ),
    },
    {
        "id": "relationship_5",
        "domain": "relationship",
        "question": (
            "My in-laws visit every few months and stay for 2–3 weeks each time. "
            "My spouse sees nothing wrong with this; I find it deeply stressful and feel my home is not my own. "
            "How do I address this without creating a lasting conflict between my spouse and me?"
        ),
    },
]

assert len(QUESTIONS) == 30, f"Expected 30 questions, got {len(QUESTIONS)}"


# ─── Main ─────────────────────────────────────────────────────────────────────


def main():
    random.seed(42)  # Reproducible randomization
    n_total = len(QUESTIONS)

    console.print(f"\n[bold cyan]amp_verdict_v2[/bold cyan] — N={n_total} Blind A/B Benchmark")
    console.print(
        f"[dim]ON: {MODEL_MAIN} + claude-sonnet-4-6 → reconcile  |  "
        f"OFF: {MODEL_MAIN} solo  |  Judge: {MODEL_JUDGE}[/dim]\n"
    )

    results = {
        "metadata": {
            "date": str(date.today()),
            "model_amp_on_analyst": MODEL_MAIN,
            "model_amp_on_critic": "claude-sonnet-4-6",
            "model_amp_off": MODEL_MAIN,
            "judge": MODEL_JUDGE,
            "blind_ab": True,
            "random_seed": 42,
            "n_questions": n_total,
        },
        "trials": [],
        "summary": {},
    }

    n_on_wins = 0
    n_off_wins = 0
    n_ties = 0

    for i, q in enumerate(QUESTIONS, 1):
        question = q["question"]
        domain = q["domain"]
        console.print(f"[bold][{i:02d}/{n_total}][/bold] [{domain}] {question[:75]}...")

        # --- amp OFF ---
        with console.status("  [dim]amp OFF (solo)...[/dim]"):
            resp_off = run_amp_off(question)
        console.print(f"  [green]✓ OFF[/green] {len(resp_off)} chars")

        # --- amp ON ---
        with console.status("  [dim]amp ON  (GPT+Claude+reconcile)...[/dim]"):
            resp_on = run_amp_on(question)
        console.print(f"  [green]✓ ON [/green] {len(resp_on)} chars")

        # --- Blind shuffle ---
        swap = random.random() < 0.5
        if swap:
            resp_a, resp_b, label_a, label_b = resp_on, resp_off, "on", "off"
        else:
            resp_a, resp_b, label_a, label_b = resp_off, resp_on, "off", "on"

        # --- Judge ---
        with console.status("  [dim]Gemini judging...[/dim]"):
            raw_verdict = _call_gemini_judge(question, resp_a, resp_b)

        # Map raw verdict back to on/off
        if raw_verdict == "A":
            winner = label_a
        elif raw_verdict == "B":
            winner = label_b
        else:
            winner = "tie"

        if winner == "on":
            n_on_wins += 1
            tag = "[bold green]ON wins ✓[/bold green]"
        elif winner == "off":
            n_off_wins += 1
            tag = "[red]OFF wins[/red]"
        else:
            n_ties += 1
            tag = "[yellow]TIE[/yellow]"

        console.print(f"  → {tag}  (swap={swap}, raw={raw_verdict})\n")

        results["trials"].append({
            "id": q["id"],
            "domain": domain,
            "question": question,
            "resp_amp_off": resp_off,
            "resp_amp_on": resp_on,
            "swap": swap,
            "raw_verdict": raw_verdict,
            "winner": winner,
        })

    # --- Summary ---
    decisive = n_on_wins + n_off_wins
    p_value = _binomial_p_value(n_on_wins, decisive) if decisive > 0 else 1.0

    results["summary"] = {
        "n_questions": n_total,
        "n_on_wins": n_on_wins,
        "n_off_wins": n_off_wins,
        "n_ties": n_ties,
        "ab_win_rate_on": round(n_on_wins / n_total, 3),
        "ab_win_rate_off": round(n_off_wins / n_total, 3),
        "tie_rate": round(n_ties / n_total, 3),
        "decisive_trials": decisive,
        "p_value": p_value,
        "significant_at_0.05": p_value < 0.05,
    }

    # --- Save ---
    out_path = Path(__file__).parent / "amp_verdict_v2.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    console.print(f"\n[bold green]Results saved → {out_path}[/bold green]")

    # --- Table ---
    s = results["summary"]
    table = Table(title=f"amp_verdict_v2 Results  (N={n_total})")
    table.add_column("Condition", style="cyan", min_width=25)
    table.add_column("Wins", justify="right")
    table.add_column("Win Rate", justify="right")
    table.add_row("amp ON  (GPT-5.2 + Claude)", str(s["n_on_wins"]), f"{s['ab_win_rate_on']:.1%}")
    table.add_row("amp OFF (GPT-5.2 solo)", str(s["n_off_wins"]), f"{s['ab_win_rate_off']:.1%}")
    table.add_row("TIE", str(s["n_ties"]), f"{s['tie_rate']:.1%}")
    table.add_section()
    sig_str = ("[bold green]p<0.05 ✓ significant[/bold green]"
               if s["significant_at_0.05"] else "[dim]not significant[/dim]")
    table.add_row("p-value (binomial, one-sided)", str(s["p_value"]), sig_str)
    console.print(table)

    return results


if __name__ == "__main__":
    main()
