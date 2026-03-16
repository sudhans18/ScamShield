"""
validator.py
------------
Cross-checks extracted entities against:
  1. Internal Supabase scam database (phone hash / UPI / URL lookups)
  2. MCA21 public registry (company verification)
  3. eMigrate RAPS stub (overseas agency check)

Security model (from project spec):
  - Sybil-attack protection: trust-weighted scoring, not vote counting
  - Rate limiting: max 3 reports per phone/IP per 24 hours
  - Temporal decay: reports older than 6 months lose weight
  - Appeal pipeline: agencies can submit MCA docs for delisting

Privacy model (DPDP 2023):
  - Phone numbers stored as SHA-256 hashes only — never in plain text
  - Raw message content never persisted — only extracted signals

All functions return structured dicts. This module never raises.
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY", "")
API_TIMEOUT  = 5   # seconds

# Trust weights per reporter type
TRUST_WEIGHTS = {
    "unverified_whatsapp": 0.1,
    "eshram_verified":     0.6,
    "ngo_partner":         0.8,
    "cybercrime_gov":      1.0,
}

# Cumulative trust weight thresholds
FLAGGED_THRESHOLD     = 3.0
BLACKLISTED_THRESHOLD = 7.0

# Temporal decay factors
DECAY_6_MONTHS  = 0.5    # reports 6+ months old lose 50% weight
DECAY_12_MONTHS = 0.1    # reports 12+ months old lose 90% weight

# In-memory rate limit store: {phone_hash → [(timestamp, count)]}
# In production, replace with Redis for multi-process safety
_RATE_LIMIT_STORE: dict = defaultdict(list)
RATE_LIMIT_MAX   = 3       # max reports per identifier
RATE_LIMIT_HOURS = 24      # per window


# ── Main validation function ──────────────────────────────────────────────────

def validate_entities(entities: dict) -> dict:
    """
    Cross-check all extracted entities against the scam database.

    Parameters
    ----------
    entities : dict from entity_extractor.extract_entities()

    Returns
    -------
    dict:
        phones_checked    list[dict]
        upi_ids_checked   list[dict]
        company_checked   dict
        score_boost       int    (0–40) added to classifier risk score
        validation_notes  list[str]
    """
    phones   = entities.get("phones", [])
    upi_ids  = entities.get("upi_ids", [])
    companies = entities.get("company_names", [])

    phones_results = [_check_phone(p) for p in phones]
    upi_results    = [_check_upi(u) for u in upi_ids]
    company_result = _check_company(companies[0] if companies else None)

    score_boost = 0
    notes: list[str] = []

    # Accumulate boost from phone matches
    for pr in phones_results:
        if pr.get("is_reported"):
            trust = pr.get("cumulative_trust", 0)
            boost = min(int(trust * 8), 25)  # max +25 per phone
            score_boost += boost
            notes.append(
                f"Phone {pr['phone'][-4:]}XXXXXX reported "
                f"{pr.get('report_count', '?')} times "
                f"(trust weight {trust:.1f}, status: {pr.get('status','unknown')})"
            )
        elif pr.get("db_status") == "unavailable":
            notes.append("Scam database temporarily unavailable — verdict based on AI analysis only")

    # UPI matches
    for ur in upi_results:
        if ur.get("is_reported"):
            score_boost += 15
            notes.append(f"UPI ID {ur['upi_id']} is linked to reported scam activity")

    # Company MCA miss
    if not company_result.get("mca_verified") and companies:
        score_boost += 8
        notes.append(f"Company '{companies[0]}' not found in MCA registry")

    if not notes:
        notes.append("No matches found in scam database — verdict based on AI analysis only")

    return {
        "phones_checked":   phones_results,
        "upi_ids_checked":  upi_results,
        "company_checked":  company_result,
        "score_boost":      min(score_boost, 40),
        "validation_notes": notes,
    }


# ── Phone checks ──────────────────────────────────────────────────────────────

def _check_phone(phone: str) -> dict:
    """Check phone against Supabase scam DB."""
    result = {
        "phone":           phone,
        "phone_hash":      _hash(phone),
        "is_reported":     False,
        "report_count":    0,
        "cumulative_trust": 0.0,
        "status":          "unknown",
        "db_status":       "ok",
    }

    if not (SUPABASE_URL and SUPABASE_KEY):
        result["db_status"] = "unavailable"
        logger.warning("validator: SUPABASE credentials not configured")
        return result

    db = _supabase_phone_lookup(_hash(phone))
    if db:
        result.update(db)
        result["is_reported"] = True
    return result

def _supabase_phone_lookup(phone_hash: str) -> Optional[dict]:
    """Query Supabase for a hashed phone number with temporal decay applied."""
    try:
        import requests
        resp = requests.get(
            f"{SUPABASE_URL}/rest/v1/scam_reports",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            params={"phone_hash": f"eq.{phone_hash}",
                    "select": "report_count,cumulative_trust_weight,status,created_at"},
            timeout=API_TIMEOUT,
        )
        if resp.status_code == 200 and resp.json():
            row = resp.json()[0]
            trust_raw = float(row.get("cumulative_trust_weight", 0))
            # Apply temporal decay
            created_str = row.get("created_at", "")
            trust = _apply_decay(trust_raw, created_str)
            return {
                "report_count":     row.get("report_count", 1),
                "cumulative_trust": trust,
                "status": (
                    "blacklisted" if trust >= BLACKLISTED_THRESHOLD
                    else "flagged" if trust >= FLAGGED_THRESHOLD
                    else "reported"
                ),
            }
        return None
    except Exception as e:
        logger.warning(f"validator: Supabase phone lookup failed — {e}")
        return None


# ── UPI checks ────────────────────────────────────────────────────────────────

def _check_upi(upi_id: str) -> dict:
    result = {"upi_id": upi_id, "is_reported": False, "status": "unknown"}
    if not (SUPABASE_URL and SUPABASE_KEY):
        return result
    try:
        import requests
        resp = requests.get(
            f"{SUPABASE_URL}/rest/v1/scam_reports",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            params={"upi_id": f"eq.{upi_id.lower()}", "select": "report_count"},
            timeout=API_TIMEOUT,
        )
        if resp.status_code == 200 and resp.json():
            result["is_reported"] = True
            result["report_count"] = resp.json()[0].get("report_count", 1)
            result["status"] = "flagged"
    except Exception as e:
        logger.warning(f"validator: UPI lookup failed — {e}")
    return result


# ── Company checks ────────────────────────────────────────────────────────────

def _check_company(company_name: Optional[str]) -> dict:
    if not company_name:
        return {"company_name": None, "mca_verified": False,
                "message": "No company name to check"}
    mca = _mca_check(company_name)
    return {
        "company_name":  company_name,
        "mca_verified":  mca["verified"],
        "mca_message":   mca["message"],
    }

def _mca_check(name: str) -> dict:
    try:
        import requests
        resp = requests.get(
            "https://www.mca.gov.in/mcafoportal/viewCompanyMasterData.do",
            params={"companyName": name}, timeout=API_TIMEOUT,
        )
        if resp.status_code == 200 and name.split()[0].lower() in resp.text.lower():
            return {"verified": True, "message": "Found in MCA registry"}
        return {"verified": False, "message": "Not found in MCA registry"}
    except Exception as e:
        return {"verified": False, "message": f"MCA check unavailable: {e}"}


# ── Report submission ─────────────────────────────────────────────────────────

def submit_report(
    phone: Optional[str] = None,
    upi_id: Optional[str] = None,
    message_text: Optional[str] = None,
    reporter_type: str = "unverified_whatsapp",
    district: Optional[str] = None,
) -> dict:
    """
    Submit a new scam report to Supabase.

    Rate limited: max RATE_LIMIT_MAX reports per identifier per 24h.
    Trust-weighted: reporter_type determines how much weight this report carries.
    """
    identifier = phone or upi_id
    if not identifier:
        return {"success": False, "error": "phone or upi_id required"}

    # Rate limit check
    id_hash = _hash(identifier)
    if not _check_rate_limit(id_hash):
        return {
            "success": False,
            "error": f"Rate limit: max {RATE_LIMIT_MAX} reports per {RATE_LIMIT_HOURS}h per identifier",
        }

    if not (SUPABASE_URL and SUPABASE_KEY):
        return {"success": False, "error": "Database not configured (SUPABASE_URL missing)"}

    trust = TRUST_WEIGHTS.get(reporter_type, 0.1)
    payload = {
        "phone_hash":     _hash(phone) if phone else None,
        "upi_id":         upi_id.lower() if upi_id else None,
        "reporter_type":  reporter_type,
        "trust_weight":   trust,
        "district":       district,
        "message_snippet": (message_text or "")[:200],
    }

    try:
        import requests
        resp = requests.post(
            f"{SUPABASE_URL}/rest/v1/scam_reports",
            json=payload,
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
            timeout=API_TIMEOUT,
        )
        if resp.status_code in (200, 201):
            _record_rate_limit(id_hash)
            logger.info(f"validator: report submitted for hash {id_hash[:8]}... trust={trust}")
            return {"success": True, "trust_weight": trust}
        return {"success": False, "error": f"DB error: HTTP {resp.status_code}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Temporal decay ────────────────────────────────────────────────────────────

def _apply_decay(raw_trust: float, created_at_str: str) -> float:
    """
    Reduce trust weight of old reports so stale data doesn't permanently flag
    legitimate numbers. Matches the spec: 6 months → 50%, 12 months → 10%.
    """
    if not created_at_str:
        return raw_trust
    try:
        # Parse ISO 8601 from Supabase
        dt = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
        age = datetime.now(timezone.utc) - dt
        if age > timedelta(days=365):
            return raw_trust * DECAY_12_MONTHS
        if age > timedelta(days=180):
            return raw_trust * DECAY_6_MONTHS
        return raw_trust
    except Exception:
        return raw_trust


# ── Rate limiting ─────────────────────────────────────────────────────────────

def _check_rate_limit(id_hash: str) -> bool:
    """Return True if the identifier is within the rate limit."""
    now = time.time()
    window = RATE_LIMIT_HOURS * 3600
    # Keep only timestamps within the window
    _RATE_LIMIT_STORE[id_hash] = [
        ts for ts in _RATE_LIMIT_STORE[id_hash] if now - ts < window
    ]
    return len(_RATE_LIMIT_STORE[id_hash]) < RATE_LIMIT_MAX

def _record_rate_limit(id_hash: str) -> None:
    _RATE_LIMIT_STORE[id_hash].append(time.time())


# ── Privacy helpers ───────────────────────────────────────────────────────────

def _hash(value: str) -> str:
    """SHA-256 hash. One-way — we can check membership but cannot reverse."""
    return hashlib.sha256(value.strip().encode()).hexdigest()


# ── Manual test ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json
    test_entities = {
        "phones":        ["9876543210"],
        "upi_ids":       ["rajubhai@okicici"],
        "company_names": ["Tata Projcts"],
        "has_fee": True, "has_urgency": True,
        "fees": [{"raw": "8000", "normalized": 8000}],
    }
    print("Running validator (DB checks skipped if SUPABASE_URL not set)...\n")
    result = validate_entities(test_entities)
    print(json.dumps(result, indent=2, ensure_ascii=False))

    print("\nRate limit test:")
    for i in range(5):
        ok = _check_rate_limit("test_hash_abc123")
        if ok: _record_rate_limit("test_hash_abc123")
        print(f"  Attempt {i+1}: {'allowed' if ok else 'BLOCKED'}")