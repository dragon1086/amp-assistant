"""
cser_gate.py — CSER 게이트 자동 재시도 로직

CSER(Cognitive Synthesis Emergence Rate) < 0.30 감지 시:
  round=2 → round=4로 자동 심화 (더 깊은 토론)
  round=4 → temperature diversity boost 후 재시도
  재시도 후에도 낮으면 → 낮은 신뢰도 경고와 함께 반환

CSER 게이트 임계값: θ = 0.30 (논문 기준)
최대 재시도: 1회 (비용 2배 허용)
"""

import logging

logger = logging.getLogger(__name__)

CSER_GATE_THRESHOLD = 0.30
MAX_GATE_RETRIES = 1  # 재시도 1회 (비용 방어)


def should_retry(cser: float, current_rounds: int, retry_count: int) -> tuple[bool, int, str]:
    """
    CSER gate 판단.

    Returns:
        (should_retry, next_rounds, action_description)
    """
    if cser >= CSER_GATE_THRESHOLD:
        return False, current_rounds, "pass"

    if retry_count >= MAX_GATE_RETRIES:
        return False, current_rounds, "max_retries_reached"

    if current_rounds == 2:
        # 2-round → 4-round 심화
        return True, 4, "upgrade_to_4round"
    else:
        # 4-round도 낮으면 재시도 포기, low_confidence 플래그
        return False, current_rounds, "low_cser_flagged"


def patch_result_with_gate_info(result: dict, gate_triggered: bool, gate_action: str, original_cser: float) -> dict:
    """result dict에 gate 메타정보 추가."""
    result["cser_gate_triggered"] = gate_triggered
    result["cser_gate_action"] = gate_action

    if gate_action == "low_cser_flagged":
        result["confidence"] = "low"
        result["cser_warning"] = (
            f"⚠️ CSER {original_cser:.3f} < θ{CSER_GATE_THRESHOLD} — "
            "두 에이전트 응답이 유사합니다. 다른 관점이 필요할 수 있습니다."
        )
        logger.warning(f"[cser_gate] CSER={original_cser:.3f} 낮음 — 에코챔버 가능성")

    elif gate_action == "upgrade_to_4round":
        result["cser_gate_note"] = f"CSER={original_cser:.3f}→ 4-round 심화로 자동 업그레이드"
        logger.info(f"[cser_gate] CSER={original_cser:.3f} < θ → 4-round 재시도")

    return result
