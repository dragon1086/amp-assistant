"""Router - automatically select the best mode for a query.

Modes:
  solo     - Simple factual queries, greetings, short answers
  pipeline - Structured tasks: code gen, documents, step-by-step
  emergent - Analysis, decisions, review, pros/cons

Detection strategy:
  1. Keyword matching (high precision)
  2. Query length heuristic
  3. Question type detection
"""

import re


# Keywords that trigger each mode
EMERGENT_KEYWORDS = [
    # Decision/analysis requests
    "해야 할까", "해야할까", "어떻게 생각", "뭐가 좋을까", "추천해줘", "추천해 줘",
    "장단점", "pros and cons", "pros/cons", "trade-off", "tradeoff",
    "문제점", "위험", "risk", "risks", "위험성",
    "검토해", "리뷰해", "review this", "review the", "check this",
    "이게 맞아", "맞나요", "맞을까", "is this correct", "is this right",
    "should i", "should we", "어떻게 해야", "의견", "opinion",
    "분석해", "analyze", "analysis", "평가해", "evaluate",
    "비교해", "compare", "비교", "어느 게 낫", "which is better",
    "준비", "strategy", "전략", "plan", "계획",
    "어떻게 하면", "best way", "best approach",
    "투자", "결정", "decision", "선택", "choice",
]

PIPELINE_KEYWORDS = [
    # Code generation
    "코드", "code", "코딩", "coding", "프로그램", "program",
    "함수", "function", "class", "클래스", "script", "스크립트",
    "python", "javascript", "typescript", "java", "golang", "rust",
    # Document creation
    "문서", "document", "report", "보고서", "readme", "spec",
    "이메일", "email", "letter", "편지", "proposal", "제안서",
    # Step-by-step tasks
    "단계", "step", "steps", "how to", "방법", "절차",
    "설치", "install", "설정", "configure", "setup",
    "만들어", "만들어줘", "만들어 줘", "create", "build", "generate", "생성",
    "작성해", "작성해줘", "write a", "write the",
    "sort", "정렬", "filter", "필터", "parse", "파싱",
    "list", "목록", "table", "테이블",
]

SOLO_PATTERNS = [
    r"^(안녕|hello|hi|hey|반가|ㅎㅇ|하이)",
    r"^(what is|what's|뭐야|뭔가요|뭐예요|무엇)",
    r"^(how much|얼마|언제|when|where|어디)",
    r"^(who is|who's|누구)",
    r"\?$",  # Simple questions ending with ?
]


def detect_mode(query: str, default_mode: str = "auto") -> str:
    """Detect the best mode for a query.

    Args:
        query: User's input text
        default_mode: Configured default ("auto", "solo", "pipeline", "emergent")

    Returns:
        One of: "solo", "pipeline", "emergent"
    """
    if default_mode != "auto":
        return default_mode

    query_lower = query.lower().strip()
    query_len = len(query.split())

    # Very short queries → solo
    if query_len <= 3:
        return "solo"

    # Check for solo patterns (simple greetings/questions)
    for pattern in SOLO_PATTERNS:
        if re.search(pattern, query_lower, re.IGNORECASE):
            if query_len <= 8:
                return "solo"

    # Check emergent keywords first (higher value)
    for keyword in EMERGENT_KEYWORDS:
        if keyword in query_lower:
            return "emergent"

    # Check pipeline keywords
    for keyword in PIPELINE_KEYWORDS:
        if keyword in query_lower:
            return "pipeline"

    # Length heuristic: long complex queries → emergent
    if query_len > 20:
        return "emergent"

    # Medium queries → pipeline
    if query_len > 8:
        return "pipeline"

    # Short simple queries → solo
    return "solo"


def describe_mode(mode: str) -> str:
    """Human-readable description of selected mode."""
    descriptions = {
        "solo": "solo (단일 응답)",
        "pipeline": "pipeline (계획→해결→검토→수정)",
        "emergent": "emergent (2-agent 독립 분석)",
    }
    return descriptions.get(mode, mode)
