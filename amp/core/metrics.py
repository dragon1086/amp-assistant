"""CSER (Cognitive Synthesis Emergence Rate) calculation.

CSER measures how much emergent insight is produced when two agents
collaborate independently. High CSER = healthy divergent thinking.
Low CSER = echo chamber.
"""

import re
from typing import Any


def _extract_ideas(text: str) -> list[str]:
    """Extract distinct idea units from text.

    Simple heuristic: split on sentences and bullet points,
    normalize, deduplicate similar phrases.
    """
    # Split on sentence boundaries and bullet markers
    separators = re.compile(r"[.!?]\s+|[\n]+[-*•·]\s*|\n{2,}")
    raw = separators.split(text)

    ideas = []
    for chunk in raw:
        chunk = chunk.strip()
        # Filter noise
        if len(chunk) < 15:
            continue
        # Normalize: lowercase, strip punctuation at edges
        normalized = re.sub(r"^[-*•·\d.)\s]+", "", chunk).strip().lower()
        if normalized:
            ideas.append(normalized)

    return ideas


def _ideas_overlap(idea_a: str, idea_b: str, threshold: float = 0.4) -> bool:
    """Check if two ideas share significant keyword overlap (Jaccard similarity)."""
    words_a = set(re.findall(r"\b\w{3,}\b", idea_a))
    words_b = set(re.findall(r"\b\w{3,}\b", idea_b))

    if not words_a or not words_b:
        return False

    intersection = words_a & words_b
    union = words_a | words_b
    jaccard = len(intersection) / len(union)
    return jaccard >= threshold


def calculate_cser(agent_a_text: str, agent_b_text: str) -> dict[str, Any]:
    """Calculate CSER between two agent outputs.

    CSER = (unique_insights_A + unique_insights_B) / total_insights

    Returns:
        dict with keys: cser, unique_a, unique_b, shared, total,
                        confidence
    """
    ideas_a = _extract_ideas(agent_a_text)
    ideas_b = _extract_ideas(agent_b_text)

    if not ideas_a and not ideas_b:
        return {
            "cser": 0.0,
            "unique_a": [],
            "unique_b": [],
            "shared": [],
            "total": 0,
            "confidence": "low",
        }

    # Find shared vs unique ideas
    shared = []
    unique_a = []
    unique_b = list(ideas_b)  # start assuming all B is unique

    for idea_a in ideas_a:
        matched = False
        for idea_b in list(unique_b):
            if _ideas_overlap(idea_a, idea_b):
                if idea_a not in [s[0] for s in shared]:
                    shared.append((idea_a, idea_b))
                unique_b = [i for i in unique_b if i != idea_b]
                matched = True
                break
        if not matched:
            unique_a.append(idea_a)

    total = len(unique_a) + len(unique_b) + len(shared)
    if total == 0:
        cser = 0.0
    else:
        cser = (len(unique_a) + len(unique_b)) / total

    # Clamp to [0, 1]
    cser = max(0.0, min(1.0, cser))

    return {
        "cser": round(cser, 3),
        "unique_a": unique_a,
        "unique_b": unique_b,
        "shared": [s[0] for s in shared],
        "total": total,
        "confidence": "high" if cser > 0.3 else "low",
    }


def format_cser(cser: float, confidence: str) -> str:
    """Format CSER for display."""
    bar_length = 10
    filled = int(cser * bar_length)
    bar = "█" * filled + "░" * (bar_length - filled)
    check = "✅" if confidence == "high" else "⚠️"
    label = "높음" if confidence == "high" else "낮음"
    return f"{check} CSER {cser:.2f} [{bar}] (신뢰도: {label})"
