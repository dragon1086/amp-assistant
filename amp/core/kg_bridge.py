"""
kg_bridge.py — amp 대화 결과 → emergent KG 자동 저장

각 emergent 분석 결과를 ~/emergent/data/knowledge-graph.json에 노드로 저장.
시간이 지날수록 KG가 풍부해지며, 다음 분석의 컨텍스트로 활용 가능.

저장 형식:
  - 질문 노드: type=question, source=amp-conversation
  - 분석 노드: type=insight, source=amp-{model_a}
  - 엣지: 질문 → 분석 (PRODUCES), 분석 → 이전 노드 (EXTENDS)

의존성: ~/emergent/src/add_node_safe.py (있으면 사용, 없으면 건너뜀)
"""

import json
import logging
import os
import subprocess
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

# emergent KG 경로
EMERGENT_KG_PATH = Path.home() / "emergent" / "data" / "knowledge-graph.json"
ADD_NODE_SCRIPT = Path.home() / "emergent" / "src" / "add_node_safe.py"


def _is_available() -> bool:
    """emergent KG와 add_node_safe.py가 모두 있는지 확인."""
    return EMERGENT_KG_PATH.exists() and ADD_NODE_SCRIPT.exists()


def _get_last_node_id() -> str | None:
    """KG에서 가장 최근 노드 ID 반환."""
    try:
        kg = json.loads(EMERGENT_KG_PATH.read_text(encoding="utf-8"))
        nodes = kg.get("nodes", [])
        if nodes:
            return nodes[-1]["id"]
    except Exception:
        pass
    return None


def _add_node(payload: dict) -> str | None:
    """
    add_node_safe.py를 통해 노드 추가.
    Returns: 추가된 노드 ID 또는 None
    """
    try:
        result = subprocess.run(
            ["python3", str(ADD_NODE_SCRIPT)],
            input=json.dumps(payload, ensure_ascii=False),
            capture_output=True,
            text=True,
            timeout=15,
            env={**os.environ, "EMERGENT_KG_PATH": str(EMERGENT_KG_PATH)},
        )
        if result.returncode == 0:
            node_id = result.stdout.strip().split("\n")[-1]  # 마지막 줄 = 노드 ID
            return node_id
        else:
            logger.warning(f"[kg_bridge] add_node 실패: {result.stderr[:100]}")
    except Exception as e:
        logger.warning(f"[kg_bridge] 노드 추가 오류: {e}")
    return None


def save_to_emergent_kg(
    query: str,
    result: dict,
    async_mode: bool = True,
) -> None:
    """
    emergent 분석 결과를 KG에 비동기 저장.

    Args:
        query:      사용자 질문
        result:     emergent.run() 반환값
        async_mode: True = 백그라운드 스레드 (응답 속도 영향 없음)
    """
    if not _is_available():
        logger.debug("[kg_bridge] emergent KG 미존재 — 저장 건너뜀")
        return

    def _do_save():
        try:
            cser = result.get("cser", 0.0)
            answer = result.get("answer", "")
            model_a = result.get("agent_a_label", "amp").split("/")[-1]
            rounds = result.get("rounds", 2)

            # 직전 노드 ID (연결 대상)
            prev_node_id = _get_last_node_id()

            # 1. 질문 노드
            q_label = query[:120]
            q_payload = {
                "label": q_label,
                "content": query[:500],
                "type": "question",
                "source": "amp-conversation",
                "tags": ["amp", "conversation"],
                "memory_type": "Episodic",
                "domain": "amp_interaction",
                "subdomain": "user_query",
                "edge_to": prev_node_id or "",
                "edge_relation": "temporal_bridge",
                "edge_label": "대화 흐름",
            }
            q_id = _add_node(q_payload)
            if not q_id:
                return

            # 2. 분석 노드 (질문 노드에 엣지 연결)
            cser_flag = "✅" if cser >= 0.30 else "⚠️"
            a_label = f"amp 분석: {query[:60]}"
            a_payload = {
                "label": a_label,
                "content": (
                    f"[CSER={cser:.3f}{cser_flag} | {rounds}-round | {model_a}]\n\n"
                    f"{answer[:800]}"
                ),
                "type": "insight",
                "source": f"amp-{model_a}",
                "tags": ["amp", "emergent", f"cser_{cser:.2f}"],
                "memory_type": "Semantic",
                "domain": "amp_interaction",
                "subdomain": "emergent_synthesis",
                "edge_to": q_id,
                "edge_relation": "PRODUCES",
                "edge_label": f"CSER={cser:.3f}",
                "cross_source": True,  # 항상 cross-source (질문→분석)
            }
            a_id = _add_node(a_payload)

            if a_id:
                logger.info(f"[kg_bridge] KG 저장 완료: q={q_id} a={a_id} CSER={cser:.3f}")
        except Exception as e:
            logger.warning(f"[kg_bridge] 저장 실패 (무시): {e}")

    if async_mode:
        t = threading.Thread(target=_do_save, daemon=True)
        t.start()
    else:
        _do_save()
