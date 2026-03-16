from __future__ import annotations

import os
import mimetypes
from typing import Any

import requests
from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, Form, HTTPException, Request, Response
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


def _score_percent(result: dict[str, Any]) -> int:
    raw_score = result.get("risk_score", 0)
    if isinstance(raw_score, (int, float)):
        if raw_score > 1:
            return max(0, min(100, int(round(raw_score))))
        return max(0, min(100, int(round(raw_score * 100))))
    return 0


def _build_hindi_response(result: dict[str, Any]) -> str:
    score = _score_percent(result)
    reasons = result.get("reasons")
    if not isinstance(reasons, list):
        reasons = []
    reasons_text = "\n".join(f"* {str(reason)}" for reason in reasons[:3]) if reasons else "* Koi clear red flag nahi mila"

    if score >= 65:
        verdict = "KHATRA"
        advice = "Paise bilkul mat bhejiye. Number aur company verify kiye bina aage mat badhiye."
    elif score >= 35:
        verdict = "SANDIGDH"
        advice = "Abhi payment mat kijiye. Company registration aur number verify kijiye."
    else:
        verdict = "LOW RISK"
        advice = "Filhal risk kam lag raha hai, fir bhi details verify karke hi decision lijiye."

    return (
        "*NaukariSaathi - Job Safety Check*\n"
        "-------------------------------\n"
        f"Verdict: {verdict}\n"
        f"Risk Score: {score}%\n\n"
        f"Karan:\n{reasons_text}\n\n"
        f"Advice: {advice}\n\n"
        "_Hum kabhi paise, OTP, ya Aadhaar nahi maangte._"
    )


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

    final_reply = _build_hindi_response(result)
    client.messages.create(
        from_=FROM_NUMBER,
        to=from_number,
        body=final_reply,
    )


@app.post("/whatsapp")
async def whatsapp_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
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

    if not Body.strip() and media_count == 0:
        reply = (
            "*NaukariSaathi me swagat hai*\n\n"
            "Suspicious job message, photo, voice note, ya document bhejiye.\n"
            "Hum check karke batayenge safe hai ya nahi."
        )
        client.messages.create(
            from_=FROM_NUMBER,
            to=From,
            body=reply,
        )
        return Response(content="", media_type="text/xml")

    client.messages.create(
        from_=FROM_NUMBER,
        to=From,
        body="Analyzing message, please wait...",
    )

    background_tasks.add_task(
        _process_and_send_result,
        From,
        Body,
        media_count,
        MediaUrl0,
        MediaContentType0,
    )

    return Response(content="", media_type="text/xml")


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
        reply = f"High scam risk ({score}%). Payment mat bhejiye. NaukariSaathi"
    elif score >= 35:
        reply = f"Suspicious message ({score}%). Verify before payment. NaukariSaathi"
    else:
        reply = f"Low risk ({score}%), but always verify. NaukariSaathi"

    client.messages.create(
        from_=os.getenv("TWILIO_PHONE_NUMBER", FROM_NUMBER),
        to=From,
        body=reply,
    )
    return Response(content="", media_type="text/xml")


@app.get("/")
def root():
    return {"status": "NaukariSaathi messaging server is running"}
