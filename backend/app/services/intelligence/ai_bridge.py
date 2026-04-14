from __future__ import annotations

import re
from typing import Any

_DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")
_HINDI_ROMAN_TOKENS = {
    "hai",
    "nahi",
    "nahin",
    "kya",
    "kyu",
    "kyun",
    "kaise",
    "kripya",
    "aap",
    "hum",
    "paise",
    "bhejo",
    "bhejiye",
    "jaldi",
    "naukri",
    "farzi",
    "dhokha",
}


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


def _media_failure_result(message: str) -> dict[str, Any]:
    return {
        "risk_score": 0.5,
        "risk_level": "MEDIUM",
        "is_scam": False,
        "verdict": "SUSPICIOUS",
        "confidence": 0,
        "reasons": [message],
        "key_contradiction": None,
        "hindi_worker_message": "Data parse nahin ho paaya, verify karke hi paise bhejein.",
        "hindi_verdict": "Data parse nahin ho paaya, verify karke hi paise bhejein.",
        "english_summary": message,
        "entities": {
            "phones": [],
            "phone": [],
            "salary": None,
            "fee": None,
            "role": None,
            "location": None,
            "agent": None,
            "company": None,
            "upi_ids": [],
            "upi": [],
            "urgency_flags": [],
            "has_fee": False,
            "has_urgency": False,
        },
        "source": "pipeline",
    }


async def analyze_text_with_ai(
    text: str,
    source_channel: str = "dashboard",
    forwarded_many_times: bool = False,
) -> dict[str, Any]:
    from app.services.intelligence.pipeline import run_intelligence_pipeline

    return await run_intelligence_pipeline(
        text=text,
        forwarded_many_times=forwarded_many_times,
        source_channel=source_channel,
    )


async def analyze_image_with_ai(
    filename: str,
    content: bytes,
    content_type: str | None = None,
    source_channel: str = "whatsapp",
) -> dict[str, Any]:
    from app.services.intelligence.pipeline import run_intelligence_pipeline
    from app.services.media.image_pipeline import process_image

    _ = (filename, content_type)
    ocr_result = process_image(content)
    if not ocr_result.get("success") or not ocr_result.get("extracted_text"):
        return _media_failure_result("Could not extract text from image.")

    extracted_text = str(ocr_result["extracted_text"]).strip()
    result = await run_intelligence_pipeline(
        text=extracted_text,
        source_channel=source_channel,
        media_context={
            "image_quality": ocr_result.get("image_quality"),
            "image_type": ocr_result.get("image_type"),
            "ocr_confidence": ocr_result.get("confidence"),
        },
    )
    result["extracted_text"] = extracted_text
    result["detected_input_language"] = _detect_language(extracted_text)
    return result


async def analyze_audio_with_ai(
    filename: str,
    content: bytes,
    content_type: str | None = None,
    source_channel: str = "whatsapp",
) -> dict[str, Any]:
    from app.services.intelligence.pipeline import run_intelligence_pipeline
    from app.services.media.audio_pipeline import process_audio

    _ = (filename, content_type)
    audio_result = process_audio(content)
    if not audio_result.get("success") or not audio_result.get("transcript"):
        return _media_failure_result("Could not transcribe audio.")

    extracted_text = str(audio_result["transcript"]).strip()
    result = await run_intelligence_pipeline(
        text=extracted_text,
        source_channel=source_channel,
        media_context={
            "audio_language": audio_result.get("language_name"),
            "audio_duration_seconds": audio_result.get("duration_seconds"),
            "audio_confidence": audio_result.get("confidence"),
        },
    )
    result["extracted_text"] = extracted_text
    result["detected_input_language"] = _detect_language(extracted_text)
    language_name = audio_result.get("language_name")
    if isinstance(language_name, str) and language_name.strip():
        result["detected_audio_language_name"] = language_name.strip()
    return result


async def analyze_document_with_ai(
    filename: str,
    content: bytes,
    content_type: str | None = None,
    source_channel: str = "whatsapp",
) -> dict[str, Any]:
    from app.services.intelligence.pipeline import run_intelligence_pipeline
    from app.services.media.doc_pipeline import process_document

    _ = content_type
    doc_result = process_document(content, filename=filename)
    if not doc_result.get("success") or not doc_result.get("extracted_text"):
        return _media_failure_result("Could not extract text from document.")

    extracted_text = str(doc_result["extracted_text"]).strip()
    result = await run_intelligence_pipeline(
        text=extracted_text,
        source_channel=source_channel,
        media_context={
            "doc_format": doc_result.get("doc_format"),
            "forgery_risk": doc_result.get("forgery_risk"),
            "forgery_reasons": doc_result.get("forgery_reasons"),
            "typosquatting_detected": doc_result.get("typosquatting_detected"),
            "typosquatting_similar_to": doc_result.get("typosquatting_similar_to"),
        },
    )
    result["extracted_text"] = extracted_text
    result["detected_input_language"] = _detect_language(extracted_text)
    return result
