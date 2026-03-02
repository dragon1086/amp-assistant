"""Emergent mode - 2-agent independent analysis with reconciliation.

The killer feature of amp: two agents independently analyze a query,
then a reconciler synthesizes agreements and conflicts into a better answer
than either agent could produce alone.

Key invariant: Agent A and Agent B MUST NOT see each other's output.
This independence is what creates emergence.

Agent A & B 모두 config.yaml에서 자유롭게 설정 가능:
  같은 벤더(GPT+GPT, Claude+Claude)도 동작하나 CSER(독창성)가 낮아질 수 있음.
  교차 벤더(GPT+Claude) 구성이 최고의 CSER를 냄.
"""

import json

from amp.core.auto_persona import generate_personas
from amp.core.kg import KnowledgeGraph
from amp.core.llm_factory import call_llm
from amp.core.metrics import calculate_cser


def _is_same_vendor(prov_a: str, prov_b: str) -> bool:
    """두 provider가 같은 벤더인지 판단.

    같은 벤더 예시:
      openai + openai → True
      anthropic_oauth + anthropic → True  (둘 다 Claude)
      openai + anthropic → False
    """
    _openai = {"openai"}
    _anthropic = {"anthropic", "anthropic_oauth", "claude_oauth"}
    _local = {"local"}

    def _family(p: str) -> str:
        if p in _openai:   return "openai"
        if p in _anthropic: return "anthropic"
        if p in _local:    return "local"
        return p  # 알 수 없는 벤더

    return _family(prov_a) == _family(prov_b)


def _get_agent_cfg(config: dict, agent: str) -> tuple[str, str]:
    """config에서 (provider, model) 반환. 기본값 fallback 포함."""
    agent_cfg = config.get("agents", {}).get(agent, {})
    if agent_cfg.get("provider") and agent_cfg.get("model"):
        return agent_cfg["provider"], agent_cfg["model"]
    # legacy / fallback
    if agent == "agent_a":
        return "openai", config.get("llm", {}).get("model", "gpt-4o")
    else:
        # agent_b: 명시 설정 없으면 openai로 fallback (anthropic_oauth 미인증 환경 대응)
        return "openai", config.get("llm", {}).get("model", "gpt-4o")


def _extract_insights(
    query: str, response_a: str, response_b: str,
    reconciled: str, config: dict
) -> dict:
    """Extract agreement/conflict structure between two agents."""
    provider_a, model_a = _get_agent_cfg(config, "agent_a")
    label_a = f"{provider_a}/{model_a}"
    label_b_cfg = _get_agent_cfg(config, "agent_b")
    label_b = f"{label_b_cfg[0]}/{label_b_cfg[1]}"

    prompt = f"""Two AI agents analyzed this question independently.

Question: {query}

Agent A ({label_a}): {response_a[:800]}

Agent B ({label_b}): {response_b[:800]}

Synthesized answer: {reconciled[:400]}

Extract in JSON:
{{
  "agreements": ["point both agents agreed on", ...],
  "agent_a_only": ["insight only Agent A raised", ...],
  "agent_b_only": ["insight only Agent B raised", ...],
  "trust_reason": "one sentence: why this multi-agent approach is more reliable"
}}
Return valid JSON only."""

    try:
        result = call_llm(prompt, provider=provider_a, model=model_a)
        data = json.loads(result)
        # 하위 호환: gpt_only/claude_only 키도 함께 제공
        data.setdefault("gpt_only", data.get("agent_a_only", []))
        data.setdefault("claude_only", data.get("agent_b_only", []))
        return data
    except Exception:
        return {
            "agreements": [], "agent_a_only": [], "agent_b_only": [],
            "gpt_only": [], "claude_only": [], "trust_reason": "",
        }


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

    # Stage 1 & 2: config에서 provider/model 읽어서 독립 실행
    prov_a, mod_a = _get_agent_cfg(config, "agent_a")
    prov_b, mod_b = _get_agent_cfg(config, "agent_b")

    # 같은 벤더 여부 감지 → 강제 다양성 모드
    same_vendor = _is_same_vendor(prov_a, prov_b)

    # Auto-persona
    kg = KnowledgeGraph()
    kg_nodes = kg.search(query, top_k=3)
    kg_context = [node["content"] for node in kg_nodes]
    personas = generate_personas(query, kg_context, same_vendor=same_vendor)

    kg_context_str = ""
    if kg_nodes:
        kg_context_str = "\n\nRelevant knowledge:\n" + "\n".join(
            f"- {node['content']}" for node in kg_nodes
        )

    # temperature 설정 (같은 벤더 시 차별화)
    temp_a = personas.get("temp_a")   # 0.3 (정밀) 또는 None
    temp_b = personas.get("temp_b")   # 1.1 (창의) 또는 None

    # 시스템 프롬프트 — 같은 벤더는 역할 제약 더 강하게
    if same_vendor:
        agent_a_system = (
            f"당신은 {personas['persona_a']}입니다.\n"
            "규칙: 반드시 데이터, 수치, 증거에만 근거하세요. "
            "직관이나 감성적 표현을 배제하고 측정 가능한 결론만 제시하세요. "
            "Answer in the same language as the user's question."
            + kg_context_str
        )
        agent_b_system = (
            f"당신은 {personas['persona_b']}입니다.\n"
            "규칙: 통념에 정면으로 도전하세요. "
            "Agent A가 말할 법한 '안전한' 결론을 피하고, "
            "비선형적·파괴적·소수 의견 관점에서 분석하세요. "
            "상식적인 조언을 반복하면 실패입니다. "
            "Answer in the same language as the user's question."
            + kg_context_str
        )
    else:
        agent_a_system = (
            f"당신은 {personas['persona_a']}입니다. 독립적으로 분석하세요. "
            "Answer in the same language as the user's question."
            + kg_context_str
        )
        agent_b_system = (
            f"당신은 {personas['persona_b']}입니다. 독립적으로 분석하세요. "
            "Answer in the same language as the user's question."
            + kg_context_str
        )

    agent_a_prompt = (
        f"Analyze this question and provide your expert assessment:{ctx_summary}\n\nQuestion: {query}"
    )
    agent_b_prompt = (
        f"Critically analyze this question from your unique perspective:{ctx_summary}\n\nQuestion: {query}"
    )

    agent_a_text = call_llm(
        agent_a_prompt, system=agent_a_system,
        provider=prov_a, model=mod_a, temperature=temp_a,
    )
    # Agent B는 Agent A 출력을 절대 보지 않음 (독립성 불변 조건)
    agent_b_text = call_llm(
        agent_b_prompt, system=agent_b_system,
        provider=prov_b, model=mod_b, temperature=temp_b,
    )

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

    # Reconciler & Verifier: Agent B provider 사용 (A와 다른 관점 유지)
    reconciled_raw = call_llm(
        reconciler_prompt,
        system="You are a master synthesizer. You receive two independent expert analyses and produce a superior unified answer that captures the best of both perspectives. Answer in the same language as the original question.",
        provider=prov_b, model=mod_b,
    )

    # Parse reconciler output
    agreements, conflicts, synthesized = _parse_reconciliation(reconciled_raw)

    # Stage 4: Verifier (Agent A provider로 교차 검증)
    verifier_prompt = f"""Check the following answer for logical consistency, completeness, and accuracy.

Original question: {query}

Answer to verify:
{synthesized}

If the answer is logically consistent and complete, output it as-is with "VERIFIED: " prefix.
If you find issues, output the corrected version with "CORRECTED: " prefix.
Answer in the same language as the original question."""

    verified_raw = call_llm(
        verifier_prompt,
        system="You are a logical consistency checker. Verify answers for correctness. Answer in the same language as the original question.",
        provider=prov_a, model=mod_a,
    )

    # Extract final answer
    final_answer = _extract_verified(verified_raw, synthesized)

    # Persist synthesized answer to KG for future context
    kg.add(content=final_answer, tags=["emergent", "reconciled"])

    # Stage 5: Extract insight metadata
    insights = _extract_insights(query, agent_a_text, agent_b_text, final_answer, config)

    return {
        "answer": final_answer,
        "mode": "emergent",
        "agent_a": agent_a_text,
        "agent_b": agent_b_text,
        "cser": cser_data["cser"],
        "confidence": cser_data["confidence"],
        "agreements": agreements,
        "conflicts": conflicts,
        "persona_a": personas["persona_a"],
        "persona_b": personas["persona_b"],
        "persona_domain": personas["domain"],
        "persona_diversity": personas["diversity_score"],
        "persona_source": personas["source"],
        "agent_a_label": f"{prov_a}/{mod_a}",
        "agent_b_label": f"{prov_b}/{mod_b}",
        "same_vendor": same_vendor,
        "insights": insights,
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
