from __future__ import annotations

from typing import Any

from app.services.graph.syndicate_detector import entity_belongs_to_syndicate

SIGNAL_WEIGHTS: dict[str, float] = {
    "fee_requested": 0.4,
    "urgency_language": 0.2,
    "salary_anomaly": 0.3,
    "unknown_company": 0.1,
}


def _risk_level_from_score(score: float) -> str:
    """Map numeric risk score to a categorical level."""
    if score < 0.3:
        return "LOW"
    if score <= 0.6:
        return "MEDIUM"
    return "HIGH"


def calculate_risk(signals: list[str], entities: dict[str, Any] | None = None) -> dict[str, Any]:
    """Calculate weighted scam risk score from detected signal names.

    Unknown signals are ignored. Duplicate signals are counted once.
    Returns a score in the range [0.0, 1.0] and a categorical risk level.
    """
    unique_signals = set(signals)
    score = sum(SIGNAL_WEIGHTS.get(signal, 0.0) for signal in unique_signals)

    syndicate_match = False
    if entities:
        try:
            syndicate_match = entity_belongs_to_syndicate(entities)
        except Exception:
            syndicate_match = False

    if syndicate_match:
        score += 0.25

    # Clamp to [0, 1] and round for stable API output.
    score = max(0.0, min(1.0, score))
    score = round(score, 2)

    return {
        "risk_score": score,
        "risk_level": _risk_level_from_score(score),
        "syndicate_match": syndicate_match,
    }
