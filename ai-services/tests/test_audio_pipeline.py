"""
tests/test_audio_pipeline.py
Run: pytest tests/test_audio_pipeline.py -v

Note: Tests that require Whisper model download are skipped
automatically if the model isn't available. This keeps CI fast.
"""

import sys
import os
import struct
import wave
import io
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from audio_pipeline import (
    process_audio,
    _load_audio,
    _language_code_to_name,
    SUPPORTED_AUDIO_FORMATS,
    MAX_AUDIO_SIZE_BYTES,
)


def make_silent_wav(duration_seconds=1, sample_rate=16000) -> bytes:
    """
    Create a valid silent WAV file in memory.
    Used for testing the loading/validation logic without needing Whisper.
    """
    n_frames = duration_seconds * sample_rate
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)          # mono
        wf.setsampwidth(2)          # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00\x00" * n_frames)
    return buf.getvalue()


# ── Tests: file loading ───────────────────────────────────────────────────────

class TestLoadAudio:

    def test_loads_valid_wav_bytes(self, tmp_path):
        """Valid WAV bytes should load successfully."""
        wav_bytes = make_silent_wav()
        result = _load_audio(wav_bytes)
        assert result["success"] is True
        assert "tmp_path" in result
        # Cleanup
        if os.path.exists(result["tmp_path"]):
            os.unlink(result["tmp_path"])

    def test_loads_valid_wav_file(self, tmp_path):
        """Valid WAV file path should load successfully."""
        wav_path = tmp_path / "test.wav"
        wav_path.write_bytes(make_silent_wav())
        result = _load_audio(str(wav_path))
        assert result["success"] is True
        if os.path.exists(result["tmp_path"]):
            os.unlink(result["tmp_path"])

    def test_rejects_missing_file(self):
        """Non-existent path should return success=False."""
        result = _load_audio("/tmp/does_not_exist_99999.wav")
        assert result["success"] is False
        assert "not found" in result["error"].lower()

    def test_rejects_unsupported_format(self, tmp_path):
        """Unsupported extension like .txt should be rejected."""
        bad_file = tmp_path / "audio.txt"
        bad_file.write_bytes(b"not audio")
        result = _load_audio(str(bad_file))
        assert result["success"] is False
        assert "unsupported" in result["error"].lower()

    def test_rejects_oversized_bytes(self):
        """Bytes over MAX_AUDIO_SIZE_BYTES should be rejected."""
        big = b"x" * (MAX_AUDIO_SIZE_BYTES + 1)
        result = _load_audio(big)
        assert result["success"] is False
        assert "too large" in result["error"].lower()

    def test_rejects_invalid_type(self):
        """Passing a dict should return a clear error."""
        result = _load_audio({"invalid": "type"})
        assert result["success"] is False

    def test_temp_file_has_correct_suffix_for_bytes(self):
        """Bytes input should create a temp file with .ogg suffix."""
        wav_bytes = make_silent_wav()
        result = _load_audio(wav_bytes)
        if result["success"]:
            assert result["tmp_path"].endswith(".ogg")
            os.unlink(result["tmp_path"])


# ── Tests: language code mapping ─────────────────────────────────────────────

class TestLanguageCodeToName:

    def test_hindi_code(self):
        assert _language_code_to_name("hi") == "Hindi"

    def test_english_code(self):
        assert _language_code_to_name("en") == "English"

    def test_bengali_code(self):
        assert _language_code_to_name("bn") == "Bengali"

    def test_unknown_code(self):
        result = _language_code_to_name("unknown")
        assert result == "Unknown"

    def test_unrecognized_code_returns_uppercase(self):
        """Codes not in the mapping should return the code uppercased."""
        result = _language_code_to_name("xy")
        assert result == "XY"


# ── Tests: full pipeline (skipped if Whisper unavailable) ─────────────────────

WHISPER_AVAILABLE = False
try:
    import whisper
    WHISPER_AVAILABLE = True
except ImportError:
    pass


@pytest.mark.skipif(not WHISPER_AVAILABLE, reason="Whisper not installed")
class TestProcessAudioWithWhisper:

    def test_silent_audio_returns_result(self, tmp_path):
        """
        Silent audio should complete without crashing.
        May return empty transcript — that's acceptable.
        """
        wav_path = tmp_path / "silent.wav"
        wav_path.write_bytes(make_silent_wav(duration_seconds=2))
        result = process_audio(str(wav_path))
        # Silent audio can legitimately fail or succeed with empty text
        assert "success" in result

    def test_result_has_required_fields_on_success(self, tmp_path):
        """
        On success, all required fields must be present.
        """
        wav_path = tmp_path / "silent.wav"
        wav_path.write_bytes(make_silent_wav(duration_seconds=2))
        result = process_audio(str(wav_path))
        if result.get("success"):
            required = ["transcript", "detected_language", "language_name",
                        "duration_seconds", "confidence", "urgency_detected"]
            for field in required:
                assert field in result, f"Missing field: {field}"

    def test_temp_file_cleaned_up_after_processing(self, tmp_path):
        """
        The pipeline should clean up its temp files even on failure.
        We verify by checking the tmp dir count before and after.
        """
        import tempfile
        import glob
        before = set(glob.glob(os.path.join(tempfile.gettempdir(), "scamshield_*")))

        wav_path = tmp_path / "silent.wav"
        wav_path.write_bytes(make_silent_wav())
        process_audio(str(wav_path))

        after = set(glob.glob(os.path.join(tempfile.gettempdir(), "scamshield_*")))
        # Any scamshield temp files created during this test should be gone
        new_files = after - before
        assert len(new_files) == 0, f"Temp files not cleaned up: {new_files}"