from __future__ import annotations

import asyncio
import json
import mimetypes
import os
import re
import sys
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from twilio.rest import Client

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

from app.services.queue.task_queue import dequeue_job
from app.services.cache.redis_client import get_cache, set_cache
from app.services.intelligence.ai_bridge import (
    analyze_audio_with_ai,
    analyze_document_with_ai,
    analyze_image_with_ai,
    analyze_text_with_ai,
)
from app.services.scam_report_store import store_analysis_report, store_report_edges

load_dotenv()

ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
FROM_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER", "")

client = Client(ACCOUNT_SID, AUTH_TOKEN)
_DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")
_HINDI_ROMAN_TOKENS = {
    "hai",
    "nahi",
    "nahin",
    "kya",
    "kyu",
    "kyun",
    "kaise",
    "aap",
    "hum",
    "paise",
    "jaldi",
    "naukri",
    "farzi",
    "dhokha",
}
_REASON_TRANSLATIONS_HI = {
    "registration fee requested": "रजिस्ट्रेशन फीस मांगी गई है",
    "urgency language detected": "जल्दी निर्णय लेने का दबाव बनाया गया है",
    "salary anomaly": "सैलरी असामान्य रूप से ज्यादा दिखाई गई है",
    "company not identified": "कंपनी की जानकारी सत्यापित नहीं हुई",
    "fee requested": "फीस मांगी गई है",
    "unknown company": "कंपनी की पहचान स्पष्ट नहीं है",
    "analysis failed": "विश्लेषण नहीं हो पाया",
    "empty input": "इनपुट खाली था",
}


def _detect_media_endpoint(content_type: str) -> str | None:
    ctype = (content_type or "").lower()
    if ctype.startswith("image/"):
        return "image"
    if ctype.startswith("audio/") or ctype.startswith("video/"):
        return "audio"
    if "pdf" in ctype or "msword" in ctype or "officedocument.wordprocessingml.document" in ctype:
        return "document"
    return None


def _store_if_high_risk(result: dict[str, Any]) -> None:
    risk_score = float(result.get("risk_score") or 0)
    if risk_score <= 0.6:
        return
    report = store_analysis_report(result, source="whatsapp")
    entities = result.get("entities")
    if isinstance(entities, dict) and report:
        store_report_edges(entities)


def _score_percent(result: dict[str, Any]) -> int:
    risk_score = result.get("risk_score", 0)
    try:
        score_percent = int(round(float(risk_score) * 100)) if float(risk_score) <= 1 else int(round(float(risk_score)))
    except (TypeError, ValueError):
        score_percent = 0
    return max(0, min(100, score_percent))


def _normalize_language(code: str | None) -> str | None:
    value = (code or "").strip().lower()
    if value in {"en", "english"}:
        return "en"
    if value in {"hi", "hindi", "हिंदी", "हिन्दी"}:
        return "hi"
    return None


def _detect_language(text: str) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return "en"
    if _DEVANAGARI_RE.search(cleaned):
        return "hi"
    words = re.findall(r"[a-zA-Z']+", cleaned.lower())
    if not words:
        return "en"
    hindi_hits = sum(1 for word in words if word in _HINDI_ROMAN_TOKENS)
    if hindi_hits >= 2 or (hindi_hits >= 1 and len(words) <= 6):
        return "hi"
    return "en"


def _translate_reason(reason: str, language: str) -> str:
    clean_reason = reason.strip()
    if language == "hi":
        return _REASON_TRANSLATIONS_HI.get(clean_reason.lower(), clean_reason)
    return clean_reason


def _resolve_response_language(from_number: str, body_text: str, result: dict[str, Any], preferred_language: str) -> str:
    explicit = _normalize_language(result.get("detected_input_language") if isinstance(result, dict) else None)
    if explicit:
        return explicit
    extracted = result.get("extracted_text") if isinstance(result, dict) else None
    if isinstance(extracted, str) and extracted.strip():
        return _detect_language(extracted)
    pref = _normalize_language(preferred_language) or _normalize_language(get_cache(f"wa:lang:{from_number}"))
    if pref:
        return pref
    if body_text.strip():
        return _detect_language(body_text)
    return "en"


def _build_localized_response(result: dict[str, Any], language: str) -> str:
    score = _score_percent(result)
    reasons = result.get("reasons")
    if not isinstance(reasons, list):
        reasons = []
    localized_reasons = [_translate_reason(str(reason), language) for reason in reasons[:3]]

    if language == "hi":
        if score >= 65:
            verdict = "खतरा"
            advice = "कोई भुगतान न करें। कंपनी और नंबर सत्यापित किए बिना आगे न बढ़ें।"
        elif score >= 35:
            verdict = "संदिग्ध"
            advice = "अभी भुगतान न करें। कंपनी पंजीकरण और संपर्क विवरण जांचें।"
        else:
            verdict = "कम जोखिम"
            advice = "फिलहाल जोखिम कम लगता है, फिर भी सत्यापन करके ही निर्णय लें।"
        reasons_text = "\n".join(f"* {item}" for item in localized_reasons) if localized_reasons else "* कोई स्पष्ट रेड फ्लैग नहीं मिला"
        return (
            "*NaukariSaathi - जॉब सेफ्टी चेक*\n"
            "-------------------------------\n"
            f"वर्डिक्ट: {verdict}\n"
            f"रिस्क स्कोर: {score}%\n\n"
            f"कारण:\n{reasons_text}\n\n"
            f"सलाह: {advice}\n\n"
            "अंग्रेज़ी में देखने के लिए *EN* लिखें।\n"
            "_हम कभी पैसे, OTP, या आधार नहीं मांगते।_"
        )

    if score >= 65:
        verdict = "DANGER"
        advice = "Do not send any payment. Verify the company and contact first."
    elif score >= 35:
        verdict = "SUSPICIOUS"
        advice = "Avoid payment for now. Verify company registration and contact details."
    else:
        verdict = "LOW RISK"
        advice = "Risk appears low, but still verify details before you act."
    reasons_text = "\n".join(f"* {item}" for item in localized_reasons) if localized_reasons else "* No clear red flags found"
    return (
        "*NaukariSaathi - Job Safety Check*\n"
        "-------------------------------\n"
        f"Verdict: {verdict}\n"
        f"Risk Score: {score}%\n\n"
        f"Reasons:\n{reasons_text}\n\n"
        f"Advice: {advice}\n\n"
        "Reply *HI* to view this in Hindi.\n"
        "_We never ask for money, OTP, or Aadhaar._"
    )


async def _fetch_media(media_url: str, content_type: str) -> tuple[str, bytes]:
    async with httpx.AsyncClient(timeout=40, follow_redirects=True) as http_client:
        response = await http_client.get(media_url, auth=(ACCOUNT_SID, AUTH_TOKEN))
        response.raise_for_status()
        filename = media_url.rstrip("/").split("/")[-1] or "upload.bin"
        if "." not in filename:
            guessed_ext = mimetypes.guess_extension((content_type or "").split(";")[0].strip().lower())
            if guessed_ext:
                filename = f"{filename}{guessed_ext}"
        return filename, response.content


async def process_message(job: dict[str, Any]) -> None:
    from_number = str(job.get("from_number") or "")
    body_text = str(job.get("body_text") or "")
    media_url = str(job.get("media_url") or "")
    media_content_type = str(job.get("media_content_type") or "")
    media_count = int(job.get("media_count") or 0)
    preferred_language = str(job.get("preferred_language") or "")

    if not from_number:
        return

    try:
        if media_count > 0 and media_url:
            endpoint = _detect_media_endpoint(media_content_type)
            if not endpoint:
                raise ValueError(f"Unsupported media type: {media_content_type}")
            filename, content = await _fetch_media(media_url, media_content_type)
            if endpoint == "image":
                result = await analyze_image_with_ai(filename, content, media_content_type, source_channel="whatsapp")
            elif endpoint == "audio":
                result = await analyze_audio_with_ai(filename, content, media_content_type, source_channel="whatsapp")
            else:
                result = await analyze_document_with_ai(filename, content, media_content_type, source_channel="whatsapp")
        elif body_text.strip():
            result = await analyze_text_with_ai(body_text, source_channel="whatsapp")
        else:
            result = {"risk_score": 0.0, "reasons": ["Empty input"]}
    except Exception as exc:
        result = {"risk_score": 0.5, "reasons": [f"Analysis service unavailable: {exc}"]}

    _store_if_high_risk(result)

    response_language = _resolve_response_language(from_number, body_text, result, preferred_language)
    set_cache(f"wa:lang:{from_number}", response_language, ttl=60 * 60 * 24 * 30)
    set_cache(f"wa:last:{from_number}", json.dumps(result), ttl=60 * 60 * 24 * 7)
    response_text = _build_localized_response(result, response_language)
    client.messages.create(
        from_=FROM_NUMBER,
        to=from_number,
        body=response_text,
    )


def main() -> None:
    while True:
        job = dequeue_job()
        if job:
            asyncio.run(process_message(job))


if __name__ == "__main__":
    main()
