"""
agent_registration.py — amp → MACRS Registry 자동 등록
Multi-Agent Capability Registry System (MACRS)

amp 봇 시작 시 호출:
  from amp.core.agent_registration import register_amp
  register_amp()

등록 내용:
  - agent: "amp" (display_name, endpoint)
  - capabilities: emergent_analysis, image_generation, quick_answer
"""

import sys
import os
import logging

# MACRS registry_client 경로 추가
_REGISTRY_PATH = os.path.expanduser("~/ai-comms")
if _REGISTRY_PATH not in sys.path:
    sys.path.insert(0, _REGISTRY_PATH)

logger = logging.getLogger(__name__)

# amp MCP 서버 주소 (기본값)
AMP_MCP_ENDPOINT = "http://127.0.0.1:3010"

# 능력 정의
CAPABILITIES = [
    {
        "name": "emergent_analysis",
        "description": (
            "2-agent 독립 분석 (emergent mode). "
            "GPT × Claude 두 AI가 독립적으로 분석 후 합성. "
            "CSER로 독창성 측정. 전략 검토, 의사결정, 장단점 분석에 최적."
        ),
        "keywords": [
            "분석", "검토", "결정", "장단점", "비교", "평가",
            "전략", "pros", "cons", "review", "analyze", "compare",
            "판단", "의견", "어떻게 생각", "어느게 나아", "추천",
        ],
        "cost_level": "medium",
        "avg_latency_ms": 15000,
    },
    {
        "name": "debate",
        "description": (
            "4-round 심층 토론 (emergent 4-round). "
            "A 제시 → B 반박 → A 재반박 → B 재반박 → 합성. "
            "복잡한 결정, 찬반 검토에 최적."
        ),
        "keywords": [
            "토론", "찬반", "vs", "대결", "심층 분석", "비교해줘",
            "debate", "devil's advocate", "논쟁", "반박",
        ],
        "cost_level": "high",
        "avg_latency_ms": 30000,
    },
    {
        "name": "image_generation",
        "description": "AI 이미지 생성 (Gemini 3.1 Flash, DALL-E3 지원).",
        "keywords": [
            "이미지", "그림", "생성", "만들어줘", "그려줘",
            "image", "generate", "draw", "이미지 생성",
        ],
        "cost_level": "high",
        "avg_latency_ms": 10000,
    },
    {
        "name": "quick_answer",
        "description": "단일 LLM 빠른 응답 (solo mode). 간단한 질문, 번역, 요약.",
        "keywords": [
            "뭐야", "알려줘", "설명해", "번역", "요약",
            "what is", "how", "explain", "summarize", "translate",
        ],
        "cost_level": "low",
        "avg_latency_ms": 3000,
    },
]


def register_amp(db_path: str = None, endpoint: str = AMP_MCP_ENDPOINT) -> bool:
    """
    amp를 MACRS registry에 등록.

    Args:
        db_path: registry.db 경로 (None이면 기본값 사용)
        endpoint: amp MCP 서버 주소

    Returns:
        True = 성공, False = registry_client 없음 (무시하고 계속)
    """
    try:
        from registry_client import RegistryClient
    except ImportError:
        logger.warning(
            "[agent_registration] registry_client를 찾을 수 없음. "
            f"~/ai-comms/ 가 없거나 아직 설치 안 됨. 건너뜀. (경로: {_REGISTRY_PATH})"
        )
        return False

    try:
        kwargs = {"db_path": db_path} if db_path else {}
        client = RegistryClient(**kwargs)

        # 에이전트 등록
        client.register_agent(
            agent_id="amp",
            display_name="amp (2-agent reasoning)",
            description=(
                "2-agent emergent debate 시스템. "
                "GPT × Claude 독립 분석 후 합성. CSER 측정 내장. "
                "분석/검토/결정 태스크 전문."
            ),
            endpoint=endpoint,
        )

        # 능력 등록
        for cap in CAPABILITIES:
            client.register_capability(
                agent_id="amp",
                name=cap["name"],
                description=cap["description"],
                keywords=cap["keywords"],
                cost_level=cap["cost_level"],
                avg_latency_ms=cap["avg_latency_ms"],
            )

        client.close()
        logger.info(f"[agent_registration] amp registry 등록 완료 ({len(CAPABILITIES)}개 능력)")
        print(f"[amp] MACRS registry 등록 완료: {len(CAPABILITIES)}개 능력")
        return True

    except Exception as e:
        logger.warning(f"[agent_registration] registry 등록 실패 (무시): {e}")
        return False


def start_heartbeat(interval_sec: int = 60, db_path: str = None) -> None:
    """
    백그라운드 스레드로 heartbeat 전송 (1분마다).
    봇이 살아있는 동안 registry에서 'active' 상태 유지.
    """
    import threading

    def _beat():
        import time
        try:
            from registry_client import RegistryClient
            kwargs = {"db_path": db_path} if db_path else {}
            client = RegistryClient(**kwargs)
            while True:
                try:
                    client.heartbeat("amp")
                except Exception:
                    pass
                time.sleep(interval_sec)
        except ImportError:
            pass  # registry 없으면 조용히 종료

    t = threading.Thread(target=_beat, daemon=True)
    t.start()
    logger.info("[agent_registration] heartbeat 스레드 시작")


if __name__ == "__main__":
    # 직접 실행 시 테스트
    ok = register_amp()
    print("등록 결과:", "✅ 성공" if ok else "⚠️ registry 없음 (무시)")
