from __future__ import annotations

from typing import Any
import os
import re

import httpx

from app.services.intelligence.analyzer import analyze_text as local_analyze_text
from app.services.intelligence.entity_extractor import extract_entities
from app.services.graph.graph_service import store_message_graph
from app.services.graph.syndicate_detector import detect_and_store_syndicates
from app.core.config import settings

AI_SERVICE_BASE_URL = (settings.AI_SERVICE_URL or "http://127.0.0.1:8001").rstrip("/")
AI_TIMEOUT_SECONDS = 5.0
AI_MEDIA_TIMEOUT_SECONDS = float(os.getenv("AI_MEDIA_TIMEOUT", "30"))
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


def _risk_level_from_score(score: float) -> str:
    if score < 0.3:
        return "LOW"
    if score <= 0.6:
        return "MEDIUM"
    return "HIGH"


def _normalize_score(raw_score: Any) -> float:
    if isinstance(raw_score, (int, float)):
        if raw_score > 1:
            return max(0.0, min(1.0, float(raw_score) / 100.0))
        return max(0.0, min(1.0, float(raw_score)))
    return 0.0


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _normalize_entities(raw_entities: dict[str, Any]) -> dict[str, Any]:
    phone = _as_list(raw_entities.get("phone") or raw_entities.get("phones") or raw_entities.get("phone_number"))
    salary = _as_list(raw_entities.get("salary") or raw_entities.get("salaries"))
    fee = _as_list(
        raw_entities.get("fee")
        or raw_entities.get("fees")
        or raw_entities.get("registration_fee")
    )
    upi = _as_list(raw_entities.get("upi") or raw_entities.get("upi_id") or raw_entities.get("upi_ids"))

    company = raw_entities.get("company") or raw_entities.get("company_name") or ""
    location = raw_entities.get("location") or raw_entities.get("city") or ""
    if not location:
        locations = _as_list(raw_entities.get("locations"))
        location = locations[0] if locations else ""

    return {
        "phone": [str(value).strip() for value in phone if str(value).strip()],
        "salary": [value for value in salary if value is not None and str(value).strip()],
        "fee": [value for value in fee if value is not None and str(value).strip()],
        "company": str(company).strip(),
        "location": str(location).strip(),
        "upi": [str(value).strip() for value in upi if str(value).strip()],
    }


def _merge_with_rule_entities(text: str, entities: dict[str, Any]) -> dict[str, Any]:
    """Backfill weak/missing AI entities using deterministic extraction."""
    try:
        rules = extract_entities(text)
    except Exception:
        return entities

    merged = dict(entities)

    ai_phones = merged.get("phone")
    if not isinstance(ai_phones, list) or not ai_phones:
        merged["phone"] = [str(item).strip() for item in rules.get("phones", []) if str(item).strip()]

    if not str(merged.get("location") or "").strip():
        merged["location"] = str(rules.get("location") or "").strip()

    if not str(merged.get("company") or "").strip():
        merged["company"] = str(rules.get("company") or "").strip()

    salary_values = merged.get("salary")
    if not isinstance(salary_values, list) or not salary_values:
        salary = rules.get("salary")
        merged["salary"] = [salary] if salary is not None else []

    fee_values = merged.get("fee")
    if not isinstance(fee_values, list) or not fee_values:
        fee = rules.get("fee")
        merged["fee"] = [fee] if fee is not None else []

    role = str(rules.get("role") or "").strip()
    if role and not str(merged.get("role") or "").strip():
        merged["role"] = role

    return merged


def _normalize_analysis_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize AI/local analysis output to a single response schema."""
    raw_score = payload.get("risk_score")
    if raw_score is None:
        scam_risk = str((payload.get("scam_result") or {}).get("scam_risk") or "").lower()
        if scam_risk == "high":
            raw_score = 0.85
        elif scam_risk == "medium":
            raw_score = 0.5
        else:
            raw_score = 0.15

    score = round(_normalize_score(raw_score), 2)

    risk_level = str(payload.get("risk_level") or payload.get("risk_label") or "").upper()
    if risk_level not in {"LOW", "MEDIUM", "HIGH"}:
        if risk_level in {"SAFE"}:
            risk_level = "LOW"
        elif risk_level in {"SUSPICIOUS"}:
            risk_level = "MEDIUM"
        elif risk_level in {"HIGH_RISK", "SCAM"}:
            risk_level = "HIGH"
        else:
            risk_level = _risk_level_from_score(score)

    reasons = payload.get("reasons")
    if not isinstance(reasons, list):
        reasons = []

    entities_data = payload.get("entities")
    if not isinstance(entities_data, dict):
        entities_data = {}
    scam_entities = (payload.get("scam_result") or {}).get("entities")
    if isinstance(scam_entities, dict):
        entities_data = {**scam_entities, **entities_data}

    result = {
        "risk_score": score,
        "risk_level": risk_level,
        "reasons": [str(reason) for reason in reasons if str(reason).strip()],
        "entities": _normalize_entities(entities_data),
    }
    if isinstance(payload.get("hindi_verdict"), str):
        result["hindi_verdict"] = payload["hindi_verdict"]
    if isinstance(payload.get("english_summary"), str):
        result["english_summary"] = payload["english_summary"]
    return result


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


async def call_ai_service(path: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    """Call AI service JSON endpoint and return None on any network/runtime failure."""
    try:
        async with httpx.AsyncClient(timeout=AI_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{AI_SERVICE_BASE_URL}{path}",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                return None
            return data
    except (httpx.RequestError, httpx.HTTPStatusError, ValueError):
        return None


async def _call_ai_service_file(
    path: str, filename: str, content: bytes, content_type: str | None
) -> dict[str, Any] | None:
    try:
        ctype = content_type or "application/octet-stream"
        files = {"file": (filename, content, ctype)}
        async with httpx.AsyncClient(timeout=AI_MEDIA_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{AI_SERVICE_BASE_URL}{path}",
                files=files,
            )
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                return None
            return data
    except (httpx.RequestError, httpx.HTTPStatusError, ValueError):
        return None


def _extract_text_from_ai_payload(payload: dict[str, Any]) -> str:
    """Extract textual content from media AI-service responses."""
    candidates = [
        payload.get("text"),
        payload.get("extracted_text"),
        payload.get("transcript"),
        (payload.get("scam_result") or {}).get("text"),
    ]
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return ""


async def analyze_text_with_ai(text: str, source_channel: str = "dashboard") -> dict[str, Any]:
    payload = await call_ai_service(
        "/analyse/text",
        {"text": text, "source_channel": source_channel},
    )
    if payload is not None:
        result = _normalize_analysis_payload(payload)
        result["entities"] = _merge_with_rule_entities(text, result.get("entities", {}))
        try:
            result["graph"] = store_message_graph(result.get("entities", {}))
            detect_and_store_syndicates()
        except Exception:
            result["graph"] = {"nodes": [], "edges": []}
        result["source"] = "ai-services"
        return result

    fallback = local_analyze_text(text, enable_llm=True)
    if isinstance(fallback, dict):
        result = _normalize_analysis_payload(fallback)
        result["entities"] = _merge_with_rule_entities(text, result.get("entities", {}))
        try:
            result["graph"] = store_message_graph(result.get("entities", {}))
            detect_and_store_syndicates()
        except Exception:
            result["graph"] = {"nodes": [], "edges": []}
        result["source"] = "backend-rules"
        return result
    return {
        "risk_score": 0.0,
        "risk_level": "LOW",
        "reasons": ["Analysis failed"],
        "entities": _normalize_entities({}),
        "graph": {"nodes": [], "edges": []},
        "source": "backend-rules",
    }


async def analyze_image_with_ai(
    filename: str,
    content: bytes,
    content_type: str | None = None,
    source_channel: str = "dashboard",
) -> dict[str, Any]:
    payload = await _call_ai_service_file("/analyse/image", filename, content, content_type)
    if payload is None:
        raise RuntimeError("AI service unavailable for image OCR.")
    extracted_text = _extract_text_from_ai_payload(payload)
    if extracted_text:
        result = await analyze_text_with_ai(extracted_text, source_channel=source_channel)
        result["extracted_text"] = extracted_text
        result["detected_input_language"] = _detect_language(extracted_text)
        return result
    result = _normalize_analysis_payload(payload)
    result["source"] = "ai-services"
    return result


async def analyze_audio_with_ai(
    filename: str,
    content: bytes,
    content_type: str | None = None,
    source_channel: str = "dashboard",
) -> dict[str, Any]:
    payload = await _call_ai_service_file("/analyse/audio", filename, content, content_type)
    if payload is None:
        raise RuntimeError("AI service unavailable for audio transcription.")
    extracted_text = _extract_text_from_ai_payload(payload)
    if extracted_text:
        result = await analyze_text_with_ai(extracted_text, source_channel=source_channel)
        result["extracted_text"] = extracted_text
        result["detected_input_language"] = _detect_language(extracted_text)
        language_name = payload.get("language_name")
        if isinstance(language_name, str) and language_name.strip():
            result["detected_audio_language_name"] = language_name.strip()
        return result
    result = _normalize_analysis_payload(payload)
    result["source"] = "ai-services"
    return result


async def analyze_document_with_ai(
    filename: str,
    content: bytes,
    content_type: str | None = None,
    source_channel: str = "dashboard",
) -> dict[str, Any]:
    payload = await _call_ai_service_file("/analyse/document", filename, content, content_type)
    if payload is None:
        raise RuntimeError("AI service unavailable for document OCR.")
    extracted_text = _extract_text_from_ai_payload(payload)
    if extracted_text:
        result = await analyze_text_with_ai(extracted_text, source_channel=source_channel)
        result["extracted_text"] = extracted_text
        result["detected_input_language"] = _detect_language(extracted_text)
        return result
    result = _normalize_analysis_payload(payload)
    result["source"] = "ai-services"
    return result


async def is_ai_service_available() -> bool:
    try:
        async with httpx.AsyncClient(timeout=AI_TIMEOUT_SECONDS) as client:
            response = await client.get(f"{AI_SERVICE_BASE_URL}/health")
            return response.status_code < 400
    except httpx.RequestError:
        return False
