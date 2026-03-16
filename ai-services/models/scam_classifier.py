"""
models/scam_classifier.py
--------------------------
The LLM-powered scam classifier — the core AI brain of ScamShield.

Replaces the rule-based _placeholder_classify() in main_service.py
once Groq API key is configured.

Uses: Groq (LLaMA 3.3-70B) — free, 14,400 req/day, sub-second latency
Fallback: Google Gemini — free, 1500 req/day

To activate: set GROQ_API_KEY in your .env file.
Then in main_service.py, replace the _placeholder_classify call with:
    from models.scam_classifier import classify

Why LLM over a fine-tuned model for the hackathon:
  - Zero training data needed upfront
  - Handles code-mixed Hindi/English natively
  - Prompt can be updated instantly (no retraining)
  - Groq is fast enough for real-time WhatsApp responses
"""

import os
import json
import logging
from typing import Optional

from dotenv import load_dotenv
from utils.safe_extract import first_or_none

load_dotenv()
logger = logging.getLogger(__name__)

# ── Model config ──────────────────────────────────────────────────────────────
GROQ_MODEL = "llama-3.3-70b-versatile"    # Best free model on Groq
GEMINI_MODEL = "gemini-1.5-flash"          # Fallback

# ── Classifier prompt ──────────────────────────────────────────────────────────
# This is the most important string in the entire codebase.
# The quality of this prompt determines the quality of every verdict.

SYSTEM_PROMPT = """You are ScamShield — an AI protecting Indian migrant workers from job fraud.

Your task: analyse a job message and return a JSON risk assessment.

SCAM SIGNALS (increase risk score):
- Any upfront fee: registration, medical, visa, processing, security deposit
- Urgency language: "aaj raat tak", "limited seats", "apply today", "jaldi karo"
- Salary unrealistically high for the stated role (Security Guard at Rs.80,000+)
- Gulf/overseas jobs with no eMigrate or RAPS registration mention
- No verifiable company name, address, or official website
- Only a phone number or UPI ID as contact
- Spelling errors in company names (typosquatting)
- Promises of free accommodation, visa, food — all included
- Requests to keep the offer secret or act before telling family

SAFE SIGNALS (decrease risk score):
- Company registered on MCA / eMigrate
- Salary realistic for the role and location
- Official website or eMigrate registration number mentioned
- "No fee" explicitly stated
- Formal language, proper contact details, company address

OUTPUT: Return ONLY valid JSON. No explanation, no markdown, no preamble.
Schema:
{
  "risk_score": <integer 0-100>,
  "is_scam": <true if risk_score >= 65>,
  "reasons": [<up to 3 specific reasons as strings>],
  "hindi_verdict": "<1 sentence in simple Hindi for a semi-literate worker>",
  "english_summary": "<1 sentence technical summary>",
  "classifier_type": "llm_groq"
}

Hindi verdict tone guide:
  risk 0-34  → reassuring but cautious
  risk 35-64 → warning, do not pay yet
  risk 65-84 → strong warning, likely fraud
  risk 85+   → definitive fraud alert"""


# ── Main classify function ────────────────────────────────────────────────────

def classify(
    text: str,
    entities: Optional[dict] = None,
    context: Optional[str] = None,
) -> dict:
    """
    Classify a text message for job fraud risk using an LLM.

    Parameters
    ----------
    text      : str  — the message text to classify
    entities  : dict — pre-extracted entities from entity_extractor
                       (injected into prompt for better accuracy)
    context   : str  — optional extra context (e.g. "This is an image OCR output")

    Returns
    -------
    dict with keys:
        risk_score      int
        is_scam         bool
        reasons         list[str]
        hindi_verdict   str
        english_summary str
        classifier_type str   — "llm_groq" | "llm_gemini" | "rule_based"
        error           str   — only if classification failed
    """
    # Build the user message with entity context if available
    user_message = _build_user_message(text, entities, context)

    # Try Groq first
    groq_key = os.getenv("GROQ_API_KEY")
    if groq_key:
        result = _classify_groq(user_message, groq_key)
        if result.get("success"):
            logger.info(f"classifier: Groq → risk={result['risk_score']} scam={result['is_scam']}")
            return result

    # Fallback to Gemini
    gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY")
    if gemini_key:
        result = _classify_gemini(user_message, gemini_key)
        if result.get("success"):
            logger.info(f"classifier: Gemini → risk={result['risk_score']} scam={result['is_scam']}")
            return result

    # Final fallback: rule-based (from main_service.py)
    logger.warning("classifier: both LLMs unavailable — falling back to rule-based")
    return _rule_based_fallback(text, entities or {})


# ── LLM backends ──────────────────────────────────────────────────────────────

def _classify_groq(user_message: str, api_key: str) -> dict:
    """Call Groq API with LLaMA 3.3."""
    try:
        from groq import Groq
        client = Groq(api_key=api_key)

        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            temperature=0.1,     # Low temperature = more consistent, deterministic outputs
            max_tokens=400,
            response_format={"type": "json_object"},  # Force JSON output
        )

        first_choice = first_or_none(response.choices) if hasattr(response, "choices") else None
        raw = getattr(getattr(first_choice, "message", None), "content", "{}")
        return _parse_llm_response(raw, "llm_groq")

    except ImportError:
        logger.warning("classifier: groq package not installed — pip install groq")
        return {"success": False}
    except Exception as e:
        logger.error(f"classifier: Groq API error — {e}")
        return {"success": False}


def _classify_gemini(user_message: str, api_key: str) -> dict:
    """Call Google Gemini API as fallback."""
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)

        model = genai.GenerativeModel(
            GEMINI_MODEL,
            system_instruction=SYSTEM_PROMPT,
        )
        response = model.generate_content(
            user_message,
            generation_config={"temperature": 0.1, "max_output_tokens": 400},
        )
        raw = response.text
        return _parse_llm_response(raw, "llm_gemini")

    except ImportError:
        logger.warning("classifier: google-generativeai not installed")
        return {"success": False}
    except Exception as e:
        logger.error(f"classifier: Gemini API error — {e}")
        return {"success": False}


def _parse_llm_response(raw: str, classifier_type: str) -> dict:
    """
    Parse and validate LLM JSON output.
    Handles common LLM quirks: markdown fences, trailing commas, etc.
    """
    try:
        # Strip markdown fences if present (some models add these despite JSON mode)
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("```")[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
        cleaned = cleaned.strip()

        data = json.loads(cleaned)

        # Validate required fields
        risk_score = int(data.get("risk_score", 50))
        risk_score = max(0, min(100, risk_score))  # clamp to 0–100

        return {
            "success": True,
            "risk_score": risk_score,
            "is_scam": risk_score >= 65,
            "reasons": data.get("reasons", [])[:3],
            "hindi_verdict": data.get("hindi_verdict", "जांच जारी है।"),
            "english_summary": data.get("english_summary", ""),
            "classifier_type": classifier_type,
        }

    except (json.JSONDecodeError, KeyError, ValueError) as e:
        logger.error(f"classifier: could not parse LLM response — {e}\nRaw: {raw[:200]}")
        return {"success": False}


def _build_user_message(
    text: str,
    entities: Optional[dict],
    context: Optional[str],
) -> str:
    """
    Build the user message for the LLM prompt.
    Injecting pre-extracted entities makes the classifier more accurate
    and reduces hallucinations (the LLM doesn't have to re-extract them).
    """
    parts = []

    if context:
        parts.append(f"[Context: {context}]")

    parts.append(f"Message to analyse:\n{text}")

    if entities:
        # Summarize entities compactly
        entity_summary = []
        if entities.get("phones"):
            entity_summary.append(f"Phones found: {', '.join(entities['phones'])}")
        if entities.get("fees"):
            amounts = [str(f["normalized"]) for f in entities["fees"]]
            entity_summary.append(f"Fee amounts: ₹{', ₹'.join(amounts)}")
        if entities.get("salaries"):
            amounts = [str(s["normalized"]) for s in entities["salaries"]]
            entity_summary.append(f"Salary claims: ₹{', ₹'.join(amounts)}")
        if entities.get("locations"):
            entity_summary.append(f"Locations: {', '.join(entities['locations'])}")
        if entities.get("urgency_flags"):
            entity_summary.append(f"Urgency phrases: {', '.join(entities['urgency_flags'])}")
        if entities.get("company_names"):
            entity_summary.append(f"Company mentioned: {', '.join(entities['company_names'])}")

        if entity_summary:
            parts.append("\nPre-extracted entities:\n" + "\n".join(f"- {e}" for e in entity_summary))

    return "\n".join(parts)


# ── Rule-based fallback ───────────────────────────────────────────────────────

def _rule_based_fallback(text: str, entities: dict) -> dict:
    """
    Simple rule-based classifier. Used when both LLMs are unavailable.
    Same logic as main_service._placeholder_classify but lives here
    so there's one canonical fallback.
    """
    score = 0
    reasons = []

    if entities.get("has_fee"):
        score += 40
        amounts = [str(f["normalized"]) for f in entities.get("fees", [])]
        reasons.append(f"Upfront fee requested: ₹{', ₹'.join(amounts)}" if amounts else "Fee requested")

    if entities.get("has_urgency"):
        score += 25
        flags = entities.get("urgency_flags", [])
        first_flag = first_or_none(flags)
        reasons.append(f"Urgency language: '{first_flag}'" if first_flag else "Urgency language detected")

    gulf = [l for l in entities.get("locations", [])
            if l in {"dubai", "uae", "qatar", "saudi", "saudi arabia", "kuwait", "bahrain", "oman"}]
    if gulf and not entities.get("company_names"):
        score += 15
        first_gulf = first_or_none(gulf)
        reasons.append(
            f"Overseas job ({first_gulf}) with no verifiable company"
            if first_gulf
            else "Overseas job with no verifiable company"
        )

    score = min(score, 100)

    if score >= 85:
        hindi = "❌ यह फर्जी नौकरी है! पैसे मत दो।"
    elif score >= 65:
        hindi = "🚨 खतरा! नौकरी नकली हो सकती है। पैसे मत भेजें।"
    elif score >= 35:
        hindi = "⚠️ सावधान! संदिग्ध संदेश। पहले जांच करें।"
    else:
        hindi = "यह नौकरी सुरक्षित लगती है। फिर भी सावधान रहें।"

    return {
        "risk_score": score,
        "is_scam": score >= 65,
        "reasons": reasons[:3] or ["No specific red flags detected"],
        "hindi_verdict": hindi,
        "english_summary": f"Rule-based score: {score}/100",
        "classifier_type": "rule_based",
    }


# ── Quick manual test ──────────────────────────────────────────────────────────
# Run: python models/scam_classifier.py
# Set GROQ_API_KEY in .env to test the real LLM path.

if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from entity_extractor import extract_entities

    test_cases = [
        {
            "label": "Classic Gulf scam",
            "text": "URGENT VACANCY — Security Guard Dubai. Salary Rs.80,000/month. Registration fee Rs.8,000. Call 9876543210. Limited seats — apply today!",
        },
        {
            "label": "Legitimate TCS job",
            "text": "Tata Consultancy Services is hiring software engineers in Bengaluru. Package: 6 LPA. Apply at careers.tcs.com. No registration fee. eMigrate registered.",
        },
        {
            "label": "Hindi scam",
            "text": "Bhai Dubai mein security guard chahiye. Salary 75000 milega. Bas 7500 registration ke liye bhejo. Jaldi karo sirf 3 seats bachi hain. Call: 9988776655",
        },
    ]

    for tc in test_cases:
        print(f"\n{'='*60}")
        print(f"Test: {tc['label']}")
        entities = extract_entities(tc["text"])
        result = classify(tc["text"], entities=entities)
        print(f"Risk: {result['risk_score']}/100 | Scam: {result['is_scam']} | Type: {result['classifier_type']}")
        print(f"Reasons: {result['reasons']}")
        print(f"Hindi: {result['hindi_verdict']}")
