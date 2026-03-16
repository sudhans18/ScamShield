import logging

logger = logging.getLogger(__name__)

print("Loading Whisper model...")

_MODEL = None
_MODEL_ERROR = None

try:
    import whisper

    _MODEL = whisper.load_model("tiny")
    print("Whisper model loaded successfully")
except Exception as exc:  # pragma: no cover
    _MODEL_ERROR = exc
    logger.warning("Whisper preload failed: %s", exc)


def transcribe_audio(file_path: str) -> str:
    """Return transcribed text from audio file. Never raises."""
    try:
        if _MODEL is None:
            return ""
        result = _MODEL.transcribe(file_path, fp16=False, verbose=False)
        return str(result.get("text", "")).strip()
    except Exception as exc:  # pragma: no cover
        print("Whisper transcription failed:", exc)
        return ""


def transcribe_audio_with_meta(file_path: str) -> dict:
    """Return transcript and metadata. Never raises."""
    try:
        if _MODEL is None:
            return {"text": "", "language": "unknown", "segments": []}
        result = _MODEL.transcribe(file_path, fp16=False, verbose=False)
        return {
            "text": str(result.get("text", "")).strip(),
            "language": result.get("language", "unknown"),
            "segments": result.get("segments", []),
        }
    except Exception as exc:  # pragma: no cover
        print("Whisper transcription failed:", exc)
        return {"text": "", "language": "unknown", "segments": []}
