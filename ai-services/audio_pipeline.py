"""
audio_pipeline.py
-----------------
Transcribes voice notes sent by workers or scammers via WhatsApp.

Scammers increasingly send voice notes from fake "HR managers"
to appear more credible. This pipeline catches that.

Workflow:
  audio file (.ogg / .mp3 / .wav) → validate → Whisper transcription
  → detect language → return transcript text

The transcript then goes through entity_extractor + scam_classifier
in main_service.py exactly like a text message would.

Whisper runs LOCALLY on the server — zero API cost.
Model sizes: "tiny" (fastest) → "base" → "small" → "medium"
For Hindi accuracy, "small" is the minimum recommended.

Called by: main_service.py
Returns:   dict with transcript text + metadata
"""

import os
import io
import logging
import tempfile
import shutil
from pathlib import Path
from typing import Union

from voice.whisper_transcriber import transcribe_audio_with_meta

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
SUPPORTED_AUDIO_FORMATS = {".ogg", ".mp3", ".wav", ".m4a", ".mp4", ".webm"}
MAX_AUDIO_SIZE_BYTES = 10 * 1024 * 1024   # 10 MB — voice notes are tiny, 10MB is generous
MAX_DURATION_SECONDS = 300                 # 5 minutes max — scam voice notes are short

# Whisper model to use.
# "base"  → fast, decent Hindi. Good for hackathon demo.
# "small" → better Hindi accuracy, ~2x slower. Recommended for production.
# Change this one line to upgrade.
WHISPER_MODEL_SIZE = "tiny"

# Languages Whisper will try to detect/transcribe.
# None = auto-detect (slower). "hi" = force Hindi. "en" = force English.
# For our use case, auto-detect is best — messages can be Hindi, Bhojpuri,
# Odia, Gujarati, or code-mixed.
WHISPER_LANGUAGE = None  # auto-detect

# ── Lazy model loading ────────────────────────────────────────────────────────
# We load Whisper only when first needed — not at import time.
# This keeps startup fast and avoids errors if whisper isn't installed.
_whisper_model = None


def _get_whisper_model():
    """
    Load Whisper model once and cache it.
    First call takes ~5–30 seconds to download weights.
    All subsequent calls are instant.
    """
    global _whisper_model
    if _whisper_model is None:
        try:
            import whisper
            logger.info(f"audio_pipeline: loading Whisper model '{WHISPER_MODEL_SIZE}'...")
            _whisper_model = whisper.load_model(WHISPER_MODEL_SIZE)
            logger.info("audio_pipeline: Whisper model loaded successfully")
        except ImportError:
            logger.error(
                "audio_pipeline: whisper not installed. Run: pip install openai-whisper"
            )
            raise
    return _whisper_model


def preload_whisper_model() -> bool:
    """Preload Whisper model during app startup. Never raises."""
    try:
        # Model is preloaded on import in voice.whisper_transcriber.
        return True
    except Exception as exc:  # pragma: no cover
        logger.warning("audio_pipeline: Whisper preload failed - %s", exc)
        return False


# ── Main pipeline function ────────────────────────────────────────────────────

def process_audio(source: Union[str, bytes, Path]) -> dict:
    """
    Full audio → transcript pipeline.

    Parameters
    ----------
    source : str | bytes | Path
        File path or raw audio bytes (e.g. from Twilio webhook).

    Returns
    -------
    dict with keys:
        success          (bool)
        transcript       (str)    — full transcribed text
        detected_language (str)   — e.g. "hi", "en", "bn"
        language_name    (str)    — e.g. "Hindi", "English", "Bengali"
        duration_seconds (float)  — audio length
        confidence       (float)  — Whisper's average log probability (rough quality signal)
        urgency_detected (bool)   — quick flag: did transcript contain urgency words?
        error            (str)    — only if success is False
    """
    logger.info("audio_pipeline: starting process_audio")

    # Step 1 — Load audio to a temp file
    load_result = _load_audio(source)
    if not load_result["success"]:
        return load_result

    tmp_path = load_result["tmp_path"]

    try:
        # Step 2 — Transcribe with Whisper
        transcription = _transcribe(tmp_path)
        if not transcription["success"]:
            return transcription

        transcript = transcription["transcript"]
        detected_lang = transcription["detected_language"]
        duration = transcription["duration_seconds"]
        confidence = transcription["confidence"]

        # Step 3 — Quick urgency check on transcript
        urgency_keywords = [
            "urgent", "fee", "registration", "limited", "today",
            "jaldi", "turant", "abhi", "aaj", "kal tak",
        ]
        urgency_detected = any(kw in transcript.lower() for kw in urgency_keywords)

        if not transcript.strip():
            return {
                "success": False,
                "error": (
                    "Transcription returned empty text. "
                    "Voice note may be too short, silent, or in an unsupported language."
                ),
            }

        logger.info(
            f"audio_pipeline: transcribed {len(transcript)} chars | "
            f"lang={detected_lang} | duration={duration:.1f}s"
        )

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
        # Always clean up temp file
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
            logger.info("audio_pipeline: temp file cleaned up")


# ── Internal helpers ──────────────────────────────────────────────────────────

def _load_audio(source: Union[str, bytes, Path]) -> dict:
    """
    Accept a file path or raw bytes.
    Copies to a temp file so Whisper can read it by path.
    Returns dict with 'success', 'tmp_path'.
    """
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

            # Copy to temp to ensure a clean path for Whisper
            suffix = path.suffix
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                shutil.copy2(path, tmp.name)
                return {"success": True, "tmp_path": tmp.name}

        elif isinstance(source, (bytes, bytearray)):
            if len(source) > MAX_AUDIO_SIZE_BYTES:
                return {"success": False, "error": "Audio bytes too large (max 10 MB)."}

            # We don't know the format from bytes — assume .ogg (WhatsApp default)
            with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as tmp:
                tmp.write(source)
                return {"success": True, "tmp_path": tmp.name}

        else:
            return {
                "success": False,
                "error": f"Invalid source type: {type(source)}. Pass a file path or bytes.",
            }

    except Exception as e:
        logger.error(f"audio_pipeline: _load_audio failed — {e}")
        return {"success": False, "error": f"Could not load audio: {str(e)}"}


def _transcribe(audio_path: str) -> dict:
    """
    Run Whisper on the audio file.
    Returns transcript + metadata.
    """
    try:
        result = transcribe_audio_with_meta(audio_path)
        transcript = str(result.get("text", "")).strip()
        detected_lang = str(result.get("language", "unknown"))

        # Calculate average log probability as a rough confidence signal
        segments = result.get("segments", [])
        if isinstance(segments, list) and segments:
            avg_logprob = sum(float(s.get("avg_logprob", 0)) for s in segments) / len(segments)
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

    except Exception as e:
        logger.error(f"audio_pipeline: Whisper transcription failed - {e}")
        return {"success": False, "error": f"Transcription failed: {str(e)}"}


def _language_code_to_name(code: str) -> str:
    """Map ISO 639-1 codes to display names for common Indian languages."""
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


# ── Quick manual test ──────────────────────────────────────────────────────────
# Run: python audio_pipeline.py
# Needs a test_audio.mp3 in sample_inputs/ OR will show setup instructions.

if __name__ == "__main__":
    import json
    from pathlib import Path

    test_path = Path(__file__).parent / "sample_inputs" / "test_audio1.mp3"

    if not test_path.exists():
        print(f"No test audio found at {test_path}")
        print(
            "\nTo test this pipeline:\n"
            "1. Record a short voice note in Hindi using your phone\n"
            "2. Save it as sample_inputs/test_audio.mp3\n"
            "3. Run this script again\n\n"
            "OR: Download a sample Hindi audio file from:\n"
            "  https://upload.wikimedia.org/wikipedia/commons/6/6c/"
            "Hindi_language.ogg\n\n"
            "Whisper supports: .ogg .mp3 .wav .m4a .webm"
        )
    else:
        print(f"Transcribing: {test_path}")
        result = process_audio(test_path)
        print(json.dumps(result, indent=2, ensure_ascii=False))
