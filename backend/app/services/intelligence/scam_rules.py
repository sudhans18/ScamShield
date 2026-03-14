from __future__ import annotations

import re
from typing import Any

FEE_KEYWORDS = (
    "registration fee",
    "processing fee",
    "visa fee",
)

URGENCY_KEYWORDS = (
    "urgent",
    "limited seats",
    "apply today",
    "tonight",
)

LOW_SKILL_ROLES = (
    "security guard",
    "helper",
)

SALARY_ANOMALY_THRESHOLD = 50000


def _normalize(text: str) -> str:
    """Lowercase and compress whitespace for robust keyword matching."""
    return re.sub(r"\s+", " ", text).strip().lower()


def _has_keyword(text: str, keywords: tuple[str, ...]) -> bool:
    normalized = _normalize(text)
    return any(keyword in normalized for keyword in keywords)


def _detect_fee_requested(text: str, entities: dict[str, Any]) -> bool:
    """Detect fee requests from text keywords or parsed fee amount."""
    fee_value = entities.get("fee")
    if isinstance(fee_value, (int, float)) and fee_value > 0:
        return True
    return _has_keyword(text, FEE_KEYWORDS)


def _detect_urgency_language(text: str) -> bool:
    """Detect pressure tactics that push immediate action."""
    return _has_keyword(text, URGENCY_KEYWORDS)


def _detect_salary_anomaly(entities: dict[str, Any]) -> bool:
    """Flag unusually high salaries for low-skill roles."""
    salary = entities.get("salary")
    role = str(entities.get("role") or "")

    if not isinstance(salary, (int, float)):
        return False

    if salary <= SALARY_ANOMALY_THRESHOLD:
        return False

    role_normalized = _normalize(role)
    return any(low_skill_role in role_normalized for low_skill_role in LOW_SKILL_ROLES)


def _detect_unknown_company(entities: dict[str, Any]) -> bool:
    """Flag messages where a clear company name is absent."""
    company = entities.get("company")
    if company is None:
        return True

    company_text = str(company).strip()
    return not company_text


def detect_scam_signals(text: str, entities: dict[str, Any]) -> dict[str, Any]:
    """Evaluate scam-like patterns in a job message.

    Returns:
    {
      "signals": ["fee_requested", ...],
      "signal_count": 2
    }
    """
    signals: list[str] = []

    if _detect_fee_requested(text, entities):
        signals.append("fee_requested")

    if _detect_urgency_language(text):
        signals.append("urgency_language")

    if _detect_salary_anomaly(entities):
        signals.append("salary_anomaly")

    if _detect_unknown_company(entities):
        signals.append("unknown_company")

    return {
        "signals": signals,
        "signal_count": len(signals),
    }
