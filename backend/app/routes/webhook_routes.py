import os
import re

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import JSONResponse
from twilio.rest import Client
from twilio.request_validator import RequestValidator

from app.services.cache.redis_client import get_cache, set_cache
from app.services.queue.task_queue import enqueue_job

router = APIRouter(tags=["webhooks"])

_twilio_auth_token = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
_validator = RequestValidator(_twilio_auth_token) if _twilio_auth_token else None
_twilio_account_sid = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
_from_number = os.getenv("TWILIO_WHATSAPP_NUMBER", "").strip()
_twilio_client = Client(_twilio_account_sid, _twilio_auth_token) if (_twilio_account_sid and _twilio_auth_token) else None
_devanagari_re = re.compile(r"[\u0900-\u097F]")
_hindi_tokens = {
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


def _normalize_language(text: str | None) -> str | None:
    value = (text or "").strip().lower()
    if value in {"en", "english"}:
        return "en"
    if value in {"hi", "hindi", "हिंदी", "हिन्दी"}:
        return "hi"
    return None


def _detect_language(text: str) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return "en"
    if _devanagari_re.search(cleaned):
        return "hi"
    words = re.findall(r"[a-zA-Z']+", cleaned.lower())
    if not words:
        return "en"
    hits = sum(1 for word in words if word in _hindi_tokens)
    if hits >= 2 or (hits >= 1 and len(words) <= 6):
        return "hi"
    return "en"


def _send_whatsapp_message(to_number: str, body: str) -> None:
    if not (_twilio_client and _from_number and to_number and body):
        return
    _twilio_client.messages.create(
        from_=_from_number,
        to=to_number,
        body=body,
    )


@router.post("/whatsapp")
async def whatsapp_webhook(
    request: Request,
    Body: str = Form(default=""),
    From: str = Form(default=""),
    NumMedia: str = Form(default="0"),
    MediaUrl0: str = Form(default=""),
    MediaContentType0: str = Form(default=""),
):
    if _validator is not None:
        signature = request.headers.get("X-Twilio-Signature", "")
        form_data = dict(await request.form())
        if not _validator.validate(str(request.url), form_data, signature):
            raise HTTPException(status_code=403, detail="Invalid Twilio signature")

    try:
        media_count = int(NumMedia or 0)
    except ValueError:
        media_count = 0

    language_command = _normalize_language(Body)
    if language_command and media_count == 0:
        set_cache(f"wa:lang:{From}", language_command, ttl=60 * 60 * 24 * 30)
        reply = (
            "भाषा हिंदी पर सेट है। कृपया अपना संदेश/फोटो/वॉइस नोट भेजें।"
            if language_command == "hi"
            else "Language set to English. Please send your message/photo/voice note."
        )
        _send_whatsapp_message(From, reply)
        return JSONResponse(content={"status": "language_updated", "language": language_command})

    preferred_language = get_cache(f"wa:lang:{From}") or _detect_language(Body)
    waiting_text = (
        "आपका संदेश विश्लेषण हो रहा है, कृपया थोड़ा इंतज़ार करें..."
        if preferred_language == "hi"
        else "Analyzing your message, please wait..."
    )
    _send_whatsapp_message(From, waiting_text)

    enqueue_job(
        {
            "from_number": From,
            "body_text": Body,
            "media_count": media_count,
            "media_url": MediaUrl0,
            "media_content_type": MediaContentType0,
            "preferred_language": preferred_language,
        }
    )

    return JSONResponse(content={"status": "queued"})
