from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

import requests
from anyio import to_thread

from app.core.config import settings

logger = logging.getLogger(__name__)

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = os.getenv("GROQ_INVESTIGATOR_MODEL", "llama-3.3-70b-versatile")

VERDICT_TO_SCORE = {
    "LEGITIMATE": 0.12,
    "SUSPICIOUS": 0.52,
    "HIGH_RISK": 0.92,
}

SYSTEM_PROMPT = """
You are a senior investigator at India's Labour Ministry with 10 years of experience detecting fraudulent recruitment.

You will receive a job message and evidence from four intelligence layers.
Do not score isolated flags. Build a coherent legitimacy model and identify logical contradictions.

STEP 1 - BUILD A LEGITIMATE MENTAL MODEL
What would a real registered recruiter write and provide?

STEP 2 - COMPARE
Compare the actual message to that legitimate mental model.

STEP 3 - FIND LOGICAL CONTRADICTIONS
Identify specific inconsistencies. Focus on contradictions, not checklist flags.

STEP 4 - STRAIN TEST LEGITIMACY
What would have to be true for this to be legitimate? Are those conditions plausible?

STEP 5 - ISSUE VERDICT
Possible verdicts:
LEGITIMATE, SUSPICIOUS, HIGH_RISK

CRITICAL KNOWLEDGE:
- Registered recruitment agencies should not ask workers for upfront recruitment fees.
- Gulf unskilled salaries are typically much lower than "too good to be true" offers.
- Real agencies provide verifiable details and consistent identity traces.
- Urgency + secrecy language is often coercive.

Return ONLY valid JSON with keys:
{
  "verdict": "LEGITIMATE" | "SUSPICIOUS" | "HIGH_RISK",
  "confidence": <0-100 integer>,
  "reasoning": "<2-3 concise sentences>",
  "key_contradiction": "<single strongest inconsistency or null>",
  "hindi_worker_message": "<one simple Hindi warning/reassurance sentence>"
}
"""


def _extract_json(content: str) -> dict[str, Any]:
    content = (content or "").strip()
    try:
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        return json.loads(fenced.group(1))

    inline = re.search(r"(\{.*\})", content, flags=re.DOTALL)
    if inline:
        return json.loads(inline.group(1))

    raise ValueError("LLM response did not contain valid JSON.")


def _coerce_verdict(value: Any) -> str:
    verdict = str(value or "").strip().upper()
    if verdict in VERDICT_TO_SCORE:
        return verdict
    if verdict in {"SCAM", "HIGH", "HIGH-RISK"}:
        return "HIGH_RISK"
    if verdict in {"MEDIUM", "UNCERTAIN"}:
        return "SUSPICIOUS"
    return "SUSPICIOUS"


def _coerce_confidence(value: Any) -> int:
    try:
        score = int(float(value))
    except (TypeError, ValueError):
        score = 60
    return max(0, min(100, score))


def _build_evidence_bundle(
    text: str,
    entities: dict,
    embedding_result: dict,
    consistency_result: dict,
    propagation_result: dict,
    media_context: dict | None = None,
) -> str:
    phones = entities.get("phones") or []
    upi_ids = entities.get("upi_ids") or []
    urgency = entities.get("urgency_flags") or []
    details = consistency_result.get("contradiction_details") or []
    media_lines: list[str] = []
    if media_context:
        for key, value in media_context.items():
            media_lines.append(f"{key}: {value}")

    lines = [
        "=== MESSAGE ===",
        text.strip(),
        "",
        "=== EXTRACTED ENTITIES ===",
        f"Company: {entities.get('company') or 'N/A'}",
        f"Phones: {phones or 'N/A'}",
        f"Salary claimed: {entities.get('salary') or 'N/A'}",
        f"Fee requested: {entities.get('fee') or 'N/A'}",
        f"Claimed location: {entities.get('location') or 'N/A'}",
        f"Job role: {entities.get('role') or 'N/A'}",
        f"UPI IDs: {upi_ids or 'N/A'}",
        f"Urgency phrases: {urgency or 'N/A'}",
        "",
        "=== LAYER 1 - EMBEDDING SIMILARITY ===",
        f"Similarity to legitimate cluster: {embedding_result.get('sim_to_legitimate')}",
        f"Similarity to scam cluster: {embedding_result.get('sim_to_scam')}",
        f"Boundary distance: {embedding_result.get('boundary_distance')}",
        f"Embedding scam score: {embedding_result.get('embedding_score')}",
        "",
        "=== LAYER 2 - CROSS-REFERENCE CONSISTENCY ===",
        f"Total contradictions: {consistency_result.get('contradictions')}",
        f"Checks run: {consistency_result.get('checks')}",
        f"DB details: {details or 'N/A'}",
        "",
        "=== LAYER 3 - PROPAGATION ANALYSIS ===",
        f"Seen count: {propagation_result.get('seen_count')}",
        f"Source channels: {propagation_result.get('source_channels_count')}",
        f"Forwarded many times: {propagation_result.get('forwarded_many_times')}",
        f"Broadcast score: {propagation_result.get('propagation_score')}",
        f"Broadcast pattern: {propagation_result.get('is_broadcast')}",
    ]
    if media_lines:
        lines.extend(["", "=== MEDIA CONTEXT ===", *media_lines])
    return "\n".join(lines)


def _call_groq_sync(evidence_bundle: str) -> dict[str, Any]:
    api_key = settings.GROQ_API_KEY
    if not api_key:
        raise ValueError("GROQ_API_KEY environment variable is not set.")

    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": evidence_bundle},
        ],
        "temperature": 0.1,
        "max_tokens": 600,
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    response = requests.post(GROQ_API_URL, headers=headers, json=payload, timeout=45)
    response.raise_for_status()
    data = response.json()
    content = data["choices"][0]["message"]["content"]
    return _extract_json(content)


def _normalize_llm_result(raw: dict[str, Any]) -> dict[str, Any]:
    verdict = _coerce_verdict(raw.get("verdict"))
    confidence = _coerce_confidence(raw.get("confidence"))
    reasoning = str(raw.get("reasoning") or "").strip() or "Evidence indicates inconsistent recruitment behavior."
    key_contradiction = raw.get("key_contradiction")
    if key_contradiction is not None:
        key_contradiction = str(key_contradiction).strip() or None
        if isinstance(key_contradiction, str) and key_contradiction.lower() == "null":
            key_contradiction = None

    hindi_message = str(raw.get("hindi_worker_message") or "").strip()
    if not hindi_message:
        if verdict == "HIGH_RISK":
            hindi_message = "Yeh offer high risk lag raha hai, paise mat bhejiye."
        elif verdict == "SUSPICIOUS":
            hindi_message = "Is offer ko verify kiye bina koi payment mat kijiye."
        else:
            hindi_message = "Offer filhal theek lagta hai, fir bhi details verify kar lijiye."

    return {
        "verdict": verdict,
        "confidence": confidence,
        "reasoning": reasoning,
        "key_contradiction": key_contradiction,
        "hindi_worker_message": hindi_message,
        "risk_score": VERDICT_TO_SCORE[verdict],
    }


async def investigate_with_llm(
    text: str,
    entities: dict,
    embedding_result: dict,
    consistency_result: dict,
    propagation_result: dict,
    media_context: dict | None = None,
) -> dict[str, Any]:
    evidence_bundle = _build_evidence_bundle(
        text=text,
        entities=entities,
        embedding_result=embedding_result,
        consistency_result=consistency_result,
        propagation_result=propagation_result,
        media_context=media_context,
    )

    try:
        raw = await to_thread.run_sync(_call_groq_sync, evidence_bundle)
        return _normalize_llm_result(raw)
    except Exception as exc:
        logger.exception("LLM investigator (Groq) failed")
        error_text = str(exc).strip() or "unknown_error"

    return {
        "verdict": "SUSPICIOUS",
        "confidence": 55,
        "reasoning": f"AI investigator unavailable (Groq failure: {error_text}).",
        "key_contradiction": None,
        "hindi_worker_message": "System busy hai, verification ke bina payment na karein.",
        "risk_score": VERDICT_TO_SCORE["SUSPICIOUS"],
        "llm_error": error_text,
    }
