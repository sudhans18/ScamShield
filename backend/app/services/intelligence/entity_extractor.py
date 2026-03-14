from __future__ import annotations

import re
from typing import Any

# Common separators and stop words used to keep phrase extraction bounded.
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
    "agent",
    "broker",
    "company",
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
    "mumbai",
    "pune",
    "hyderabad",
    "bengaluru",
    "bangalore",
    "chennai",
    "kolkata",
    "kerala",
    "goa",
}

_PHONE_RE = re.compile(r"(?<!\d)(?:\+91[-\s]?)?([6-9]\d{9})(?!\d)")
_NUMBER_RE = re.compile(r"\b\d{1,3}(?:,\d{2,3})*(?:\.\d+)?\b")


def _to_int(number_text: str) -> int:
    """Convert numeric text with optional commas/decimals to int."""
    cleaned = number_text.replace(",", "")
    return int(float(cleaned))


def _extract_phones(text: str) -> list[str]:
    """Extract Indian phone numbers and normalize to 10 digits."""
    phones = _PHONE_RE.findall(text)
    # Preserve order while removing duplicates.
    seen: set[str] = set()
    result: list[str] = []
    for phone in phones:
        if phone not in seen:
            seen.add(phone)
            result.append(phone)
    return result


def _extract_amount_after_keywords(text: str, keywords: tuple[str, ...]) -> int | None:
    """Find amount appearing close to specific keywords like salary/fee."""
    keyword_part = "|".join(re.escape(word) for word in keywords)
    amount_pattern = re.compile(
        rf"(?:\b(?:{keyword_part})\b)\s*(?::|=|is)?\s*(?:rs\.?|inr|aed)?\s*({_NUMBER_RE.pattern})",
        re.IGNORECASE,
    )

    match = amount_pattern.search(text)
    if match:
        return _to_int(match.group(1))

    # Handle forms like: 8000 registration fee
    reverse_pattern = re.compile(
        rf"({_NUMBER_RE.pattern})\s*(?:rs\.?|inr|aed)?\s*(?:\b(?:{keyword_part})\b)",
        re.IGNORECASE,
    )
    reverse_match = reverse_pattern.search(text)
    if reverse_match:
        return _to_int(reverse_match.group(1))

    return None


def _clean_phrase(value: str) -> str:
    value = re.sub(r"\s+", " ", value).strip(" -,:.")
    return value


def _extract_agent(text: str) -> str | None:
    match = re.search(r"\b(?:agent|broker|contact)\s+([A-Za-z][A-Za-z.'-]*)", text, re.IGNORECASE)
    if not match:
        return None
    return _clean_phrase(match.group(1)).title()


def _extract_location(text: str) -> str | None:
    # Explicit patterns first.
    explicit = re.search(
        r"\b(?:in|at|location)\s+([A-Za-z][A-Za-z\s]{1,40}?)(?=\b(?:"
        + "|".join(_STOP_TOKENS)
        + r")\b|$)",
        text,
        re.IGNORECASE,
    )
    if explicit:
        return _clean_phrase(explicit.group(1)).title()

    # Fallback to a known-location lookup inside the sentence.
    lowered = text.lower()
    for loc in sorted(_COMMON_LOCATIONS, key=len, reverse=True):
        if re.search(rf"\b{re.escape(loc)}\b", lowered):
            return loc.title()

    return None


def _extract_role(text: str, location: str | None) -> str | None:
    # Pattern-based role extraction when role is explicitly tagged.
    tagged = re.search(
        r"\b(?:role|position|job|vacancy|opening)\s*(?::|as|for)?\s+([A-Za-z][A-Za-z\s]{1,50}?)(?=\b(?:"
        + "|".join(_STOP_TOKENS)
        + r")\b|$)",
        text,
        re.IGNORECASE,
    )
    if tagged:
        return _clean_phrase(tagged.group(1))

    # Heuristic: take initial words before location/salary/fee/call/etc.
    start = text
    if location:
        start = re.split(rf"\b{re.escape(location)}\b", start, flags=re.IGNORECASE, maxsplit=1)[0]

    start = re.split(
        r"\b(?:salary|fee|registration|call|contact|agent|broker|phone|company)\b",
        start,
        flags=re.IGNORECASE,
        maxsplit=1,
    )[0]

    role = _clean_phrase(start)
    if not role:
        return None

    # Avoid returning tiny/noisy fragments.
    words = role.split()
    if 1 <= len(words) <= 6:
        return role

    return None


def _extract_company(text: str) -> str | None:
    match = re.search(
        r"\b(?:company|at)\s+([A-Za-z][A-Za-z0-9&.,'\-\s]{1,60}?)(?=\b(?:"
        + "|".join(_STOP_TOKENS)
        + r")\b|$)",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None
    return _clean_phrase(match.group(1)).title()


def extract_entities(text: str) -> dict[str, Any]:
    """Extract structured entities from job-related message text.

    Returns keys for:
    - phones: list[str]
    - salary: int | None
    - fee: int | None
    - role: str | None
    - location: str | None
    - agent: str | None
    - company: str | None (included only if detected)
    """
    phones = _extract_phones(text)
    salary = _extract_amount_after_keywords(text, ("salary", "sal", "pay", "wage", "income"))
    fee = _extract_amount_after_keywords(text, ("fee", "fees", "registration fee", "service charge", "processing"))
    agent = _extract_agent(text)
    location = _extract_location(text)
    role = _extract_role(text, location)
    company = _extract_company(text)

    result: dict[str, Any] = {
        "phones": phones,
        "salary": salary,
        "fee": fee,
        "role": role,
        "location": location,
        "agent": agent,
    }
    if company:
        result["company"] = company

    return result
