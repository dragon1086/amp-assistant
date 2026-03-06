"""Emergent mode - 2-agent analysis with reconciliation.

The killer feature of amp: two agents independently analyze a query,
then a reconciler synthesizes agreements and conflicts into a better answer
than either agent could produce alone.

Adaptive rounds:
  rounds=2 (default): Agents analyze INDEPENDENTLY (no cross-visibility).
                      → Reconciler + Verifier synthesize. Best for open analysis.
  rounds=4:           Sequential debate: A→ B-rebuts → A-counters → B-recounters → Synthesis.
                      Best for controversy, comparisons, and adversarial stress-testing.

Key invariant for rounds=2: Agent A and Agent B MUST NOT see each other's output.
This independence is what creates emergence.

Agent A & B 모두 config.yaml에서 자유롭게 설정 가능:
  같은 벤더(GPT+GPT, Claude+Claude)도 동작하나 CSER(독창성)가 낮아질 수 있음.
  교차 벤더(GPT+Claude) 구성이 최고의 CSER를 냄.
"""

import json
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

from amp.core.auto_persona import generate_personas
from amp.core.kg import KnowledgeGraph
from amp.core.llm_factory import call_llm
from amp.core.metrics import calculate_cser
from amp.core.cser_gate import should_retry, patch_result_with_gate_info
from amp.core import kg_bridge


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


def _get_agent_cfg(config: dict, agent: str) -> tuple[str, str, str | None]:
    """config에서 (provider, model, reasoning_effort) 반환. 기본값 fallback 포함."""
    agent_cfg = config.get("agents", {}).get(agent, {})
    reasoning_effort = agent_cfg.get("reasoning_effort", None)
    if agent_cfg.get("provider") and agent_cfg.get("model"):
        return agent_cfg["provider"], agent_cfg["model"], reasoning_effort
    # 기본값: Agent A = anthropic_oauth (Claude, 무료), Agent B = openai (크로스 벤더)
    if agent == "agent_a":
        return "anthropic_oauth", "claude-sonnet-4-6", None
    else:
        return "openai", config.get("llm", {}).get("model", "gpt-5-mini"), None


def _extract_insights(
    query: str, response_a: str, response_b: str,
    reconciled: str, config: dict
) -> dict:
    """Extract agreement/conflict structure between two agents."""
    provider_a, model_a, _ = _get_agent_cfg(config, "agent_a")
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


def _run_4round_debate(
    query: str, prov_a: str, mod_a: str, prov_b: str, mod_b: str,
    personas: dict, kg_context_str: str, same_vendor: bool,
    call_fn,  # _call_with_fallback bound closure
    _p,       # progress callback
) -> tuple[str, str, str, str, str]:
    """4-round sequential debate (ported from ~/emergent/amp.py).

    Round 1: Agent A answers
    Round 2: Agent B rebuts (반박) — sees A's answer
    Round 3: Agent A counters (반론) — sees B's rebuttal
    Round 4: Agent B re-rebuts (재반박) — sees A's counter
    + Synthesis by Reconciler

    Returns: (answer_a, rebuttal_b, counter_a, counter_b, synthesis)
    """
    persona_a = personas.get("persona_a", "분석적 전문가")
    persona_b = personas.get("persona_b", "비판적 전문가")

    # Round 1: Agent A initial analysis
    _p("agent_a_start", persona=persona_a, model=f"{prov_a}/{mod_a}")
    a_system = (
        f"당신은 {persona_a}입니다. 질문에 대해 깊이 있는 분석을 제공하세요."
        " Answer in the same language as the user's question." + kg_context_str
    )
    answer_a, _ = call_fn(
        f"이 질문을 분석하고 전문가적 견해를 제공하세요:\n\n{query}",
        a_system, prov_a, mod_a,
    )
    _p("agent_a_done", persona=persona_a, preview=answer_a[:120])

    # Round 2: Agent B rebuttal (sees A's answer)
    _p("agent_b_start", persona=persona_b, model=f"{prov_b}/{mod_b}")
    b_system = (
        f"당신은 {persona_b}입니다. 상대방의 분석을 비판적으로 검토하고 반박하세요."
        " 동의하는 부분과 동의하지 않는 부분을 명확히 구분하세요."
        " Answer in the same language as the user's question." + kg_context_str
    )
    rebuttal_b, _ = call_fn(
        f"원래 질문: {query}\n\n[{persona_a}]의 분석:\n{answer_a}\n\n"
        "위 분석에 대해 비판적으로 반박하세요.",
        b_system, prov_b, mod_b,
    )
    _p("agent_b_done", persona=persona_b, preview=rebuttal_b[:120])

    # Round 3: Agent A counter (sees B's rebuttal)
    _p("agent_a_counter", persona=persona_a)
    counter_a, _ = call_fn(
        f"원래 질문: {query}\n\n나의 원래 분석:\n{answer_a}\n\n"
        f"[{persona_b}]의 반박:\n{rebuttal_b}\n\n"
        "상대방의 반박에 반론하세요. 타당한 비판은 인정하고, 여전히 유효한 논점은 방어하세요.",
        a_system, prov_a, mod_a,
    )

    # Round 4: Agent B re-rebuttal (sees A's counter)
    _p("agent_b_recounter", persona=persona_b)
    counter_b, _ = call_fn(
        f"원래 질문: {query}\n\n나의 반박:\n{rebuttal_b}\n\n"
        f"[{persona_a}]의 반론:\n{counter_a}\n\n"
        "최종 입장을 정리하세요. 새로운 논점이 있다면 제시하세요.",
        b_system, prov_b, mod_b,
    )

    # Synthesis
    _p("reconciling")
    synth_prompt = (
        f"질문: {query}\n\n"
        f"== [{persona_a}] 최초 분석 ==\n{answer_a}\n\n"
        f"== [{persona_b}] 반박 ==\n{rebuttal_b}\n\n"
        f"== [{persona_a}] 반론 ==\n{counter_a}\n\n"
        f"== [{persona_b}] 재반박 ==\n{counter_b}\n\n"
        "양측 토론을 종합해 최종 판단을 내리세요.\n"
        "Format your response as:\n"
        "AGREEMENTS:\n- [합의된 사항]\n\n"
        "CONFLICTS:\n- [이견 사항]\n\n"
        "SYNTHESIZED ANSWER:\n[최종 종합 답변]"
    )
    synthesis_raw = call_fn(
        synth_prompt,
        "You are a neutral synthesizer. Produce the final unified answer from a debate. "
        "Answer in the same language as the original question.",
        prov_b, mod_b,
    )[0]

    return answer_a, rebuttal_b, counter_a, counter_b, synthesis_raw


def run(query: str, context: list[dict], config: dict, on_progress=None,
        rounds: int = 2, _retry_count: int = 0) -> dict:
    """Execute emergent multi-agent analysis.

    Stages (rounds=2, default — independent analysis):
      1. Agent A (analyst)  — does NOT see B's output
      2. Agent B (critic)   — does NOT see A's output
      3. Reconciler sees both → synthesizes
      4. Verifier checks logic consistency

    Stages (rounds=4 — sequential debate):
      1. Agent A answers
      2. Agent B rebuts (sees A)
      3. Agent A counters (sees B's rebuttal)
      4. Agent B re-rebuts (sees A's counter)
      + Synthesis

    Args:
        query: User's question or request
        context: Conversation history
        config: amp configuration dict
        on_progress: optional callable(stage: str, data: dict) for real-time updates
                     stages: persona_selected | agent_a_start | agent_a_done |
                             agent_b_start | agent_b_done | reconciling |
                             verifying | done | error
        rounds: 2 (independent, default) or 4 (sequential debate)

    Returns:
        dict with keys: answer, mode, agent_a, agent_b, cser, confidence,
                        agreements, conflicts, rounds
    """
    def _p(stage: str, **data):
        if on_progress:
            try:
                on_progress(stage, data)
            except Exception:
                pass
    # Build context summary (shared background, NOT agent outputs)
    ctx_summary = ""
    if context:
        recent = context[-4:]
        ctx_summary = "\n\nConversation context:\n" + "\n".join(
            f"{m['role'].upper()}: {m['content'][:300]}" for m in recent
        )

    # Stage 1 & 2: config에서 provider/model 읽어서 독립 실행
    prov_a, mod_a, reason_a = _get_agent_cfg(config, "agent_a")
    prov_b, mod_b, reason_b = _get_agent_cfg(config, "agent_b")

    # 같은 벤더 여부 감지 → 강제 다양성 모드
    same_vendor = _is_same_vendor(prov_a, prov_b)

    # Auto-persona
    kg = KnowledgeGraph()

    # 성능 보호: KG 검색은 최대 2초만 허용 (느리면 스킵)
    kg_nodes = []
    try:
        from concurrent.futures import ThreadPoolExecutor as _TPEX
        _kpool = _TPEX(max_workers=1)
        _kf = _kpool.submit(lambda: kg.search(query, top_k=3))
        kg_nodes = _kf.result(timeout=float(config.get("amp", {}).get("kg_search_timeout", 2.0))) or []
        _kpool.shutdown(wait=False)
    except Exception:
        kg_nodes = []

    kg_context = [node.get("content", "") for node in kg_nodes if node.get("content")]
    personas = generate_personas(query, kg_context, same_vendor=same_vendor)
    _p("persona_selected",
       persona_a=personas.get("persona_a", "Agent A"),
       persona_b=personas.get("persona_b", "Agent B"),
       model_a=f"{prov_a}/{mod_a}",
       model_b=f"{prov_b}/{mod_b}")

    kg_context_str = ""
    if kg_nodes:
        kg_context_str = "\n\nRelevant knowledge:\n" + "\n".join(
            f"- {node['content']}" for node in kg_nodes
        )

    # temperature 설정 (같은 벤더 시 차별화)
    temp_a = personas.get("temp_a")   # 0.3 (정밀) 또는 None
    temp_b = personas.get("temp_b")   # 1.1 (창의) 또는 None

    # 시스템 프롬프트 — 같은 벤더는 역할 제약 더 강하게
    # 도메인별 심화 지시
    domain = personas.get("domain", "general")
    _domain_hint_a = {
        "strategy":     "수치·근거 기반으로 구체적 실행 단계를 제시하세요.",
        "resource_allocation": "기회비용과 트레이드오프를 반드시 정량화하세요.",
        "ethics":       "가치 충돌 구조를 명시하고, 각 가치의 우선순위 근거를 제시하세요.",
        "career":       "장기 커리어 경로와 단기 리스크를 분리해서 분석하세요.",
        "relationship": "감정·논리·사회적 맥락을 각각 구분해서 분석하세요.",
        "emotion":      "인지적 편향 가능성을 먼저 진단한 뒤 전략을 제시하세요.",
    }.get(domain, "핵심 근거를 3가지 이내로 압축해서 제시하세요.")

    _domain_hint_b = {
        "strategy":     "주류 전략 교과서가 틀릴 수 있는 시나리오를 반드시 포함하세요.",
        "resource_allocation": "일반적 '분산 투자' 조언을 반복하면 실패입니다. 집중 전략의 케이스를 제시하세요.",
        "ethics":       "다수가 동의할 것 같은 결론을 의도적으로 피하세요. 소수 관점·이해충돌 구조를 드러내세요.",
        "career":       "'안정성'과 '성장'의 상충을 기본값으로 가정하지 마세요. 제3의 경로를 찾으세요.",
        "relationship": "상대방의 감정을 대변하는 관점에서 분석하세요.",
        "emotion":      "감정의 정보적 가치(신호로서의 감정)를 중심으로 분석하세요.",
    }.get(domain, "상대방이 말할 법한 '예상 가능한' 결론을 의도적으로 피하고 비선형적 관점을 제시하세요.")

    if same_vendor:
        agent_a_system = (
            f"당신은 {personas['persona_a']}입니다.\n"
            "규칙: 반드시 데이터, 수치, 증거에만 근거하세요. "
            "직관이나 감성적 표현을 배제하고 측정 가능한 결론만 제시하세요. "
            f"{_domain_hint_a} "
            "Answer in the same language as the user's question."
            + kg_context_str
        )
        agent_b_system = (
            f"당신은 {personas['persona_b']}입니다.\n"
            "규칙: 통념에 정면으로 도전하세요. "
            "Agent A가 말할 법한 '안전한' 결론을 피하고, "
            "비선형적·파괴적·소수 의견 관점에서 분석하세요. "
            f"{_domain_hint_b} "
            "상식적인 조언을 반복하면 실패입니다. "
            "Answer in the same language as the user's question."
            + kg_context_str
        )
    else:
        agent_a_system = (
            f"당신은 {personas['persona_a']}입니다. 독립적으로 분석하세요. "
            f"{_domain_hint_a} "
            "Answer in the same language as the user's question."
            + kg_context_str
        )
        agent_b_system = (
            f"당신은 {personas['persona_b']}입니다. 독립적으로 분석하세요. "
            f"{_domain_hint_b} "
            "Answer in the same language as the user's question."
            + kg_context_str
        )

    agent_a_prompt = (
        f"Analyze this question and provide your expert assessment:{ctx_summary}\n\nQuestion: {query}"
    )
    agent_b_prompt = (
        f"Critically analyze this question from your unique perspective:{ctx_summary}\n\nQuestion: {query}"
    )

    # OAuth fallback: anthropic_oauth 실패 시 openai로 자동 전환
    fallback_model = config.get("llm", {}).get("model", "gpt-5-mini")

    def _call_with_fallback(prompt: str, system: str, provider: str, model: str,
                            temperature=None, reasoning_effort=None) -> tuple[str, str]:
        """LLM 호출. OAuth 미인증 시 openai로 fallback. (응답, 실제사용provider) 반환."""
        from amp.core.llm_factory import OAuthNotAvailableError
        kwargs = {}
        if reasoning_effort:
            kwargs["reasoning_effort"] = reasoning_effort
        try:
            return call_llm(prompt, system=system, provider=provider, model=model,
                           temperature=temperature, **kwargs), provider
        except OAuthNotAvailableError:
            return call_llm(prompt, system=system, provider="openai",
                           model=fallback_model, temperature=temperature), "openai"

    # ── rounds=4: Sequential debate ─────────────────────────────────────────
    if rounds == 4:
        answer_a, rebuttal_b, counter_a, counter_b, synthesis_raw = _run_4round_debate(
            query, prov_a, mod_a, prov_b, mod_b,
            personas, kg_context_str, same_vendor,
            _call_with_fallback, _p,
        )
        agent_a_text = answer_a
        agent_b_text = rebuttal_b  # primary B output for CSER
        cser_data = calculate_cser(agent_a_text, counter_b)  # final outputs have most divergence
        agreements, conflicts, synthesized = _parse_reconciliation(synthesis_raw)
        final_answer = synthesized or synthesis_raw
        kg.add(content=final_answer, tags=["emergent", "debate", "4round"])
        insights = _extract_insights(query, agent_a_text, agent_b_text, final_answer, config)
        _p("done")
        _result_4r = {
            "answer": final_answer,
            "mode": "emergent",
            "rounds": 4,
            "agent_a": agent_a_text,
            "agent_b": agent_b_text,
            "debate_counter_a": counter_a,
            "debate_counter_b": counter_b,
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
        # CSER gate: 4-round에서도 낮으면 low_cser_flagged
        _gate_retry, _, _gate_action = should_retry(cser_data["cser"], 4, _retry_count)
        _result_4r = patch_result_with_gate_info(_result_4r, False, _gate_action, cser_data["cser"])
        # emergent KG에 비동기 저장
        kg_bridge.save_to_emergent_kg(query, _result_4r, async_mode=True)
        return _result_4r

    # ── rounds=2 (default): Independent analysis — 병렬 실행 ──────────────────
    # Agent A와 B는 서로 출력을 보지 않으므로 완전히 병렬 실행 가능
    # 직렬 대비 ~50% 시간 절약 (subprocess 2번 → 동시 실행)
    _p("agent_a_start", persona=personas.get("persona_a", "Agent A"), model=f"{prov_a}/{mod_a}")
    _p("agent_b_start", persona=personas.get("persona_b", "Agent B"), model=f"{prov_b}/{mod_b}")

    per_agent_timeout = config.get("amp", {}).get("timeout", 90)

    def _run_a():
        return _call_with_fallback(
            agent_a_prompt, agent_a_system, prov_a, mod_a, temp_a, reasoning_effort=reason_a
        )

    def _run_b():
        return _call_with_fallback(
            agent_b_prompt, agent_b_system, prov_b, mod_b, temp_b, reasoning_effort=reason_b
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        future_a = pool.submit(_run_a)
        future_b = pool.submit(_run_b)
        try:
            agent_a_text, prov_a_actual = future_a.result(timeout=per_agent_timeout)
        except FutureTimeoutError:
            agent_a_text, prov_a_actual = f"[Agent A timeout after {per_agent_timeout}s]", prov_a
        try:
            agent_b_text, prov_b_actual = future_b.result(timeout=per_agent_timeout)
        except FutureTimeoutError:
            agent_b_text, prov_b_actual = f"[Agent B timeout after {per_agent_timeout}s]", prov_b

    _p("agent_a_done", persona=personas.get("persona_a", "Agent A"), preview=agent_a_text[:120])
    _p("agent_b_done", persona=personas.get("persona_b", "Agent B"), preview=agent_b_text[:120])

    # fallback 발생 시 same_vendor 재계산 (다양성 로직에 반영)
    if prov_a_actual != prov_a or prov_b_actual != prov_b:
        same_vendor = _is_same_vendor(prov_a_actual, prov_b_actual)

    # Stage 3: Reconciler sees both outputs
    cser_data = calculate_cser(agent_a_text, agent_b_text)

    # ── CSER Gate: θ=0.30 미달 시 자동 심화 ────────────────────────────────
    _gate_retry, _next_rounds, _gate_action = should_retry(
        cser_data["cser"], current_rounds=2, retry_count=_retry_count
    )
    if _gate_retry:
        _p("cser_gate", cser=cser_data["cser"], action=_gate_action, upgrading_to=_next_rounds)
        return run(
            query=query, context=context, config=config,
            on_progress=on_progress, rounds=_next_rounds,
            _retry_count=_retry_count + 1,
        )

    reconciler_prompt = f"""You have received independent analyses from two expert agents on the same question.

Original question: {query}

[Agent A - Analyst]:
{agent_a_text}

[Agent B - Critic]:
{agent_b_text}

Your task:
1. Identify points where both agents AGREE (list as agreements)
2. Identify points where they DISAGREE or have different perspectives (list as conflicts)
3. Identify important perspectives that NEITHER agent covered (missing angles, blind spots, unstated assumptions)
4. Synthesize a final answer that captures the best insights from both AND fills in the missing perspectives

Format your response as:
AGREEMENTS:
- [agreement points]

CONFLICTS:
- [conflict points]

MISSING PERSPECTIVES:
- [important angles, risks, or context that both agents overlooked]

SYNTHESIZED ANSWER:
[your final synthesized answer in the same language as the original question — must incorporate the missing perspectives]"""

    # Stage 3+4: Reconciler+Verifier 통합 단일 콜
    # - 두 번 순차 호출(~27s) → 1번 통합 호출(~4s)로 단축
    # - gpt-5-mini + reasoning_effort:none → 빠름, 합성은 단순 추론으로 충분
    _p("reconciling", cser=cser_data.get("score", 0))
    # Stage 3+4: 단일 합성 콜 — 불필요한 중간 구조 제거, 최종 답만 생성
    # → 입력 2300c/출력 1800c → 입력 1200c/출력 500c 이하로 단축
    _p("reconciling", cser=cser_data.get("score", 0))
    combined_prompt = f"""Question: {query}

Expert A: {agent_a_text[:450]}

Expert B: {agent_b_text[:450]}

Write the best possible answer by combining insights from both experts.
- Capture unique points from each
- Fill any gaps or blind spots
- Fix logical issues
- Be direct and concise
- Answer in the same language as the question"""

    final_answer = call_llm(
        combined_prompt,
        system=(
            "You combine two expert analyses into one superior answer. "
            "Concise, direct, no preamble. Respond in 150-200 words maximum."
        ),
        provider="openai",
        model=config.get("llm", {}).get("synth_model", "gpt-5-mini"),
        reasoning_effort="none",
    )
    agreements, conflicts, synthesized = [], [], final_answer

    # Persist to KG — fire-and-forget (임베딩 API 블로킹 없음)
    from concurrent.futures import ThreadPoolExecutor as _TPEX
    _kx = _TPEX(max_workers=1)
    _kx.submit(lambda: kg.add(content=final_answer, tags=["emergent", "reconciled"]))
    _kx.shutdown(wait=False)

    # Stage 5: Extract insight metadata — 비동기 백그라운드 (응답 블로킹 없음)
    _insights_holder: dict = {}

    def _bg_insights():
        try:
            _insights_holder["data"] = _extract_insights(
                query, agent_a_text, agent_b_text, final_answer, config
            )
        except Exception:
            _insights_holder["data"] = {}

    from concurrent.futures import ThreadPoolExecutor as _TPE
    _ins_pool = _TPE(max_workers=1)
    _ins_future = _ins_pool.submit(_bg_insights)
    _ins_pool.shutdown(wait=False)          # 메인 응답을 블로킹하지 않음
    insights = {}                           # 즉시 빈 dict 반환 (백그라운드에서 채워짐)

    _p("done")
    _result_2r = {
        "answer": final_answer,
        "mode": "emergent",
        "rounds": 2,
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
    # CSER gate 메타 (이미 gate_retry 통과했으므로 gate_triggered=False)
    _result_2r = patch_result_with_gate_info(_result_2r, False, _gate_action, cser_data["cser"])
    # emergent KG에 비동기 저장
    kg_bridge.save_to_emergent_kg(query, _result_2r, async_mode=True)
    return _result_2r


def _parse_reconciliation(text: str) -> tuple[list[str], list[str], str]:
    """Parse reconciler output into agreements, conflicts, and synthesized answer.
    Also captures MISSING PERSPECTIVES and prepends them to conflicts list.
    """
    agreements = []
    conflicts = []
    missing = []
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
        elif "MISSING PERSPECTIVES:" in upper or "MISSING:" in upper or "BLIND SPOT" in upper:
            current_section = "missing"
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
        elif current_section == "missing" and stripped.startswith("-"):
            item = stripped.lstrip("- ").strip()
            if item:
                missing.append(f"[누락 관점] {item}")
        elif current_section == "synthesis" and stripped:
            synthesized += line + "\n"

    synthesized = synthesized.strip()
    if not synthesized:
        synthesized = text

    # missing perspectives를 conflicts 뒤에 붙여서 함께 전달
    return agreements, conflicts + missing, synthesized


def _extract_verified(verified_raw: str, fallback: str) -> str:
    """Extract the final answer from verifier output."""
    for prefix in ("VERIFIED:", "CORRECTED:", "VERIFIED: ", "CORRECTED: "):
        if verified_raw.upper().startswith(prefix.upper()):
            return verified_raw[len(prefix):].strip()

    # If verifier didn't use expected format, return its full response
    if len(verified_raw.strip()) > 50:
        return verified_raw.strip()

    return fallback
