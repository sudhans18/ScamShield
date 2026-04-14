from __future__ import annotations

import json
import re
from typing import Any

from app.services.cache.redis_client import get_cache, set_cache
from app.services.supabase_client import supabase


_GULF_COUNTRY_ALIASES = {
    "uae": "UAE",
    "united arab emirates": "UAE",
    "dubai": "UAE",
    "abu dhabi": "UAE",
    "sharjah": "UAE",
    "qatar": "Qatar",
    "doha": "Qatar",
    "saudi": "Saudi Arabia",
    "saudi arabia": "Saudi Arabia",
    "ksa": "Saudi Arabia",
    "riyadh": "Saudi Arabia",
    "jeddah": "Saudi Arabia",
    "oman": "Oman",
    "muscat": "Oman",
    "bahrain": "Bahrain",
    "kuwait": "Kuwait",
}


def _normalize(text: str | None) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()
    return re.sub(r"\s+", " ", cleaned)


def _levenshtein(a: str, b: str) -> int:
    if len(a) < len(b):
        return _levenshtein(b, a)
    if not b:
        return len(a)
    previous = list(range(len(b) + 1))
    for index_a, char_a in enumerate(a):
        current = [index_a + 1]
        for index_b, char_b in enumerate(b):
            current.append(min(previous[index_b + 1] + 1, current[index_b] + 1, previous[index_b] + (char_a != char_b)))
        previous = current
    return previous[-1]


def _safe_json_load(raw: str | None) -> dict[str, Any] | None:
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        return None
    return None


def _resolve_work_country(location: str | None) -> str | None:
    normalized = _normalize(location)
    if not normalized:
        return None
    for alias, country in _GULF_COUNTRY_ALIASES.items():
        if alias in normalized:
            return country
    if normalized in {"india", "bharat"}:
        return "India"
    return None


def _fetch_registry_rows() -> list[dict[str, Any]]:
    try:
        response = supabase.table("company_registry").select("*").limit(1000).execute()
        return response.data or []
    except Exception:
        return []


def _fetch_prefix_rows() -> list[dict[str, Any]]:
    try:
        response = supabase.table("phone_prefix_location").select("*").limit(1000).execute()
        return response.data or []
    except Exception:
        return []


def _pick_company(company_name: str, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    normalized = _normalize(company_name)
    if not normalized:
        return None

    for row in rows:
        if _normalize(row.get("name_normalized") or row.get("name")) == normalized:
            return row

    best_row: dict[str, Any] | None = None
    best_distance = 999
    for row in rows:
        target = _normalize(row.get("name_normalized") or row.get("name"))
        if not target:
            continue
        distance = _levenshtein(normalized, target)
        if distance < best_distance:
            best_row = row
            best_distance = distance

    if best_row is not None and best_distance <= 2:
        return best_row
    return None


def _typosquatting_target(company_name: str, rows: list[dict[str, Any]]) -> tuple[bool, str | None]:
    normalized = _normalize(company_name)
    if not normalized:
        return False, None

    best_name: str | None = None
    best_distance = 999
    for row in rows:
        target = _normalize(row.get("name_normalized") or row.get("name"))
        if not target:
            continue
        if target == normalized:
            continue
        distance = _levenshtein(normalized, target)
        if 0 < distance < best_distance:
            best_distance = distance
            best_name = row.get("name")

    if best_name and 1 <= best_distance <= 3:
        return True, str(best_name)
    return False, None


def _role_supported(role: str | None, company_row: dict[str, Any]) -> bool | None:
    if not role:
        return None
    allowed = company_row.get("allowed_job_categories") or []
    if not isinstance(allowed, list) or not allowed:
        return False
    role_n = _normalize(role)
    for item in allowed:
        item_n = _normalize(str(item))
        if not item_n:
            continue
        if role_n in item_n or item_n in role_n:
            return True
    return False


def _lookup_phone_country(phone: str | None, prefix_rows: list[dict[str, Any]]) -> str | None:
    if not phone:
        return None
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 10 and digits.startswith(("6", "7", "8", "9")):
        digits = "91" + digits

    best_match: dict[str, Any] | None = None
    best_len = -1
    for row in prefix_rows:
        prefix = str(row.get("prefix") or "")
        prefix_digits = re.sub(r"\D", "", prefix)
        if not prefix_digits:
            continue
        if digits.startswith(prefix_digits) and len(prefix_digits) > best_len:
            best_match = row
            best_len = len(prefix_digits)
    if best_match:
        return str(best_match.get("country") or "").strip() or None
    return None


def check_entity_consistency_against_db(entities: dict) -> dict:
    """
    Cross-reference extracted entities against mock registry tables.
    """
    cache_key = "consistency:db:" + json.dumps(entities or {}, sort_keys=True, default=str)
    try:
        cached = _safe_json_load(get_cache(cache_key))
    except Exception:
        cached = None
    if cached:
        return cached

    contradiction_details: list[str] = []
    db_contradictions = 0
    db_checks_run = 0
    company_found = False
    company_blacklisted = False
    typo_suspected = False
    typo_target: str | None = None

    company_name = str((entities or {}).get("company") or "").strip()
    role = str((entities or {}).get("role") or "").strip()
    location = str((entities or {}).get("location") or "").strip()
    phones = (entities or {}).get("phones") or []
    if not isinstance(phones, list):
        phones = [phones]
    phone = str(phones[0]).strip() if phones else ""

    company_rows = _fetch_registry_rows()
    prefix_rows = _fetch_prefix_rows()
    work_country = _resolve_work_country(location)

    picked_company = None
    if company_name:
        db_checks_run += 1
        picked_company = _pick_company(company_name, company_rows)
        if picked_company is None:
            db_contradictions += 1
            contradiction_details.append("Company not registered in known agency registry.")
        else:
            company_found = True

        db_checks_run += 1
        typo_suspected, typo_target = _typosquatting_target(company_name, company_rows)
        if typo_suspected:
            db_contradictions += 1
            contradiction_details.append(
                f"Company name looks like impersonation of '{typo_target}'."
            )

    if picked_company:
        db_checks_run += 1
        if bool(picked_company.get("is_blacklisted")):
            company_blacklisted = True
            db_contradictions += 2
            contradiction_details.append("Company is marked as blacklisted in registry.")

        if location:
            db_checks_run += 1
            city = _normalize(str(picked_company.get("registered_city") or ""))
            state = _normalize(str(picked_company.get("registered_state") or ""))
            loc = _normalize(location)
            if city and city not in loc and loc not in city and state and state not in loc:
                db_contradictions += 1
                contradiction_details.append(
                    f"Claimed location '{location}' does not match registered location."
                )

        if role:
            db_checks_run += 1
            role_ok = _role_supported(role, picked_company)
            if role_ok is False:
                db_contradictions += 1
                contradiction_details.append(
                    f"Role '{role}' not listed in company's allowed job categories."
                )

        if work_country and work_country != "India":
            db_checks_run += 1
            countries = picked_company.get("placement_countries") or []
            if not isinstance(countries, list):
                countries = []
            normalized_countries = {_normalize(str(item)) for item in countries}
            if _normalize(work_country) not in normalized_countries:
                db_contradictions += 1
                contradiction_details.append(
                    f"Company has no placement registration for {work_country}."
                )

    phone_country = _lookup_phone_country(phone, prefix_rows)
    if phone and work_country:
        db_checks_run += 1
        if phone_country and _normalize(phone_country) != _normalize(work_country):
            db_contradictions += 1
            contradiction_details.append(
                f"Phone country '{phone_country}' conflicts with claimed work location '{work_country}'."
            )

    result = {
        "db_contradictions": db_contradictions,
        "db_checks_run": db_checks_run,
        "contradiction_details": contradiction_details,
        "company_found_in_registry": company_found,
        "company_is_blacklisted": company_blacklisted,
        "typosquatting_suspected": typo_suspected,
        "typosquatting_target": typo_target,
        "work_country": work_country,
        "phone_country": phone_country,
    }
    try:
        set_cache(cache_key, json.dumps(result), ttl=3600)
    except Exception:
        pass
    return result
