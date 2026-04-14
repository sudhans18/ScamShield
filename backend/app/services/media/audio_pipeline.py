"""
Audio transcription pipeline for ScamShield.
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Union

from app.services.media.whisper_transcriber import (
    preload_whisper_model as _preload_whisper_model,
    transcribe_audio_with_meta,
)

logger = logging.getLogger(__name__)


SUPPORTED_AUDIO_FORMATS = {".ogg", ".mp3", ".wav", ".m4a", ".mp4", ".webm"}
MAX_AUDIO_SIZE_BYTES = 10 * 1024 * 1024
MAX_DURATION_SECONDS = 300


def preload_whisper_model() -> bool:
    """Optional startup warm-up hook. Never raises."""
    try:
        return _preload_whisper_model()
    except Exception as exc:  # pragma: no cover
        logger.warning("audio_pipeline: Whisper preload failed - %s", exc)
        return False


def process_audio(source: Union[str, bytes, Path]) -> dict:
    """
    Full audio -> transcript pipeline.
    """
    logger.info("audio_pipeline: starting process_audio")
    load_result = _load_audio(source)
    if not load_result["success"]:
        return load_result

    tmp_path = load_result["tmp_path"]
    try:
        transcription = _transcribe(tmp_path)
        if not transcription["success"]:
            return transcription

        transcript = transcription["transcript"]
        detected_lang = transcription["detected_language"]
        duration = transcription["duration_seconds"]
        confidence = transcription["confidence"]

        urgency_keywords = [
            "urgent",
            "fee",
            "registration",
            "limited",
            "today",
            "jaldi",
            "turant",
            "abhi",
            "aaj",
            "kal tak",
        ]
        urgency_detected = any(keyword in transcript.lower() for keyword in urgency_keywords)

        if not transcript.strip():
            return {
                "success": False,
                "error": (
                    "Transcription returned empty text. "
                    "Voice note may be too short, silent, or in an unsupported language."
                ),
            }

        if duration > MAX_DURATION_SECONDS:
            logger.info("audio_pipeline: duration %.1fs exceeds soft threshold", duration)

        return {
            "success": True,
            "transcript": transcript,
            "detected_language": detected_lang,
            "language_name": _language_code_to_name(detected_lang),
            "duration_seconds": duration,
            "confidence": round(confidence, 3),
            "urgency_detected": urgency_detected,
            "char_count": len(transcript),
        }
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def _load_audio(source: Union[str, bytes, Path]) -> dict:
    try:
        if isinstance(source, (str, Path)):
            path = Path(source)
            if not path.exists():
                return {"success": False, "error": f"Audio file not found: {path}"}

            if path.suffix.lower() not in SUPPORTED_AUDIO_FORMATS:
                return {
                    "success": False,
                    "error": (
                        f"Unsupported audio format '{path.suffix}'. "
                        f"Supported: {SUPPORTED_AUDIO_FORMATS}"
                    ),
                }

            if path.stat().st_size > MAX_AUDIO_SIZE_BYTES:
                return {"success": False, "error": "Audio file too large (max 10 MB)."}

            with tempfile.NamedTemporaryFile(delete=False, suffix=path.suffix) as tmp:
                shutil.copy2(path, tmp.name)
                return {"success": True, "tmp_path": tmp.name}

        if isinstance(source, (bytes, bytearray)):
            if len(source) > MAX_AUDIO_SIZE_BYTES:
                return {"success": False, "error": "Audio bytes too large (max 10 MB)."}

            with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as tmp:
                tmp.write(source)
                return {"success": True, "tmp_path": tmp.name}

        return {
            "success": False,
            "error": f"Invalid source type: {type(source)}. Pass a file path or bytes.",
        }
    except Exception as exc:
        logger.error("audio_pipeline: _load_audio failed - %s", exc)
        return {"success": False, "error": f"Could not load audio: {exc}"}


def _transcribe(audio_path: str) -> dict:
    try:
        result = transcribe_audio_with_meta(audio_path)
        transcript = str(result.get("text", "")).strip()
        detected_lang = str(result.get("language", "unknown"))
        segments = result.get("segments", [])

        if isinstance(segments, list) and segments:
            avg_logprob = sum(float(segment.get("avg_logprob", 0)) for segment in segments) / len(segments)
            duration = float(segments[-1].get("end", 0) or 0)
        else:
            avg_logprob = 0.0
            duration = 0.0

        return {
            "success": True,
            "transcript": transcript,
            "detected_language": detected_lang,
            "duration_seconds": duration,
            "confidence": avg_logprob,
        }
    except Exception as exc:
        logger.error("audio_pipeline: Whisper transcription failed - %s", exc)
        return {"success": False, "error": f"Transcription failed: {exc}"}


def _language_code_to_name(code: str) -> str:
    mapping = {
        "hi": "Hindi",
        "en": "English",
        "bn": "Bengali",
        "te": "Telugu",
        "ta": "Tamil",
        "gu": "Gujarati",
        "mr": "Marathi",
        "or": "Odia",
        "pa": "Punjabi",
        "ur": "Urdu",
        "ml": "Malayalam",
        "kn": "Kannada",
        "unknown": "Unknown",
    }
    return mapping.get(code, code.upper())

