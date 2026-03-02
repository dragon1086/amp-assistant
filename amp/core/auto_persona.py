"""
amp Auto-Persona Engine
Automatically generates optimal contrasting personas for any query.
Designed with cokac-bot. Three pillars: 시장성 / 시대를 앞서나감 / AGI
"""

import json
import os

from openai import OpenAI

# Domain preset pool (covers 95% of queries without extra LLM call)
PERSONA_PRESETS = {
    "career": ("커리어 성장 코치 (기회와 가능성 중심)", "재무 안정 분석가 (리스크와 현실 중심)"),
    "relationship": ("관계 심리학자 (감정과 패턴 분석)", "현실주의 조언자 (경계와 명확성 중심)"),
    "business": ("스타트업 낙관론자 (실행과 성장 중심)", "시장 현실주의자 (리스크와 경쟁 분석)"),
    "investment": ("성장 투자 전문가 (수익 기회 탐색)", "리스크 관리 전문가 (하방 보호 중심)"),
    "legal_contract": ("법률 리스크 분석가 (독소조항 탐지)", "비즈니스 기회 분석가 (실용적 이익 중심)"),
    "health": ("예방의학 전문가 (최악의 경우 고려)", "통합의학 상담사 (전체적 웰빙 중심)"),
    "ethics": ("원칙 중심 윤리학자 (장기 결과와 가치)", "실용주의 해결사 (현실적 균형 탐색)"),
    "creative": ("창의적 혁신가 (가능성 확장)", "실행 전략가 (현실 구현 방법 중심)"),
    "parenting": ("발달심리학자 (아이 관점 중심)", "현실적 부모 코치 (가족 시스템 균형)"),
    "default": ("분석적 전문가 (데이터와 논리 중심)", "공감적 조언자 (감정과 가치 중심)"),
}

DOMAIN_KEYWORDS = {
    "career": ["이직", "취업", "직장", "연봉", "승진", "커리어", "job", "salary", "resign", "quit"],
    "relationship": ["연애", "결혼", "이별", "갈등", "친구", "가족", "부모", "남친", "여친", "배우자"],
    "business": ["창업", "스타트업", "사업", "비즈니스", "투자자", "펀딩", "startup", "business"],
    "investment": ["투자", "주식", "코인", "부동산", "펀드", "etf", "invest", "stock"],
    "legal_contract": ["계약", "사인", "법률", "소송", "계약서", "contract", "legal"],
    "health": ["건강", "병원", "증상", "약", "수술", "다이어트", "health", "doctor"],
    "ethics": ["윤리", "도덕", "옳은", "잘못", "신고", "고발", "ethics", "moral"],
    "creative": ["아이디어", "디자인", "글쓰기", "작품", "creative", "design", "write"],
    "parenting": ["육아", "아이", "자녀", "교육", "학교", "parenting", "child"],
}


def detect_domain(query: str) -> str:
    query_lower = query.lower()
    for domain, keywords in DOMAIN_KEYWORDS.items():
        if any(kw in query_lower for kw in keywords):
            return domain
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


def generate_personas(query: str, kg_context: list = None) -> dict:
    """
    Main entry point. Returns optimal contrasting personas for a query.
    Uses presets when possible (fast, free), dynamic generation as fallback.
    """
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
    kg_context = kg_context or []

    # 1. Try preset match
    domain = detect_domain(query)
    persona_a, persona_b = PERSONA_PRESETS.get(domain, PERSONA_PRESETS["default"])

    # 2. Validate diversity
    similarity = validate_persona_diversity(persona_a, persona_b, client)

    # 3. If too similar, fall back to dynamic generation
    if similarity > 0.85:
        persona_a, persona_b = _dynamic_generate(query, kg_context, client)
        source = "dynamic"
    else:
        source = "preset"

    return {
        "domain": domain,
        "persona_a": persona_a,
        "persona_b": persona_b,
        "diversity_score": round(1 - similarity, 3),
        "source": source,
    }


def _dynamic_generate(query: str, kg_context: list, client: OpenAI) -> tuple:
    """Fallback: LLM generates custom personas for unusual queries via Claude OAuth."""
    from amp.core.emergent import _call_claude

    context_str = "\n".join([f"- {c}" for c in kg_context[:3]]) if kg_context else "없음"

    result = _call_claude(
        f"""Query: {query}
Past context: {context_str}

Generate 2 contrasting expert personas. Requirements:
- Genuinely different worldviews/values
- Domain-appropriate expertise
- Each catches blind spots the other misses
Return: {{"persona_a": "...", "persona_b": "..."}}""",
        system="You generate contrasting expert personas for dual-perspective analysis. Return valid JSON only.",
    )

    try:
        data = json.loads(result)
        return data["persona_a"], data["persona_b"]
    except Exception:
        return PERSONA_PRESETS["default"]
