from __future__ import annotations

from typing import Any

_REASON_TRANSLATIONS: dict[str, str] = {
    "registration fee requested": "Registration fee mangi gayi",
    "urgency language detected": "Jaldi apply karne ka dabav banaya gaya",
    "salary anomaly": "Salary asamanya roop se zyada batayi gayi",
    "company not identified": "Company verify nahi hui",
    "fee requested": "Fee mangi gayi",
    "unknown company": "Company verify nahi hui",
}


def _to_percent(score: Any) -> int:
    try:
        value = float(score)
    except (TypeError, ValueError):
        return 0
    value = max(0.0, min(1.0, value))
    return int(round(value * 100))


def _headline(level: str, percent: int) -> str:
    if level == "HIGH" or percent > 60:
        return "KHATRA!"
    if level == "MEDIUM" or percent >= 30:
        return "SAAVDHAN!"
    return "SURAKSHIT"


def _translate_reason(reason: str) -> str:
    normalized = reason.strip().lower()
    return _REASON_TRANSLATIONS.get(normalized, reason.strip())


def generate_hindi_response(result: dict[str, Any]) -> str:
    """Generate a user-facing Hindi response from scam analysis result."""
    risk_score = result.get("risk_score", 0)
    risk_level = str(result.get("risk_level", "")).upper()
    reasons = result.get("reasons") or []

    percent = _to_percent(risk_score)
    title = _headline(risk_level, percent)

    lines: list[str] = [
        title,
        "",
        "Yeh naukri sandesh farzi ho sakta hai." if percent >= 30 else "Yeh naukri sandesh filhal kam jokhim wala lagta hai.",
        "",
        f"Risk: {percent}%",
        "",
    ]

    if reasons:
        lines.append("Karan:")
        for reason in reasons:
            lines.append(f"* {_translate_reason(str(reason))}")
        lines.append("")

    if percent >= 60:
        lines.append("Paise mat bhejein.")
    elif percent >= 30:
        lines.append("Pehle company aur offer verify karein.")
    else:
        lines.append("Phir bhi documents aur company details verify karein.")

    return "\n".join(lines)
