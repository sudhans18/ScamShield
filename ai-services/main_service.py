"""
main_service.py
---------------
FastAPI application — the single entry point for all AI analysis.

Person 1 (backend) calls THIS. Nobody calls the individual
pipeline files directly in production. This file orchestrates:

  text input   → entity_extractor → scam_classifier → response
  image input  → image_pipeline   → entity_extractor → scam_classifier → response
  audio input  → audio_pipeline   → entity_extractor → scam_classifier → response
  doc input    → doc_pipeline     → entity_extractor → scam_classifier → response

Endpoints:
  POST /analyse/text       — raw WhatsApp message text
  POST /analyse/image      — uploaded image (JPG/PNG)
  POST /analyse/audio      — uploaded audio (.ogg/.mp3)
  POST /analyse/document   — uploaded document (PDF/DOCX)
  GET  /health             — health check for Person 1 to ping

Run with:
  uvicorn main_service:app --reload --port 8001

All responses follow the same schema (see AnalysisResult below).
"""

import os
import logging
import mimetypes
import tempfile
import shutil
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

print("AI service starting...")

# ── Our modules ───────────────────────────────────────────────────────────────
from entity_extractor import extract_entities
from image_pipeline import process_image
from audio_pipeline import preload_whisper_model, process_audio
from doc_pipeline import process_document
from models.scam_classifier import classify
from validator import validate_entities
from utils.safe_extract import first_or_none
from utils.text_cleaner import clean_text

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

# ── FastAPI app ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="ScamShield AI Service",
    description=(
        "AI analysis engine for NaukariSaathi / ScamShield. "
        "Classifies job messages, images, audio, and documents for fraud risk."
    ),
    version="0.1.0",
)

# Allow calls from the backend (Person 1) and browser extension (Person 5)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten this in production
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    """Preload heavy dependencies and emit startup logs."""
    preload_whisper_model()
    print("AI service ready")


# ── Request / Response schemas ────────────────────────────────────────────────

class TextRequest(BaseModel):
    """
    Body for POST /analyse/text
    Sent by Person 1's backend whenever a WhatsApp message arrives.
    """
    text: str
    source_channel: Optional[str] = "whatsapp"  # whatsapp | sms | telegram | browser_extension
    worker_district: Optional[str] = None        # e.g. "Deoria" — for heatmap tracking


class AnalysisResult(BaseModel):
    """
    Unified response schema returned by ALL /analyse/* endpoints.
    Every consumer (WhatsApp bot, browser extension, dashboard) gets this same shape.

    Also available as `scam_result` field with the exact format specified:
      { "text": ..., "entities": {...}, "scam_risk": "low/medium/high" }
    """
    success: bool

    # Core verdict
    risk_score: int            # 0–100 (100 = definite scam)
    is_scam: bool              # True if risk_score >= 65
    risk_label: str            # "SAFE" | "SUSPICIOUS" | "HIGH_RISK" | "SCAM"

    # Human-readable verdicts
    hindi_verdict: str
    english_summary: str

    # Evidence
    reasons: list[str]
    entities: dict

    # Structured output matching the project spec exactly
    scam_result: dict = {}     # {"text": str, "entities": {...}, "scam_risk": "low/medium/high"}

    # Metadata
    input_type: str
    source_channel: str
    processing_notes: list[str]
    db_checks: dict = {}


class ReportRequest(BaseModel):
    """Body for POST /report — worker confirms a scam after our warning."""
    phone: Optional[str] = None
    upi_id: Optional[str] = None
    message_text: Optional[str] = None
    reporter_type: str = "unverified_whatsapp"
    district: Optional[str] = None


# ── Thresholds ────────────────────────────────────────────────────────────────

RISK_THRESHOLDS = {
    "SAFE":      (0,  34),
    "SUSPICIOUS":(35, 64),
    "HIGH_RISK": (65, 84),
    "SCAM":      (85, 100),
}

HINDI_VERDICTS = {
    "SAFE":       "यह नौकरी सुरक्षित लगती है। फिर भी सावधान रहें।",
    "SUSPICIOUS": "⚠️ सावधान! यह संदेश संदिग्ध है। पैसे मत भेजें अभी।",
    "HIGH_RISK":  "🚨 खतरा! यह नौकरी नकली हो सकती है। पैसे बिल्कुल मत भेजें।",
    "SCAM":       "❌ यह फर्जी नौकरी है! पैसे मत दो। अपने परिवार को बताओ।",
}


# ── Placeholder classifier (until scam_classifier.py is built) ────────────────

def _placeholder_classify(text: str, entities: dict) -> dict:
    """
    Rule-based fallback classifier.
    Used until models/scam_classifier.py (Groq LLM) is integrated.

    Scoring:
      +40 if fees found
      +25 if urgency phrases found
      +15 if Gulf location + no company name
      +10 if URL found with no verified company
      +10 if only a phone number (no company info)
    """
    score = 0
    reasons = []

    if entities.get("has_fee"):
        score += 40
        fee_amounts = [f["normalized"] for f in entities.get("fees", [])]
        reasons.append(f"Upfront fee requested: ₹{', ₹'.join(str(f) for f in fee_amounts)}")

    if entities.get("has_urgency"):
        score += 25
        flags = entities.get("urgency_flags", [])
        first_flag = first_or_none(flags)
        if first_flag:
            reasons.append(f"Urgency language detected: '{first_flag}'")

    gulf_locations = [
        loc for loc in entities.get("locations", [])
        if loc in ["dubai", "uae", "qatar", "saudi", "saudi arabia",
                   "kuwait", "bahrain", "oman", "abu dhabi", "sharjah"]
    ]
    if gulf_locations and not entities.get("company_names"):
        score += 15
        first_gulf = first_or_none(gulf_locations)
        if first_gulf:
            reasons.append(f"Overseas job ({first_gulf}) with no verifiable company name")

    if entities.get("urls") and not entities.get("company_names"):
        score += 10
        reasons.append("Website URL found but no registered company name")

    if entities.get("phones") and not entities.get("company_names") and not entities.get("urls"):
        score += 10
        reasons.append("Only a phone number provided — no verifiable agency details")

    score = min(score, 100)

    return {
        "risk_score": score,
        "reasons": reasons[:3],  # Max 3 reasons
        "classifier_type": "rule_based",  # Will be "llm" once Groq is integrated
    }


# ── Shared analysis logic ─────────────────────────────────────────────────────

def _first_amount(items: list) -> int | None:
    if not items:
        return None
    first = items[0]
    if isinstance(first, dict):
        value = first.get("normalized")
        if isinstance(value, (int, float)):
            return int(value)
        return None
    if isinstance(first, (int, float)):
        return int(first)
    return None


def _fallback_response(input_type: str, source_channel: str, reason: str) -> AnalysisResult:
    """Return stable fallback response when analysis fails."""
    return AnalysisResult(
        success=False,
        risk_score=50,
        is_scam=False,
        risk_label="SUSPICIOUS",
        hindi_verdict="विवरण का विश्लेषण नहीं हो पाया, कृपया दोबारा प्रयास करें।",
        english_summary="AI service fallback",
        reasons=[reason or "AI service fallback"],
        entities={
            "phones": [],
            "salary": [],
            "fee": [],
            "company": "",
            "location": "",
            "upi": [],
        },
        scam_result={
            "text": "",
            "entities": {
                "salary": None,
                "registration_fee": None,
                "phone_number": None,
                "company": None,
                "location": None,
            },
            "scam_risk": "medium",
        },
        input_type=input_type,
        source_channel=source_channel,
        processing_notes=["fallback_response"],
        db_checks={},
    )


def _filename_with_content_suffix(filename: str | None, content_type: str | None, default_name: str) -> str:
    """Ensure uploaded files have a usable extension for pipeline format checks."""
    name = (filename or "").strip() or default_name
    if Path(name).suffix:
        return name

    guessed_ext = mimetypes.guess_extension((content_type or "").split(";")[0].strip().lower())
    if guessed_ext:
        return f"{name}{guessed_ext}"
    return name


def _build_result(
    text: str,
    input_type: str,
    source_channel: str,
    processing_notes: list,
    extra_metadata: dict | None = None,
) -> AnalysisResult:
    """
    Core analysis logic shared by ALL endpoints.
    Every input type (text / image / audio / document) ends up here.

    Pipeline:
      1. Clean text         — normalize numbers, remove OCR artefacts
      2. Extract entities   — phones, fees, salaries, urgency phrases
      3. Validate entities  — check DB, MCA registry, trust weights
      4. Classify           — Groq LLM → Gemini → rule-based fallback
      5. Merge scores       — LLM score + DB boost = final score
      6. Build response     — unified AnalysisResult schema
    """
    # Step 1: Clean text
    text = clean_text(text, source=input_type)

    if not text.strip():
        logger.warning("_build_result: empty text after cleaning")
        processing_notes.append("Text was empty after cleaning — no analysis possible")
        return AnalysisResult(
            success=False,
            risk_score=0,
            is_scam=False,
            risk_label="SAFE",
            hindi_verdict="संदेश खाली है। दोबारा भेजें।",
            english_summary="Empty text — no analysis performed.",
            reasons=["No text to analyse"],
            entities={},
            input_type=input_type,
            source_channel=source_channel,
            processing_notes=processing_notes,
        )

    # Step 2: Extract entities
    try:
        entities = extract_entities(text)
    except Exception as exc:
        logger.exception("Entity extraction failed")
        return _fallback_response(input_type, source_channel, f"Entity parsing error: {exc}")

    # Step 3: Validate entities against DB and government registries
    # This adds a score_boost if any phone/UPI is in the scam DB
    db_checks = {}
    score_boost = 0
    try:
        validation = validate_entities(entities)
        score_boost = validation.get("score_boost", 0)
        db_checks = validation
        if validation.get("validation_notes"):
            processing_notes.extend(validation["validation_notes"])
    except Exception as e:
        # Never crash the response because DB is down
        logger.warning(f"_build_result: validator failed (non-fatal) — {e}")
        processing_notes.append("Database check unavailable — verdict based on AI analysis only")

    # Step 4: LLM classification (Groq → Gemini → rule-based)
    try:
        classification = classify(
            text=text,
            entities=entities,
            context=f"Input type: {input_type}, Channel: {source_channel}",
        )
    except Exception as exc:
        logger.exception("Classifier failed")
        return _fallback_response(input_type, source_channel, f"Classification error: {exc}")

    # Step 5: Merge LLM score + DB boost
    try:
        base_score = int(float(classification.get("risk_score", 0)))
    except Exception:
        base_score = 0
    final_score = min(base_score + score_boost, 100)

    # Determine label from final score
    risk_label = "SAFE"
    for label, (low, high) in RISK_THRESHOLDS.items():
        if low <= final_score <= high:
            risk_label = label
            break

    # Use LLM-generated Hindi verdict if available, else use our template
    hindi_verdict = classification.get("hindi_verdict") or HINDI_VERDICTS[risk_label]
    english_summary = classification.get("english_summary") or (
        f"{risk_label} — risk score {final_score}/100. "
        f"{'Fee detected. ' if entities.get('has_fee') else ''}"
        f"{'Urgency language detected. ' if entities.get('has_urgency') else ''}"
        f"Classifier: {classification.get('classifier_type', 'unknown')}"
    )

    # Log for monitoring
    logger.info(
        f"_build_result: channel={source_channel} type={input_type} "
        f"base={base_score} boost={score_boost} final={final_score} "
        f"label={risk_label} classifier={classification.get('classifier_type')}"
    )

    # Step 6: Assemble result
    # Build the exact ScamResult format from the project spec
    phone_number = first_or_none(entities.get("phones"))
    company_name = first_or_none(entities.get("company_names"))
    location_name = first_or_none(entities.get("locations"))
    print("Extracted entities:", entities)
    print("Risk score:", final_score)

    scam_result = {
        "text": text,
        "entities": {
            "salary":            _first_amount(entities.get("salaries", [])),
            "registration_fee":  _first_amount(entities.get("fees", [])),
            "phone_number":      phone_number,
            "company":           company_name,
            "location":          location_name,
        },
        "scam_risk": (
            "high"   if final_score >= 65 else
            "medium" if final_score >= 35 else
            "low"
        ),
    }

    return AnalysisResult(
        success=True,
        risk_score=final_score,
        is_scam=final_score >= 65,
        risk_label=risk_label,
        hindi_verdict=hindi_verdict,
        english_summary=english_summary,
        reasons=classification.get("reasons", ["No specific flags detected"]),
        entities=entities,
        scam_result=scam_result,
        input_type=input_type,
        source_channel=source_channel,
        processing_notes=processing_notes,
        db_checks=db_checks,
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
def health_check():
    """Person 1 pings this to verify the AI service is up."""
    return {"status": "ok", "service": "ScamShield AI", "version": "0.1.0"}


@app.post("/analyse/text", response_model=AnalysisResult)
def analyse_text(request: TextRequest):
    """
    Analyse a raw text message (WhatsApp, SMS, Telegram).

    Person 1 calls this when a worker forwards a job message to the WhatsApp bot.
    Person 5 (browser extension) calls this for text scraped from Facebook/OLX.

    Example call:
        POST /analyse/text
        {
            "text": "URGENT: Security guard Dubai. Salary 80000. Fee 8000. Call 9876543210.",
            "source_channel": "whatsapp",
            "worker_district": "Deoria"
        }
    """
    if not request.text or not request.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    if len(request.text) > 10_000:
        raise HTTPException(status_code=400, detail="Text too long (max 10,000 chars)")

    logger.info(
        f"analyse/text | channel={request.source_channel} | "
        f"district={request.worker_district} | len={len(request.text)}"
    )

    try:
        return _build_result(
            text=request.text,
            input_type="text",
            source_channel=request.source_channel or "unknown",
            processing_notes=[],
        )
    except Exception as exc:
        logger.exception("analyse/text failed")
        return _fallback_response("text", request.source_channel or "unknown", str(exc))


@app.post("/analyse/image", response_model=AnalysisResult)
async def analyse_image(file: UploadFile = File(...)):
    """
    Analyse an image (photo of job ad, offer letter, pamphlet).

    Person 3 (WhatsApp bot) calls this when a worker sends a photo.
    Supported: JPG, JPEG, PNG, WEBP, BMP (max 5 MB).

    Example call (multipart/form-data):
        POST /analyse/image
        file: <image file>
    """
    processing_notes = []

    # Save uploaded file to a temp location for processing
    safe_name = _filename_with_content_suffix(file.filename, file.content_type, "upload.jpg")
    suffix = Path(safe_name).suffix.lower() or ".jpg"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    try:
        # Run image pipeline (OCR)
        image_result = process_image(tmp_path)

        if not image_result["success"]:
            return _fallback_response("image", "whatsapp", "Image processing failed")

        extracted_text = image_result["extracted_text"]

        # Add quality warning if image was poor
        quality = image_result.get("image_quality", "good")
        if quality in ("low", "very_low"):
            processing_notes.append(
                f"Image quality is {quality} — OCR accuracy may be reduced. "
                "Ask the worker to send a clearer photo."
            )

        lang_hint = image_result.get("language_hint", "english")
        processing_notes.append(f"Detected language: {lang_hint}")

        logger.info(
            f"analyse/image | quality={quality} | lang={lang_hint} | "
            f"chars={len(extracted_text)}"
        )

        return _build_result(
            text=extracted_text,
            input_type="image",
            source_channel="whatsapp",
            processing_notes=processing_notes,
        )
    except Exception as exc:
        logger.exception("analyse/image failed")
        return _fallback_response("image", "whatsapp", str(exc))

    finally:
        # Always clean up the temp file
        os.unlink(tmp_path)


@app.post("/analyse/audio", response_model=AnalysisResult)
async def analyse_audio(file: UploadFile = File(...)):
    """
    Analyse a voice note (.ogg from WhatsApp, .mp3, .wav).

    Scammers increasingly use voice notes to appear more credible.
    This endpoint transcribes the audio with Whisper, then runs
    the same classifier as /analyse/text.

    Supported formats: .ogg .mp3 .wav .m4a .webm (max 10 MB)

    Note: First call takes ~10–30s to download the Whisper model weights.
    Subsequent calls are fast (model is cached in memory).
    """
    processing_notes = []
    logger.info(f"analyse/audio | filename={file.filename}")

    # Save upload to temp file
    safe_name = _filename_with_content_suffix(file.filename, file.content_type, "audio.ogg")
    suffix = Path(safe_name).suffix.lower() or ".ogg"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    try:
        audio_result = process_audio(tmp_path)

        if not audio_result["success"]:
            return _fallback_response("audio", "whatsapp", "Audio processing failed")

        transcript = audio_result["transcript"]
        lang = audio_result.get("language_name", "Unknown")
        duration = audio_result.get("duration_seconds", 0)

        processing_notes.append(f"Voice note transcribed | Language: {lang} | Duration: {duration:.1f}s")

        if audio_result.get("urgency_detected"):
            processing_notes.append("Urgency keywords detected in voice note transcript")

        logger.info(
            f"analyse/audio | lang={lang} | duration={duration:.1f}s | "
            f"chars={len(transcript)}"
        )

        return _build_result(
            text=transcript,
            input_type="audio",
            source_channel="whatsapp",
            processing_notes=processing_notes,
        )
    except Exception as exc:
        logger.exception("analyse/audio failed")
        return _fallback_response("audio", "whatsapp", str(exc))

    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


@app.post("/analyse/document", response_model=AnalysisResult)
async def analyse_document(file: UploadFile = File(...)):
    """
    Analyse a document (PDF offer letter, DOCX contract).

    Runs the Document Forgery Detector:
    - Extracts text from PDF or DOCX
    - Identifies company name, GST number, CIN
    - Cross-checks against MCA21 registry
    - Detects typosquatting (e.g. "Tata Projcts" vs "Tata Projects")
    - Checks for fee requests inside offer letters (red flag)

    Supported: .pdf .docx (max 10 MB)
    """
    processing_notes = []
    logger.info(f"analyse/document | filename={file.filename}")

    filename = _filename_with_content_suffix(file.filename, file.content_type, "document.pdf")
    suffix = Path(filename).suffix.lower() or ".pdf"

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    try:
        doc_result = process_document(tmp_path, filename=filename)

        if not doc_result["success"]:
            return _fallback_response("document", "whatsapp", "Document processing failed")

        extracted_text = doc_result["extracted_text"]
        forgery_risk = doc_result.get("forgery_risk", "unknown")
        mca_verified = doc_result.get("mca_verified", False)
        company = doc_result.get("company_name")

        # Surface forgery findings as processing notes so they appear in the response
        if doc_result.get("forgery_reasons"):
            processing_notes.extend(doc_result["forgery_reasons"])

        if company:
            mca_status = "verified in MCA registry" if mca_verified else "NOT found in MCA registry"
            processing_notes.append(f"Company '{company}' — {mca_status}")

        processing_notes.append(
            f"Document forgery assessment: {forgery_risk.upper()} risk "
            f"(format: {doc_result.get('doc_format', 'unknown').upper()})"
        )

        logger.info(
            f"analyse/document | format={doc_result.get('doc_format')} | "
            f"company={company} | mca={mca_verified} | forgery={forgery_risk}"
        )

        return _build_result(
            text=extracted_text,
            input_type="document",
            source_channel="whatsapp",
            processing_notes=processing_notes,
        )
    except Exception as exc:
        logger.exception("analyse/document failed")
        return _fallback_response("document", "whatsapp", str(exc))

    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


# ── Dev runner ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main_service:app", host="0.0.0.0", port=8001, reload=True)


