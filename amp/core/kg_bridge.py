"""
kg_bridge.py — amp 대화 결과 → KG 자동 저장 (SQLite + 벡터 임베딩)

kg.py의 KnowledgeGraph를 사용:
  - 저장: SQLite (~/.amp/kg.db)
  - 검색: OpenAI 임베딩 + 코사인 유사도
  - JSON 파일 방식 완전 대체

저장 형식:
  - 질문 노드: type=question
  - 분석 노드: type=insight (CSER 포함)
  - 엣지: 질문 → 분석 (PRODUCES)
"""

import logging
import threading
from pathlib import Path

logger = logging.getLogger(__name__)


def _get_kg():
    """KnowledgeGraph 인스턴스 반환. import 오류 시 None."""
    try:
        from amp.core.kg import KnowledgeGraph
        return KnowledgeGraph()
    except Exception as e:
        logger.debug(f"[kg_bridge] KG 초기화 실패 (무시): {e}")
        return None


def save_to_emergent_kg(
    query: str,
    result: dict,
    async_mode: bool = True,
) -> None:
    """
    emergent 분석 결과를 KG에 저장.

    Args:
        query:      사용자 질문
        result:     emergent.run() 반환값
        async_mode: True = 백그라운드 스레드 (응답 속도 영향 없음)
    """
    def _do_save():
        kg = _get_kg()
        if kg is None:
            return

        try:
            cser = result.get("cser", 0.0)
            answer = result.get("answer", "")
            model_a = result.get("agent_a_label", "amp").split("/")[-1]
            model_b = result.get("agent_b_label", "amp").split("/")[-1]
            rounds = result.get("rounds", 2)
            agreements = result.get("agreements", [])

            # 1. 질문 노드
            q_id = kg.add(
                content=query,
                tags=["question", "amp-conversation"],
                node_type="question",
                metadata={"source": "amp-conversation"},
            )

            # 2. 분석 노드 (CSER 포함)
            cser_flag = "✅" if cser >= 0.30 else "⚠️"
            insight_content = (
                f"[CSER={cser:.3f}{cser_flag} | {rounds}-round | "
                f"{model_a}×{model_b}]\n\n{answer[:800]}"
            )
            a_id = kg.add(
                content=insight_content,
                tags=["insight", "emergent", f"cser_{cser:.2f}", model_a],
                node_type="insight",
                metadata={
                    "source": "amp-emergent",
                    "cser": cser,
                    "rounds": rounds,
                    "agreements": agreements[:3],
                },
            )

            # 3. 엣지: 질문 → 분석
            kg.relate(q_id, a_id, "PRODUCES", weight=cser)

            logger.info(
                f"[kg_bridge] KG 저장 완료: q={q_id} a={a_id} CSER={cser:.3f}"
            )

        except Exception as e:
            logger.warning(f"[kg_bridge] 저장 실패 (무시): {e}")

    if async_mode:
        t = threading.Thread(target=_do_save, daemon=True)
        t.start()
    else:
        _do_save()


def search_kg(query: str, top_k: int = 3) -> list[dict]:
    """
    KG에서 관련 노드 시맨틱 검색.
    emergent 분석 시작 전 컨텍스트 주입에 활용.

    Returns:
        [{'id', 'content', 'tags', 'type', 'similarity'}, ...]
    """
    kg = _get_kg()
    if kg is None:
        return []
    try:
        return kg.search(query, top_k=top_k)
    except Exception as e:
        logger.debug(f"[kg_bridge] 검색 실패 (무시): {e}")
        return []
