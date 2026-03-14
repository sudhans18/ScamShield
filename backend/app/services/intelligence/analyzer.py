from __future__ import annotations

from typing import Any

from .entity_extractor import extract_entities
from .llm_classifier import classify_with_llm
from .risk_scorer import calculate_risk
from .scam_rules import detect_scam_signals

SIGNAL_REASON_MAP: dict[str, str] = {
    "fee_requested": "registration fee requested",
    "urgency_language": "urgency language detected",
    "salary_anomaly": "salary anomaly",
    "unknown_company": "company not identified",
}


def _signals_to_reasons(signals: list[str]) -> list[str]:
    """Convert internal signal names to user-facing reasons."""
    reasons: list[str] = []
    for signal in signals:
        reasons.append(SIGNAL_REASON_MAP.get(signal, signal.replace("_", " ")))
    return reasons


def _merge_with_llm(
    base_result: dict[str, Any],
    llm_result: dict[str, Any],
    signals: list[str],
) -> dict[str, Any]:
    """Merge deterministic pipeline output with optional LLM enrichment."""
    llm_score = llm_result.get("risk_score")
    if isinstance(llm_score, (int, float)):
        # Blend deterministic and LLM score for medium-risk ambiguity.
        blended_score = round((float(base_result["risk_score"]) + float(llm_score)) / 2, 2)
        base_result["risk_score"] = blended_score
        base_result["risk_level"] = (
            "LOW" if blended_score < 0.3 else "MEDIUM" if blended_score <= 0.6 else "HIGH"
        )

    llm_signals = llm_result.get("signals")
    if isinstance(llm_signals, list):
        for signal in llm_signals:
            signal_text = str(signal).strip()
            if signal_text and signal_text not in signals:
                signals.append(signal_text)

    llm_reason = llm_result.get("reason")
    if isinstance(llm_reason, str) and llm_reason.strip():
        base_result.setdefault("llm_reason", llm_reason.strip())

    return base_result


def analyze_text(text: str) -> dict[str, Any]:
    """Run the full scam intelligence pipeline for a job message.

    Pipeline:
    1. Extract entities
    2. Detect rule-based scam signals
    3. Compute weighted risk score and level
    4. Run LLM deep analysis only for medium-risk cases
    5. Merge and return consolidated result
    """
    try:
        entities = extract_entities(text)
        signal_result = detect_scam_signals(text, entities)
        signals = list(signal_result.get("signals", []))

        risk_result = calculate_risk(signals)

        result: dict[str, Any] = {
            "risk_score": risk_result["risk_score"],
            "risk_level": risk_result["risk_level"],
            "reasons": _signals_to_reasons(signals),
            "entities": entities,
        }

        score = float(result["risk_score"])
        if 0.3 <= score <= 0.6:
            try:
                llm_result = classify_with_llm(text)
                result = _merge_with_llm(result, llm_result, signals)
                result["reasons"] = _signals_to_reasons(signals)
            except Exception as exc:  # pragma: no cover
                # Keep pipeline resilient if external API is unavailable.
                result["llm_error"] = str(exc)

        return result
    
    except RecursionError as e:
        return {"error": f"RecursionError: {str(e)}"}
