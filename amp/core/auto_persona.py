"""
amp Auto-Persona Engine
Automatically generates optimal contrasting personas for any query.
Designed with cokac-bot. Three pillars: 시장성 / 시대를 앞서나감 / AGI

도메인 감지 우선순위:
  1. 정적 키워드 매칭 (O(1), LLM 호출 없음)
  2. DomainRegistry 임베딩 유사도 (캐시 조회)
  3. DomainRegistry 신규 창작 (gpt-5-mini 1회, DB 저장 후 재사용)
"""

import json
import os

from openai import OpenAI

from amp.core.domain_registry import DomainRegistry, DomainSpec

# ─── 같은 벤더 전용: 극단적 관점 대비 팩 ───────────────────────────────────
# 같은 모델 계열은 기본 priors를 공유하므로 역할을 매우 강하게 분리해야 CSER 확보 가능.
# temp_a(낮음) = 정밀/보수, temp_b(높음) = 창의/도전적
SAME_VENDOR_PRESETS: dict[str, tuple[str, str]] = {
    "career":       ("커리어 최적화 전략가 — 데이터 기반, 현실 우선, 위험 최소화",
                     "파괴적 혁신 코치 — 현상 타파, 비선형 도약, 편안함을 거부"),
    "relationship": ("인지행동 치료사 — 패턴 분석, 명확한 경계, 감정적 거리",
                     "깊은 연결 추구자 — 취약성 수용, 감정적 몰입, 무조건적 이해"),
    "business":     ("리스크 관리 CFO — 현금흐름, 생존가능성, 보수적 성장",
                     "비전형 창업가 — 시장 파괴, 10배 성장, 실패를 학습으로"),
    "investment":   ("퀀트 리스크 애널리스트 — 하방 보호, 포트폴리오 헤징, 통계 근거",
                     "모멘텀 성장 투자자 — 비대칭 수익, 집중 배팅, 추세 추종"),
    "legal_contract":("독소조항 사냥꾼 — 최악 시나리오, 모든 허점 탐지, 절대 서명 거부",
                      "딜 클로저 — 비즈니스 기회 우선, 실용적 타협, 관계 자산 보호"),
    "health":       ("예방의학 전문가 — 증거 기반, 최악 가능성 우선 고려, 조기 개입",
                     "통합 웰빙 코치 — 전체론적 접근, 삶의 질 우선, 자연 치유"),
    "ethics":       ("의무론적 윤리학자 — 원칙 불변, 결과 무관, 절대적 도덕 규범",
                     "공리주의 실용주의자 — 최대 다수 이익, 결과 중심, 맥락 유연"),
    "creative":     ("시스템 설계자 — 실행 가능성, 제약 조건 내 최적화, 재현성",
                     "제약 없는 몽상가 — 불가능을 전제 무시, 형식 파괴, 순수 창의"),
    "parenting":    ("발달심리학 전문가 — 연구 기반, 장기 심리 영향, 안전 우선",
                     "자유 양육 철학자 — 자율성 극대화, 실수를 통한 성장, 아이 주도"),
    "default":      ("정밀 분석가 — 논리, 증거, 측정 가능한 결론만",
                     "직관적 통합자 — 맥락, 감정, 시스템 전체 패턴"),
}

# 같은 벤더 감지 시 사용할 temperature 쌍
SAME_VENDOR_TEMPS = (0.3, 1.1)   # (agent_a: 정밀, agent_b: 창의/도전)

# ─── 교차 벤더 기본 프리셋 ───────────────────────────────────────────────────
PERSONA_PRESETS = {
    "career":         ("커리어 성장 코치 (기회와 가능성 중심)", "재무 안정 분석가 (리스크와 현실 중심)"),
    "relationship":   ("관계 심리학자 (감정과 패턴 분석)", "현실주의 조언자 (경계와 명확성 중심)"),
    "business":       ("스타트업 낙관론자 (실행과 성장 중심)", "시장 현실주의자 (리스크와 경쟁 분석)"),
    "investment":     ("성장 투자 전문가 (수익 기회 탐색)", "리스크 관리 전문가 (하방 보호 중심)"),
    "legal_contract": ("법률 리스크 분석가 (독소조항 탐지)", "비즈니스 기회 분석가 (실용적 이익 중심)"),
    "health":         ("예방의학 전문가 (최악의 경우 고려)", "통합의학 상담사 (전체적 웰빙 중심)"),
    "ethics":         ("원칙 중심 윤리학자 (장기 결과와 가치)", "실용주의 해결사 (현실적 균형 탐색)"),
    "creative":       ("창의적 혁신가 (가능성 확장)", "실행 전략가 (현실 구현 방법 중심)"),
    "parenting":      ("발달심리학자 (아이 관점 중심)", "현실적 부모 코치 (가족 시스템 균형)"),
    "default":        ("분석적 전문가 (데이터와 논리 중심)", "공감적 조언자 (감정과 가치 중심)"),
}

DOMAIN_KEYWORDS = {
    "career":         ["이직", "취업", "직장", "연봉", "승진", "커리어", "job", "salary", "resign", "quit"],
    "relationship":   ["연애", "결혼", "이별", "갈등", "친구", "가족", "부모", "남친", "여친", "배우자"],
    "business":       ["창업", "스타트업", "사업", "비즈니스", "투자자", "펀딩", "startup", "business"],
    "investment":     ["투자", "주식", "코인", "부동산", "펀드", "etf", "invest", "stock"],
    "legal_contract": ["계약", "사인", "법률", "소송", "계약서", "contract", "legal"],
    "health":         ["건강", "병원", "증상", "약", "수술", "다이어트", "health", "doctor"],
    "ethics":         ["윤리", "도덕", "옳은", "잘못", "신고", "고발", "ethics", "moral"],
    "creative":       ["아이디어", "디자인", "글쓰기", "작품", "creative", "design", "write"],
    "parenting":      ["육아", "아이", "자녀", "교육", "학교", "parenting", "child"],
}


def detect_domain(query: str, use_llm_fallback: bool = True) -> str:
    """
    정적 키워드로 도메인 감지.
    use_llm_fallback=True이면 키워드 미스 시 _llm_detect_domain 호출.

    참고: 키워드 완전 미스인 경우, generate_personas()는 DomainRegistry를
    통해 더 정교한 동적 분류를 수행한다. 이 함수는 빠른 경로 전용.
    """
    query_lower = query.lower()
    for domain, keywords in DOMAIN_KEYWORDS.items():
        if any(kw in query_lower for kw in keywords):
            return domain
    if use_llm_fallback:
        return _llm_detect_domain(query)
    return "default"


def _llm_detect_domain(query: str) -> str:
    """
    키워드로 감지 못한 경우 gpt-5-mini로 기존 9개 도메인 중 하나로 분류.
    DomainRegistry가 초기화되기 전 단계 또는 레거시 경로에서 사용.
    """
    try:
        client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
        domains = list(DOMAIN_KEYWORDS.keys()) + ["default"]
        resp = client.chat.completions.create(
            model="gpt-5-mini",
            messages=[
                {"role": "system", "content": (
                    f"Classify the query into exactly one of: {', '.join(domains)}. "
                    "Return the domain name only, nothing else."
                )},
                {"role": "user", "content": query},
            ],
            max_tokens=10,
        )
        domain = resp.choices[0].message.content.strip().lower()
        return domain if domain in DOMAIN_KEYWORDS else "default"
    except Exception:
        return "default"


def validate_persona_diversity(persona_a: str, persona_b: str, client: OpenAI) -> float:
    """Check embedding distance between personas. Returns cosine similarity (lower = more diverse)."""
    try:
        resp = client.embeddings.create(
            model="text-embedding-3-small",
            input=[persona_a, persona_b],
        )
        a, b = resp.data[0].embedding, resp.data[1].embedding
        dot = sum(x * y for x, y in zip(a, b))
        na = sum(x**2 for x in a) ** 0.5
        nb = sum(x**2 for x in b) ** 0.5
        return dot / (na * nb)
    except Exception:
        return 0.5  # fallback: assume OK


def generate_personas(query: str, kg_context: list = None, same_vendor: bool = False) -> dict:
    """
    Main entry point. Returns optimal contrasting personas for a query.

    도메인 감지 우선순위:
      1. 정적 키워드 매칭 (O(1), LLM 호출 없음)
      2. DomainRegistry.find()  — 임베딩 유사도 캐시 조회
      3. DomainRegistry.create() — gpt-5-mini로 신규 도메인 창작 + 저장

    Args:
        query:       User question
        kg_context:  KG search results for extra context
        same_vendor: True일 때 같은 벤더 전용 극단 대비 팩 사용.

    Returns:
        dict with persona_a, persona_b, diversity_score, source,
        domain, and (same_vendor=True일 때) temp_a, temp_b
    """
    kg_context = kg_context or []

    # ── 1단계: 정적 키워드 매칭 ──────────────────────────────────────────────
    domain = detect_domain(query, use_llm_fallback=False)
    dynamic_spec: DomainSpec | None = None

    # ── 2~3단계: 키워드 미스 → 동적 레지스트리 ───────────────────────────────
    if domain == "default":
        try:
            client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
            registry = DomainRegistry()

            # 2단계: 캐시 조회
            spec = registry.find(query, client)

            # 3단계: 캐시 미스 → 신규 창작
            if spec is None:
                spec = registry.create(query, client)

            dynamic_spec = spec
            domain = spec.name

        except Exception:
            pass  # 실패 시 정적 default 사용

    # ── 페르소나 결정 ─────────────────────────────────────────────────────────
    if same_vendor:
        if dynamic_spec is not None:
            # 동적 도메인: DomainSpec의 sv_persona 사용
            persona_a = dynamic_spec.sv_persona_a
            persona_b = dynamic_spec.sv_persona_b
        else:
            # 정적 도메인: SAME_VENDOR_PRESETS 사용
            persona_a, persona_b = SAME_VENDOR_PRESETS.get(domain, SAME_VENDOR_PRESETS["default"])
        temp_a, temp_b = SAME_VENDOR_TEMPS
        return {
            "domain": domain,
            "persona_a": persona_a,
            "persona_b": persona_b,
            "diversity_score": 0.75,
            "source": f"same_vendor_preset" if dynamic_spec is None else f"same_vendor_dynamic:{dynamic_spec.source}",
            "temp_a": temp_a,
            "temp_b": temp_b,
        }

    # 교차 벤더
    if dynamic_spec is not None:
        persona_a = dynamic_spec.persona_a
        persona_b = dynamic_spec.persona_b
        source = f"dynamic:{dynamic_spec.source}"
    elif domain in PERSONA_PRESETS:
        persona_a, persona_b = PERSONA_PRESETS[domain]
        source = "preset"
    else:
        persona_a, persona_b = PERSONA_PRESETS["default"]
        source = "preset:default"

    # kg_context가 있으면 LLM으로 더 정교하게 조정 (기존 동작 유지)
    if kg_context and len(kg_context) > 0 and dynamic_spec is None:
        try:
            client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
            persona_a, persona_b = _dynamic_generate(query, kg_context, client)
            source = "dynamic:kg_context"
        except Exception:
            pass

    return {
        "domain": domain,
        "persona_a": persona_a,
        "persona_b": persona_b,
        "diversity_score": 0.5,
        "source": source,
        "temp_a": None,
        "temp_b": None,
    }


def _dynamic_generate(query: str, kg_context: list, client: OpenAI) -> tuple:
    """KG context 기반 LLM 페르소나 동적 생성 (kg_context가 있을 때만 호출)."""
    context_str = "\n".join([f"- {c}" for c in kg_context[:3]]) if kg_context else "없음"

    prompt = f"""Query: {query}
Past context: {context_str}

Generate 2 genuinely contrasting expert personas with different worldviews.
Each should catch blind spots the other misses.
Return valid JSON only: {{"persona_a": "...", "persona_b": "..."}}"""

    try:
        response = client.chat.completions.create(
            model="gpt-5-mini",
            messages=[
                {"role": "system", "content": "Generate contrasting personas. Return valid JSON only."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
        )
        data = json.loads(response.choices[0].message.content)
        return data["persona_a"], data["persona_b"]
    except Exception:
        return PERSONA_PRESETS["default"]
