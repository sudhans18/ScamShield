from __future__ import annotations

import os
import mimetypes
import re
import sys
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, Form, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from twilio.request_validator import RequestValidator
from twilio.rest import Client

load_dotenv()

app = FastAPI()

ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
FROM_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER", "")
BACKEND_BASE_URL = os.getenv("BACKEND_API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")

client = Client(ACCOUNT_SID, AUTH_TOKEN)
validator = RequestValidator(AUTH_TOKEN)
USER_LANGUAGE_PREFS: dict[str, str] = {}
LAST_ANALYSIS_BY_USER: dict[str, dict[str, Any]] = {}
SUPPORTED_LANGUAGES = {"en", "hi"}
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

_BACKEND_PATH = Path(__file__).resolve().parents[1] / "backend"
if str(_BACKEND_PATH) not in sys.path:
    sys.path.append(str(_BACKEND_PATH))

from app.services.queue.task_queue import enqueue_job


def _score_percent(result: dict[str, Any]) -> int:
    raw_score = result.get("risk_score", 0)
    if isinstance(raw_score, (int, float)):
        if raw_score > 1:
            return max(0, min(100, int(round(raw_score))))
        return max(0, min(100, int(round(raw_score * 100))))
    return 0


def _normalize_language(code: str | None) -> str | None:
    value = (code or "").strip().lower()
    if value in SUPPORTED_LANGUAGES:
        return value
    if value in {"hindi", "हिंदी", "हिन्दी"}:
        return "hi"
    if value in {"english", "eng"}:
        return "en"
    return None


def _parse_language_command(body_text: str) -> str | None:
    text = (body_text or "").strip()
    if not text:
        return None
    compact = re.sub(r"[^a-zA-Z\u0900-\u097F ]+", "", text).strip().lower()
    if compact in {"en", "english", "lang en", "language en", "language english"}:
        return "en"
    if compact in {"hi", "hindi", "हिंदी", "हिन्दी", "lang hi", "language hi", "language hindi"}:
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


def _resolve_response_language(
    from_number: str,
    body_text: str,
    result: dict[str, Any],
) -> str:
    explicit = _normalize_language(result.get("detected_input_language") if isinstance(result, dict) else None)
    if explicit:
        USER_LANGUAGE_PREFS[from_number] = explicit
        return explicit

    if isinstance(result, dict):
        extracted = result.get("extracted_text")
        if isinstance(extracted, str) and extracted.strip():
            detected = _detect_language(extracted)
            USER_LANGUAGE_PREFS[from_number] = detected
            return detected

    if body_text.strip():
        detected = _detect_language(body_text)
        USER_LANGUAGE_PREFS[from_number] = detected
        return detected

    preferred = _normalize_language(USER_LANGUAGE_PREFS.get(from_number))
    return preferred or "en"


def _translate_reason(reason: str, language: str) -> str:
    clean_reason = reason.strip()
    if language == "hi":
        return _REASON_TRANSLATIONS_HI.get(clean_reason.lower(), clean_reason)
    return clean_reason


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
            "*ScamShield - जॉब सेफ़्टी चेक*\n"
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
        "*ScamShield - Job Safety Check*\n"
        "-------------------------------\n"
        f"Verdict: {verdict}\n"
        f"Risk Score: {score}%\n\n"
        f"Reasons:\n{reasons_text}\n\n"
        f"Advice: {advice}\n\n"
        "Reply *HI* to view this in Hindi.\n"
        "_We never ask for money, OTP, or Aadhaar._"
    )


def _language_change_reply(language: str) -> str:
    if language == "hi":
        return "भाषा हिंदी पर सेट है। कृपया अपना संदेश/फोटो/वॉइस नोट भेजें।"
    return "Language set to English. Please send your message/photo/voice note."


def _detect_media_endpoint(content_type: str) -> str | None:
    ctype = (content_type or "").lower()
    if ctype.startswith("image/"):
        return "/api/analyze/image"
    if ctype.startswith("audio/") or ctype.startswith("video/"):
        return "/api/analyze/audio"
    if "pdf" in ctype or "msword" in ctype or "officedocument.wordprocessingml.document" in ctype:
        return "/api/analyze/document"
    return None


def _analyze_text(text: str) -> dict[str, Any]:
    response = requests.post(
        f"{BACKEND_BASE_URL}/api/analyze",
        json={"text": text, "source": "whatsapp"},
        timeout=40,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("Backend returned invalid JSON for text analysis.")
    return payload


def _analyze_media(media_url: str, content_type: str) -> dict[str, Any]:
    endpoint = _detect_media_endpoint(content_type)
    if not endpoint:
        raise ValueError(f"Unsupported media type: {content_type}")

    media_resp = requests.get(
        media_url,
        auth=(ACCOUNT_SID, AUTH_TOKEN),
        timeout=40,
    )
    media_resp.raise_for_status()

    filename = media_url.rstrip("/").split("/")[-1] or "upload.bin"
    if "." not in filename:
        guessed_ext = mimetypes.guess_extension((content_type or "").split(";")[0].strip().lower())
        if guessed_ext:
            filename = f"{filename}{guessed_ext}"
    files = {"file": (filename, media_resp.content, content_type or "application/octet-stream")}
    response = requests.post(
        f"{BACKEND_BASE_URL}{endpoint}",
        files=files,
        timeout=90,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("Backend returned invalid JSON for media analysis.")
    return payload


def _process_and_send_result(
    from_number: str,
    body_text: str,
    media_count: int,
    media_url: str,
    media_content_type: str,
) -> None:
    """Run analysis in background and send final WhatsApp response."""
    try:
        if media_count > 0 and media_url:
            result = _analyze_media(media_url, media_content_type)
        elif body_text.strip():
            result = _analyze_text(body_text)
        else:
            result = {"risk_score": 0.0, "reasons": ["Empty input"]}
    except Exception as exc:
        result = {"risk_score": 0.5, "reasons": [f"Analysis service unavailable: {exc}"]}

    language = _resolve_response_language(from_number, body_text, result)
    LAST_ANALYSIS_BY_USER[from_number] = result
    final_reply = _build_localized_response(result, language)
    client.messages.create(
        from_=FROM_NUMBER,
        to=from_number,
        body=final_reply,
    )


@app.post("/whatsapp")
async def whatsapp_webhook(
    request: Request,
    Body: str = Form(default=""),
    From: str = Form(default=""),
    NumMedia: str = Form(default="0"),
    MediaUrl0: str = Form(default=""),
    MediaContentType0: str = Form(default=""),
):
    url = str(request.url)
    signature = request.headers.get("X-Twilio-Signature", "")
    form_data = dict(await request.form())

    if not validator.validate(url, form_data, signature):
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")

    media_count = int(NumMedia or 0)
    language_command = _parse_language_command(Body)

    if language_command and media_count == 0:
        USER_LANGUAGE_PREFS[From] = language_command
        previous_result = LAST_ANALYSIS_BY_USER.get(From)
        if previous_result:
            reply = _build_localized_response(previous_result, language_command)
        else:
            reply = _language_change_reply(language_command)
        client.messages.create(
            from_=FROM_NUMBER,
            to=From,
            body=reply,
        )
        return Response(content="", media_type="text/xml")

    if not Body.strip() and media_count == 0:
        preferred = _normalize_language(USER_LANGUAGE_PREFS.get(From)) or "en"
        if preferred == "hi":
            reply = (
                "*ScamShield में स्वागत है*\n\n"
                "कृपया संदिग्ध जॉब मैसेज, फोटो, वॉइस नोट, या दस्तावेज़ भेजें।\n"
                "हम जांचकर बताएंगे कि यह सुरक्षित है या नहीं।"
            )
        else:
            reply = (
                "*Welcome to ScamShield*\n\n"
                "Please send a suspicious job message, photo, voice note, or document.\n"
                "We will check and tell you if it is safe."
            )
        client.messages.create(
            from_=FROM_NUMBER,
            to=From,
            body=reply,
        )
        return Response(content="", media_type="text/xml")

    interim_language = _normalize_language(USER_LANGUAGE_PREFS.get(From)) or _detect_language(Body)
    if interim_language == "hi":
        waiting_text = "आपका संदेश विश्लेषण हो रहा है, कृपया थोड़ा इंतज़ार करें..."
    else:
        waiting_text = "Analyzing your message, please wait..."

    client.messages.create(
        from_=FROM_NUMBER,
        to=From,
        body=waiting_text,
    )

    enqueue_job(
        {
            "from_number": From,
            "body_text": Body,
            "media_count": media_count,
            "media_url": MediaUrl0,
            "media_content_type": MediaContentType0,
        }
    )

    return JSONResponse(content={"status": "queued"})


@app.post("/sms")
async def sms_webhook(
    request: Request,
    Body: str = Form(default=""),
    From: str = Form(default=""),
):
    text = Body.replace("CHECK", "").strip()
    try:
        result = _analyze_text(text) if text else {"risk_score": 0}
    except Exception as exc:
        result = {"risk_score": 0.5, "reasons": [f"Analysis service unavailable: {exc}"]}

    score = _score_percent(result)
    if score >= 65:
        reply = f"High scam risk ({score}%). Payment mat bhejiye. ScamShield"
    elif score >= 35:
        reply = f"Suspicious message ({score}%). Verify before payment. ScamShield"
    else:
        reply = f"Low risk ({score}%), but always verify. ScamShield"

    client.messages.create(
        from_=os.getenv("TWILIO_PHONE_NUMBER", FROM_NUMBER),
        to=From,
        body=reply,
    )
    return Response(content="", media_type="text/xml")


@app.get("/")
def root():
    return {"status": "ScamShield messaging server is running"}
