from __future__ import annotations

import re
from typing import Any


_STOP_TOKENS = (
    "salary",
    "sal",
    "pay",
    "wage",
    "fee",
    "registration",
    "call",
    "contact",
    "phone",
    "mobile",
    "whatsapp",
    "agent",
    "broker",
    "company",
    "urgent",
    "immediate",
    "joining",
    "interview",
)

_COMMON_LOCATIONS = {
    "dubai",
    "abu dhabi",
    "doha",
    "muscat",
    "qatar",
    "kuwait",
    "oman",
    "bahrain",
    "saudi",
    "riyadh",
    "jeddah",
    "delhi",
    "new delhi",
    "mumbai",
    "navi mumbai",
    "pune",
    "hyderabad",
    "bengaluru",
    "bangalore",
    "chennai",
    "kolkata",
    "kochi",
    "kerala",
    "goa",
    "lucknow",
    "jaipur",
    "ahmedabad",
    "surat",
    "noida",
    "gurgaon",
    "gurugram",
    "faridabad",
    "patna",
    "bhopal",
    "indore",
    "nagpur",
    "kanpur",
    "vijayawada",
    "vizag",
    "visakhapatnam",
}

_URGENCY_PHRASES = (
    "urgent",
    "limited seats",
    "apply today",
    "apply now",
    "only today",
    "last date",
    "hurry",
    "immediately",
    "asap",
    "do not miss",
    "last chance",
    "act now",
    "respond immediately",
    "jaldi",
    "abhi",
    "turant",
    "kal tak",
    "aaj",
)

_PHONE_CANDIDATE_RE = re.compile(r"(?<!\w)(?:\+?\d[\d\s\-()]{8,}\d)")
_NUMBER_RE = re.compile(r"\b(?:\d{1,3}(?:,\d{2,3})+|\d+)(?:\.\d+)?\b")
_UPI_RE = re.compile(r"\b[a-zA-Z0-9.\-_]{2,}@[a-zA-Z]{2,}\b")


def _to_int(number_text: str) -> int:
    return int(float(number_text.replace(",", "")))


def _normalize_phone_candidate(candidate: str) -> str | None:
    digits = re.sub(r"\D", "", candidate or "")
    if not digits or len(digits) < 10 or len(digits) > 15:
        return None

    if len(digits) == 12 and digits.startswith("91") and digits[2] in "6789":
        return digits[-10:]
    if len(digits) == 11 and digits.startswith("0") and digits[1] in "6789":
        return digits[-10:]
    if len(digits) == 10 and digits[0] in "6789":
        return digits

    return f"+{digits}"


def _extract_phones(text: str) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for match in _PHONE_CANDIDATE_RE.finditer(text):
        candidate = (match.group(0) or "").strip()
        if not candidate:
            continue
        if "," in candidate and "+" not in candidate:
            continue
        normalized = _normalize_phone_candidate(candidate)
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def _extract_upi_ids(text: str) -> list[str]:
    seen: set[str] = set()
    upi_ids: list[str] = []
    for match in _UPI_RE.findall(text):
        upi_id = match.lower().strip()
        if upi_id not in seen:
            seen.add(upi_id)
            upi_ids.append(upi_id)
    return upi_ids


def _extract_amount_after_keywords(text: str, keywords: tuple[str, ...]) -> int | None:
    keyword_part = "|".join(re.escape(word) for word in keywords)
    amount_pattern = re.compile(
        rf"(?:\b(?:{keyword_part})\b)\s*(?::|=|is)?\s*(?:rs\.?|inr|aed)?\s*({_NUMBER_RE.pattern})",
        re.IGNORECASE,
    )
    match = amount_pattern.search(text)
    if match:
        return _to_int(match.group(1))

    reverse_pattern = re.compile(
        rf"({_NUMBER_RE.pattern})\s*(?:rs\.?|inr|aed)?\s*(?:\b(?:{keyword_part})\b)",
        re.IGNORECASE,
    )
    reverse_match = reverse_pattern.search(text)
    if reverse_match:
        return _to_int(reverse_match.group(1))

    return None


def _clean_phrase(value: str) -> str:
    value = re.sub(r"\s+", " ", value).strip(" -,:.;")
    return value


def _truncate_on_stop_tokens(value: str) -> str:
    pattern = r"\b(?:" + "|".join(re.escape(token) for token in _STOP_TOKENS) + r")\b"
    return re.split(pattern, value, maxsplit=1, flags=re.IGNORECASE)[0].strip()


def _extract_agent(text: str) -> str | None:
    match = re.search(
        r"\b(?:agent|broker|contact(?:\s+person)?)\s*[:=-]?\s*([A-Za-z][A-Za-z.'-]*)",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None
    return _clean_phrase(match.group(1)).title()


def _extract_location(text: str) -> str | None:
    patterns = [
        r"\b(?:location|loc|place)\s*[:=-]?\s*([A-Za-z][A-Za-z\s,.-]{2,60})",
        r"\b(?:based\s+in|posted\s+in|work\s+location)\s*[:=-]?\s*([A-Za-z][A-Za-z\s,.-]{2,60})",
        r"\b(?:in|at|from|to)\s+([A-Za-z][A-Za-z\s,.-]{2,50})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        location = _clean_phrase(match.group(1))
        location = _truncate_on_stop_tokens(location)
        location = _clean_phrase(location)
        if not location or any(char.isdigit() for char in location):
            continue
        if len(location.split()) > 5:
            location = " ".join(location.split()[:5])
        return location.title()

    lowered = text.lower()
    for loc in sorted(_COMMON_LOCATIONS, key=len, reverse=True):
        if re.search(rf"\b{re.escape(loc)}\b", lowered):
            return loc.title()
    return None


def _extract_role(text: str, location: str | None) -> str | None:
    tagged = re.search(
        r"\b(?:role|position|job|vacancy|opening|designation)\s*(?::|as|for)?\s+([A-Za-z][A-Za-z\s]{1,50}?)(?=\b(?:"
        + "|".join(_STOP_TOKENS)
        + r")\b|$)",
        text,
        re.IGNORECASE,
    )
    if tagged:
        return _clean_phrase(tagged.group(1))

    start = text
    if location:
        start = re.split(rf"\b{re.escape(location)}\b", start, flags=re.IGNORECASE, maxsplit=1)[0]
    start = re.split(
        r"\b(?:salary|fee|registration|call|contact|agent|broker|phone|company|location)\b",
        start,
        flags=re.IGNORECASE,
        maxsplit=1,
    )[0]
    role = _clean_phrase(start)
    if not role:
        return None
    words = role.split()
    if 1 <= len(words) <= 6:
        role_lower = role.lower()
        if role_lower in {"urgent", "immediate", "apply now", "apply today"}:
            return None
        return role
    return None


def _extract_company(text: str) -> str | None:
    patterns = [
        r"\b(?:company|organization|firm)\s*[:=-]?\s*([A-Za-z][A-Za-z0-9&.,'\-\s]{1,60}?)(?=\b(?:"
        + "|".join(_STOP_TOKENS)
        + r")\b|$)",
        r"\b(?:at|from)\s+([A-Za-z][A-Za-z0-9&.,'\-\s]{1,60}?)(?=\b(?:"
        + "|".join(_STOP_TOKENS)
        + r")\b|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        company = _clean_phrase(match.group(1)).title()
        if company:
            return company
    return None


def _extract_urgency_flags(text: str) -> list[str]:
    lowered = text.lower()
    matches: list[str] = []
    for phrase in _URGENCY_PHRASES:
        if phrase in lowered:
            matches.append(phrase)
    return matches


def extract_entities(text: str) -> dict[str, Any]:
    phones = _extract_phones(text)
    salary = _extract_amount_after_keywords(text, ("salary", "sal", "pay", "wage", "income"))
    fee = _extract_amount_after_keywords(text, ("fee", "fees", "registration fee", "service charge", "processing"))
    agent = _extract_agent(text)
    location = _extract_location(text)
    role = _extract_role(text, location)
    company = _extract_company(text)
    upi_ids = _extract_upi_ids(text)
    urgency_flags = _extract_urgency_flags(text)

    result: dict[str, Any] = {
        "phones": phones,
        "salary": salary,
        "fee": fee,
        "role": role,
        "location": location,
        "agent": agent,
        "company": company,
        "upi_ids": upi_ids,
        "urgency_flags": urgency_flags,
        "has_fee": fee is not None,
        "has_urgency": bool(urgency_flags),
    }
    return result
