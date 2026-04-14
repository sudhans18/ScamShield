from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_MODEL = None
_MODEL_ERROR: Exception | None = None
_MODEL_NAME = "tiny"


def _get_model():
    global _MODEL, _MODEL_ERROR
    if _MODEL is not None:
        return _MODEL
    if _MODEL_ERROR is not None:
        return None

    try:
        import whisper

        _MODEL = whisper.load_model(_MODEL_NAME)
    except Exception as exc:  # pragma: no cover
        _MODEL_ERROR = exc
        logger.warning("Whisper lazy-load failed: %s", exc)
        return None

    return _MODEL


def preload_whisper_model() -> bool:
    return _get_model() is not None


def transcribe_audio(file_path: str) -> str:
    try:
        model = _get_model()
        if model is None:
            return ""
        result: dict[str, Any] = model.transcribe(file_path, fp16=False, verbose=False)
        return str(result.get("text", "")).strip()
    except Exception as exc:  # pragma: no cover
        logger.warning("Whisper transcription failed: %s", exc)
        return ""


def transcribe_audio_with_meta(file_path: str) -> dict:
    try:
        model = _get_model()
        if model is None:
            return {"text": "", "language": "unknown", "segments": []}
        result: dict[str, Any] = model.transcribe(file_path, fp16=False, verbose=False)
        return {
            "text": str(result.get("text", "")).strip(),
            "language": result.get("language", "unknown"),
            "segments": result.get("segments", []),
        }
    except Exception as exc:  # pragma: no cover
        logger.warning("Whisper transcription failed: %s", exc)
        return {"text": "", "language": "unknown", "segments": []}

