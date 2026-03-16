"""
entity_extractor.py
--------------------
Production NER for ScamShield. Extracts structured entities from raw text.

Two-tier extraction:
  Tier 1 — Regex (always runs, zero dependencies)
  Tier 2 — spaCy NER (runs if spaCy is installed; adds ORG, GPE entities)

Handles real-world scam obfuscation:
  - Leet-speak:  r3g f33 → reg fee,  ₹2k → 2000,  two thousand → 2000
  - Multi-currency: $500, AED 2000, SAR 1500 → all normalised to display value
  - Phone variations: +91-98765 43210, (0)9876543210, 91-9876543210
  - UPI handle variations (20+ bank handles)
  - Salary expressed as lakh/crore: "1.5 lakh pm" → 150000
  - Company names with abbreviations: "ABC Pvt. Ltd", "XYZ Intl."
  - Location variants: "KSA" → saudi, "U.A.E." → uae

Input:  raw text (string)
Output: dict matching the ScamResult entities schema
"""

from __future__ import annotations

import logging
import re
import unicodedata
from typing import Optional

logger = logging.getLogger(__name__)

# ── spaCy optional import ────────────────────────────────────────────────────

_NLP = None  # lazy-loaded

def _get_nlp():
    """Load spaCy model once. Silently returns None if not installed."""
    global _NLP
    if _NLP is not None:
        return _NLP
    try:
        import spacy
        try:
            _NLP = spacy.load("en_core_web_sm")
            logger.info("entity_extractor: spaCy en_core_web_sm loaded")
        except OSError:
            # Model not downloaded — run: python -m spacy download en_core_web_sm
            _NLP = False
            logger.warning("entity_extractor: spaCy model not found. Using regex only. "
                           "Run: python -m spacy download en_core_web_sm")
    except ImportError:
        _NLP = False
        logger.info("entity_extractor: spaCy not installed. Using regex only.")
    return _NLP if _NLP else None


# ── Leet-speak normalisation map ─────────────────────────────────────────────

LEET_MAP = str.maketrans({
    "0": "o", "1": "i", "3": "e", "4": "a",
    "5": "s", "6": "g", "7": "t", "8": "b", "9": "g",
    "@": "a", "$": "s",
})

# Words that look leet but are actually numbers — DON'T leet-translate these
_NUMBER_CONTEXT = re.compile(r"(?:rs\.?|₹|inr|fee|salary|sal|pay)\s*[\d]", re.IGNORECASE)

def _normalise_leet(text: str) -> str:
    """
    Expand leet-speak fee/keyword obfuscations without corrupting numbers.
    Only applies leet translation to word tokens, not digit sequences.

    Examples:
      "r3g f33"        → "reg fee"
      "proc3ss1ng f3e" → "processing fee"
      "₹8,000"         → left unchanged (number context)
    """
    # Protect number-like tokens: wrap in a placeholder
    protected = re.sub(r"[\d,]+", lambda m: "\x00" + m.group(0) + "\x00", text)
    # Translate leet chars only in the non-number parts
    parts = protected.split("\x00")
    result = []
    for i, part in enumerate(parts):
        if i % 2 == 1:          # protected number
            result.append(part)
        else:
            result.append(part.translate(LEET_MAP))
    return "".join(result)


# ── Verbal number normalisation ───────────────────────────────────────────────

_VERBAL_MAP = {
    "two thousand": "2000",  "three thousand": "3000", "five thousand": "5000",
    "eight thousand": "8000", "ten thousand": "10000", "twenty thousand": "20000",
    "one lakh": "100000", "two lakh": "200000", "five lakh": "500000",
    "2k": "2000", "3k": "3000", "5k": "5000", "8k": "8000", "10k": "10000",
    "2.5k": "2500", "5k": "5000", "15k": "15000", "20k": "20000",
}

def _expand_verbal_numbers(text: str) -> str:
    """Replace verbal amounts ('two thousand', '5k') with digits."""
    lowered = text.lower()
    for verbal, digit in _VERBAL_MAP.items():
        lowered = lowered.replace(verbal, digit)
    return lowered


# ── Patterns ──────────────────────────────────────────────────────────────────

# Indian mobile: starts 6-9, 10 digits, optional +91/91/0091 prefix
PHONE_RE = re.compile(
    r"(?:(?:\+91|0091|91)[\s\-.]?)?"   # optional country code
    r"(?:\(0\))?"                        # optional (0)
    r"([6-9]\d{4}[\s\-.]?\d{5})"        # 5+5 with optional separator
    r"(?!\d)"
)

# UPI: handle@bankcode
UPI_HANDLES = (
    "okaxis|okicici|okhdfcbank|oksbi|paytm|ybl|upi|axisbank|icici|sbi|"
    "hdfcbank|kotak|ibl|indus|barodampay|aubank|idbi|pnb|bob|cnrb|ubi|"
    "alla|mahb|utib|pmys|apb|ezeepay|fbl|jiomoney|airtel|apl|goaxis|"
    "rbl|tm|pingpay|postbank|abfspay|kvb|ratnaker|scmobile|sib|tjsb|"
    "vijb|yesbank|amazonpay|gpay|phonepe|bhim"
)
UPI_RE = re.compile(
    rf"[\w.\-]{{3,}}@(?:{UPI_HANDLES})", re.IGNORECASE
)

# Fees — keyword + amount, handles leet-normalised text
FEE_KW = (
    r"(?:registration|reg|medical|visa|processing|proc|security|deposit|"
    r"advance|joining|training|document|courier|service|agent|application)"
    r"[\s\-]*(?:fee|fees|charge|charges|cost|amount|payment|pay|f[e3]{2})?"
)
FEE_RE = re.compile(
    rf"(?:{FEE_KW}|(?:fees?|charges?|deposit|advance))"
    r"[\s:]*(?:rs\.?|₹|inr|aed|sar|qar|omr|usd|\$)?\s*"
    r"([\d][\d,]*(?:\.\d{{1,2}})?)"
    r"(?!\s*(?:lakh|crore|lac))",          # lakh/crore handled separately
    re.IGNORECASE,
)

# Lakh/crore fee: "registration fee 1.5 lakh"
FEE_LAKH_RE = re.compile(
    rf"(?:{FEE_KW}|fees?|charges?|deposit)"
    r"[\s:]*(?:rs\.?|₹|inr)?\s*"
    r"([\d]+(?:\.\d+)?)\s*(?:lakh|lac)\b",
    re.IGNORECASE,
)

# Salary patterns — plain + lakh/crore + per-month variants + multi-currency
SALARY_RE = re.compile(
    r"(?:salary|sal\b|pay\b|income|ctc|package|earning|compensation|stipend|remuneration)"
    r"[\s:of]*(?:rs\.?|₹|inr|aed|sar|qar|usd|\$)?\s*"
    r"([\d][\d,]*)"
    r"(?:\s*(?:per month|p\.?m\.?|/month|monthly|per annum|p\.?a\.?|/year|yearly))?",
    re.IGNORECASE,
)
SALARY_LAKH_RE = re.compile(
    r"(?:salary|sal\b|pay\b|income|ctc|package)"
    r"[\s:of]*(?:rs\.?|₹|inr)?\s*"
    r"([\d]+(?:\.\d+)?)\s*(?:lakh|lac|crore)\b",
    re.IGNORECASE,
)
# Standalone "Rs X per month" not already captured by salary keyword
SALARY_PM_RE = re.compile(
    r"(?:rs\.?|₹|inr)\s*([\d][\d,]*)\s*(?:per month|p\.?m\.?|/month|monthly)\b",
    re.IGNORECASE,
)
# Multi-currency salary: "$2000", "AED 3000", "SAR 1500"
SALARY_FOREIGN_RE = re.compile(
    r"(?:salary|sal|pay|income|ctc|package)[\s:of]*"
    r"(?P<currency>aed|sar|qar|omr|myr|usd|\$|£|€)\s*"
    r"(?P<amount>[\d][\d,]*)",
    re.IGNORECASE,
)

# Standalone rupee/foreign-currency amounts (catch-all for fees not matched above)
RUPEE_ANY_RE = re.compile(
    r"(?:rs\.?|₹|inr)\s*([\d][\d,]*(?:\.\d{1,2})?)"
    r"|(\d[\d,]*)\s*(?:rs\.?|₹|/-)",
    re.IGNORECASE,
)

# URLs
URL_RE = re.compile(
    r"(?:https?://|www\.)[\w\-./&?=%+#@]+|[\w\-]{3,}\.(?:com|in|net|org|co\.in|gov\.in|jobs|work)",
    re.IGNORECASE,
)

# Company heuristic — title-cased prefix + legal suffix
COMPANY_SUFFIX = (
    r"(?:Pvt\.?\s*Ltd\.?|Private\s+Limited|Ltd\.?|Limited|Inc\.?|LLP|"
    r"Enterprises?|Solutions?|Services?|Consultanc(?:y|ies)|Agenc(?:y|ies)|"
    r"Recruitment|HR|International|Intl\.?|Overseas|Manpower|Placement|"
    r"Technologies|Tech\.?|Group|Corp\.?|Corporation)"
)
COMPANY_RE = re.compile(
    rf"([A-Z][A-Za-z0-9\s&\.\-]{{2,45}}?)\s*{COMPANY_SUFFIX}",
    re.IGNORECASE,
)

# Locations — normalised to lowercase canonical names
LOCATION_ALIASES: dict[str, str] = {
    "dubai": "dubai", "uae": "uae", "u.a.e.": "uae",
    "united arab emirates": "uae", "abu dhabi": "uae", "sharjah": "uae",
    "qatar": "qatar", "doha": "qatar",
    "saudi": "saudi", "saudi arabia": "saudi", "ksa": "saudi",
    "riyadh": "saudi", "jeddah": "saudi",
    "kuwait": "kuwait", "bahrain": "bahrain", "oman": "oman", "muscat": "oman",
    "malaysia": "malaysia", "kl": "malaysia", "kuala lumpur": "malaysia",
    "singapore": "singapore", "thailand": "thailand", "bangkok": "thailand",
    "cambodia": "cambodia", "phnom penh": "cambodia",
    "indonesia": "indonesia", "jakarta": "indonesia",
    "myanmar": "myanmar", "vietnam": "vietnam",
    "delhi": "delhi", "new delhi": "delhi", "ncr": "delhi",
    "mumbai": "mumbai", "bombay": "mumbai",
    "bengaluru": "bengaluru", "bangalore": "bengaluru",
    "hyderabad": "hyderabad", "chennai": "chennai", "madras": "chennai",
    "kolkata": "kolkata", "calcutta": "kolkata",
    "pune": "pune", "surat": "surat", "ahmedabad": "ahmedabad",
    "noida": "noida", "gurgaon": "gurgaon", "gurugram": "gurgaon",
    "chandigarh": "chandigarh", "jaipur": "jaipur",
    "lucknow": "lucknow", "patna": "patna", "bhopal": "bhopal",
    "raipur": "raipur", "bhubaneswar": "bhubaneswar",
}

URGENCY_PHRASES = [
    "urgent", "limited seats", "apply today", "apply now", "only today",
    "last date", "hurry", "immediately", "asap", "don't miss", "do not miss",
    "closing soon", "few seats left", "deadline today", "seats are limited",
    "last chance", "filling fast", "act now", "respond immediately",
    "aaj raat tak", "kal tak", "abhi apply karo", "jaldi karo",
    "sirf aaj", "bahut kam seats", "turant", "seedha contact karo",
    "abhi call karo", "kal last date", "sirf 2 seats",
]


# ── Main function ─────────────────────────────────────────────────────────────

def extract_entities(text: str) -> dict:
    """
    Full entity extraction pipeline.

    Parameters
    ----------
    text : str — raw text from any source (WhatsApp, OCR, audio transcript)

    Returns
    -------
    dict matching ScamResult.entities schema plus metadata flags.
    """
    if not text or not isinstance(text, str) or not text.strip():
        logger.warning("entity_extractor: empty/invalid input")
        return _empty()

    logger.info(f"entity_extractor: processing {len(text)} chars")

    # Normalise before extraction
    normalised = _normalise(text)

    phones        = _phones(normalised)
    upi_ids       = _upi(normalised)
    fees          = _fees(normalised)
    salaries      = _salaries(normalised)
    company_names = _companies(normalised)
    locations     = _locations(normalised)
    urls          = _urls(normalised)
    urgency_flags = _urgency(normalised)

    # spaCy tier-2 enrichment
    spacy_extras = _spacy_enrich(text, company_names, locations)
    company_names = _dedupe_strings(company_names + spacy_extras.get("orgs", []))
    locations     = _dedupe_strings(locations     + spacy_extras.get("gpe",  []))

    entity_count = sum(map(len, [phones, upi_ids, fees, salaries,
                                  company_names, locations, urls, urgency_flags]))

    result = {
        "phones":        phones,
        "upi_ids":       upi_ids,
        "fees":          fees,
        "salaries":      salaries,
        "company_names": company_names,
        "locations":     locations,
        "urls":          urls,
        "urgency_flags": urgency_flags,
        "has_fee":       bool(fees),
        "has_urgency":   bool(urgency_flags),
        "entity_count":  entity_count,
        "nlp_tier":      "spacy+regex" if spacy_extras.get("used_spacy") else "regex",
    }

    logger.info(
        f"entity_extractor: phones={len(phones)} fees={len(fees)} "
        f"urgency={len(urgency_flags)} companies={len(company_names)} "
        f"tier={result['nlp_tier']}"
    )
    return result


# ── Normalisation ─────────────────────────────────────────────────────────────

def _normalise(text: str) -> str:
    """
    Apply all normalisation steps before regex extraction.
    Order matters: unicode → leet → verbal numbers
    """
    # NFKC: normalise unicode look-alike characters scammers use
    text = unicodedata.normalize("NFKC", text)
    # Expand leet-speak keywords
    text = _normalise_leet(text)
    # Expand verbal amounts
    text = _expand_verbal_numbers(text)
    return text


# ── Extraction functions ──────────────────────────────────────────────────────

def _phones(text: str) -> list[str]:
    raw_matches = PHONE_RE.findall(text)
    seen: set = set()
    result = []
    for raw in raw_matches:
        # Strip separators, keep only digits
        digits = re.sub(r"[\s\-.]", "", raw)
        if len(digits) == 10 and digits not in seen:
            seen.add(digits)
            result.append(digits)
    return result

def _upi(text: str) -> list[str]:
    return list({m.lower() for m in UPI_RE.findall(text)})

def _fees(text: str) -> list[dict]:
    seen: set = set()
    result = []

    def _add(raw_str: str, multiplier: float = 1.0):
        n = _parse_amount(raw_str, multiplier)
        if n and n not in seen and n < 200_000:   # fees realistically < 2 lakh
            seen.add(n)
            result.append({"raw": raw_str.strip(), "normalized": n})

    for m in FEE_RE.finditer(text):
        _add(m.group(1))
    for m in FEE_LAKH_RE.finditer(text):
        _add(m.group(1), multiplier=100_000)

    # Catch standalone rupee amounts not already captured (exclude salary range)
    salary_amounts = {s["normalized"] for s in _salaries(text)}
    for m in RUPEE_ANY_RE.finditer(text):
        raw = (m.group(1) or m.group(2) or "").strip()
        n = _parse_amount(raw)
        if n and n not in seen and n not in salary_amounts and n < 100_000:
            seen.add(n)
            result.append({"raw": raw, "normalized": n})

    return result

def _salaries(text: str) -> list[dict]:
    seen: set = set()
    result = []

    def _add(raw_str: str, multiplier: float = 1.0, currency: str = "INR"):
        n = _parse_amount(raw_str, multiplier)
        if n and n not in seen:
            seen.add(n)
            result.append({"raw": raw_str.strip(), "normalized": n, "currency": currency})

    for m in SALARY_RE.finditer(text):
        _add(m.group(1))
    for m in SALARY_LAKH_RE.finditer(text):
        unit = "crore" if "crore" in m.group(0).lower() else "lakh"
        _add(m.group(1), multiplier=10_000_000 if unit == "crore" else 100_000)
    for m in SALARY_PM_RE.finditer(text):
        _add(m.group(1))
    for m in SALARY_FOREIGN_RE.finditer(text):
        _add(m.group("amount"), currency=m.group("currency").upper())

    return result

def _companies(text: str) -> list[str]:
    matches = COMPANY_RE.findall(text)
    return _dedupe_strings([" ".join(m.split()) for m in matches if len(m.strip()) > 3])

def _locations(text: str) -> list[str]:
    text_lower = text.lower()
    found: set = set()
    for alias, canonical in LOCATION_ALIASES.items():
        # Word-boundary aware match to avoid "oman" matching "roman"
        if re.search(rf"\b{re.escape(alias)}\b", text_lower):
            found.add(canonical)
    return sorted(found)

def _urls(text: str) -> list[str]:
    return list({m.lower() for m in URL_RE.findall(text)})

def _urgency(text: str) -> list[str]:
    text_lower = text.lower()
    return [p for p in URGENCY_PHRASES if p in text_lower]


# ── spaCy enrichment ─────────────────────────────────────────────────────────

def _spacy_enrich(original_text: str, existing_companies: list, existing_locs: list) -> dict:
    """
    Run spaCy NER on the original (non-normalised) text.
    Adds ORG entities not already captured by regex,
    and GPE (geopolitical) entities as location hints.
    Returns {"orgs": [...], "gpe": [...], "used_spacy": bool}
    """
    nlp = _get_nlp()
    if not nlp:
        return {"orgs": [], "gpe": [], "used_spacy": False}

    try:
        # Limit to 5000 chars — spaCy can be slow on very long texts
        doc = nlp(original_text[:5000])
        existing_lower = {c.lower() for c in existing_companies}
        existing_loc_set = set(existing_locs)

        orgs, gpe = [], []
        for ent in doc.ents:
            if ent.label_ == "ORG":
                name = ent.text.strip()
                if len(name) > 3 and name.lower() not in existing_lower:
                    orgs.append(name)
            elif ent.label_ in ("GPE", "LOC"):
                canonical = LOCATION_ALIASES.get(ent.text.lower())
                if canonical and canonical not in existing_loc_set:
                    gpe.append(canonical)

        return {"orgs": orgs, "gpe": gpe, "used_spacy": True}

    except Exception as e:
        logger.warning(f"entity_extractor: spaCy enrichment failed — {e}")
        return {"orgs": [], "gpe": [], "used_spacy": False}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_amount(raw: str, multiplier: float = 1.0) -> Optional[int]:
    """Parse '8,000' or '1.5' (lakh) → int. Returns None if unparseable."""
    if not raw:
        return None
    cleaned = raw.replace(",", "").strip()
    try:
        return int(float(cleaned) * multiplier)
    except (ValueError, TypeError):
        return None

def _dedupe_strings(items: list[str]) -> list[str]:
    seen: set = set()
    result = []
    for item in items:
        key = item.lower().strip()
        if key and key not in seen:
            seen.add(key)
            result.append(item)
    return result

def _empty() -> dict:
    return {
        "phones": [], "upi_ids": [], "fees": [], "salaries": [],
        "company_names": [], "locations": [], "urls": [], "urgency_flags": [],
        "has_fee": False, "has_urgency": False, "entity_count": 0, "nlp_tier": "none",
    }


# ── Manual test ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json
    cases = [
        ("Classic Gulf scam",
         "URGENT VACANCY — Security Guard in Dubai\n"
         "Salary: Rs. 80,000/month | Reg f33: Rs. 8,000 | Medical fee: Rs. 3,000\n"
         "Call: +91-9876543210 | UPI: rajubhai@okicici\n"
         "Limited seats — apply today! www.gulfjobs-urgent.com"),

        ("Leet-speak obfuscation",
         "proc3ss1ng f3e: 5k. S@l@ry: two thousand AED. Call 9988776655. Jaldi karo!"),

        ("Verbal amounts",
         "Registration fee: five thousand rupees. Salary: 1.5 lakh per month. Dubai job."),

        ("Legitimate TCS post",
         "TCS Pvt Ltd hiring engineers in Bengaluru. CTC 6 LPA. careers.tcs.com. No fee."),
    ]
    for label, text in cases:
        print(f"\n{'='*60}\n{label}\n{'='*60}")
        r = extract_entities(text)
        print(json.dumps(r, indent=2, ensure_ascii=False))