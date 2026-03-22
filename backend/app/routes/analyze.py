import hashlib
import json
import logging

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from app.models.schemas import AnalyzeRequest
from app.core.rate_limiter import limiter
from app.middleware.rate_limit import check_rate_limit
from app.services.cache.redis_client import get_cache, set_cache
from app.services.intelligence.ai_bridge import (
    analyze_audio_with_ai,
    analyze_document_with_ai,
    analyze_image_with_ai,
    analyze_text_with_ai,
)
from app.services.scam_report_store import store_analysis_report, store_report_edges

router = APIRouter(prefix="/api", tags=["analysis"])
logger = logging.getLogger(__name__)

SOURCE_MAP = {
    "browser_extension": "extension",
    "extension": "extension",
    "whatsapp": "whatsapp",
    "dashboard": "dashboard",
}


def _normalize_source(source: str | None) -> str:
    return SOURCE_MAP.get((source or "dashboard").strip().lower(), "dashboard")


def _store_if_high_risk(result: dict, source: str) -> None:
    risk_score = float(result.get("risk_score") or 0)
    if risk_score <= 0.6:
        return

    report = store_analysis_report(result, source=source)
    entities = result.get("entities")
    if isinstance(entities, dict) and report:
        store_report_edges(entities)


def _log_analysis_event(result: dict, source: str) -> None:
    entities = result.get("entities") if isinstance(result.get("entities"), dict) else {}
    logger.info(
        json.dumps(
            {
                "event": "analysis_complete",
                "risk_score": result.get("risk_score"),
                "phones": entities.get("phone", []),
                "source": source,
            }
        )
    )


@router.post("/analyze")
@limiter.limit("10/minute")
async def analyze(payload: AnalyzeRequest, request: Request):
    text = (payload.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text cannot be empty.")

    phone_number = (payload.phone_number or "").strip() or (request.client.host if request.client else "unknown")
    allowed = check_rate_limit(phone_number)
    if not allowed:
        return JSONResponse(
            status_code=429,
            content={"error": "Too many requests. Try again later."}
        )

    source = _normalize_source(payload.source)

    message_hash = hashlib.sha256(text.encode()).hexdigest()
    cache_key = f"analysis:{message_hash}"
    cached = get_cache(cache_key)
    if cached:
        return json.loads(cached)

    result = await analyze_text_with_ai(text, source_channel=source)
    _store_if_high_risk(result, source)
    _log_analysis_event(result, source)

    set_cache(cache_key, json.dumps(result), ttl=86400)
    return result


@router.post("/analyze/image")
async def analyze_image(request: Request, file: UploadFile = File(...)):
    phone_number = request.client.host if request.client else "unknown"
    allowed = check_rate_limit(phone_number)
    if not allowed:
        return JSONResponse(
            status_code=429,
            content={"error": "Too many requests. Try again later."}
        )
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file upload.")
    try:
        result = await analyze_image_with_ai(
            file.filename or "image.jpg",
            content,
            file.content_type,
            source_channel="whatsapp",
        )
        _store_if_high_risk(result, "whatsapp")
        _log_analysis_event(result, "whatsapp")
        return result
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Image analysis unavailable: {exc}") from exc


@router.post("/analyze/audio")
async def analyze_audio(request: Request, file: UploadFile = File(...)):
    phone_number = request.client.host if request.client else "unknown"
    allowed = check_rate_limit(phone_number)
    if not allowed:
        return JSONResponse(
            status_code=429,
            content={"error": "Too many requests. Try again later."}
        )
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file upload.")
    try:
        result = await analyze_audio_with_ai(
            file.filename or "audio.ogg",
            content,
            file.content_type,
            source_channel="whatsapp",
        )
        _store_if_high_risk(result, "whatsapp")
        _log_analysis_event(result, "whatsapp")
        return result
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Audio analysis unavailable: {exc}") from exc


@router.post("/analyze/document")
async def analyze_document(request: Request, file: UploadFile = File(...)):
    phone_number = request.client.host if request.client else "unknown"
    allowed = check_rate_limit(phone_number)
    if not allowed:
        return JSONResponse(
            status_code=429,
            content={"error": "Too many requests. Try again later."}
        )
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file upload.")
    try:
        result = await analyze_document_with_ai(
            file.filename or "document.pdf",
            content,
            file.content_type,
            source_channel="whatsapp",
        )
        _store_if_high_risk(result, "whatsapp")
        _log_analysis_event(result, "whatsapp")
        return result
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Document analysis unavailable: {exc}") from exc
