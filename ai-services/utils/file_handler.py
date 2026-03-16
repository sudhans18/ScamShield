"""
utils/file_handler.py
---------------------
Centralizes all file I/O and temp file management.

Keeps the pipeline files clean — they don't need to know where
files come from (path / bytes / FastAPI UploadFile), this handles it.

Used by: main_service.py, image_pipeline.py, audio_pipeline.py, doc_pipeline.py
"""

import os
import io
import shutil
import logging
import tempfile
from pathlib import Path
from typing import Union, Optional
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# Max sizes per input type
MAX_SIZES = {
    "image":    5  * 1024 * 1024,   # 5 MB
    "audio":    10 * 1024 * 1024,   # 10 MB
    "document": 10 * 1024 * 1024,   # 10 MB
    "generic":  20 * 1024 * 1024,   # 20 MB
}

# Allowed extensions per type
ALLOWED_EXTENSIONS = {
    "image":    {".jpg", ".jpeg", ".png", ".webp", ".bmp"},
    "audio":    {".ogg", ".mp3", ".wav", ".m4a", ".mp4", ".webm"},
    "document": {".pdf", ".docx", ".doc"},
}


@contextmanager
def temp_file(suffix: str = "", prefix: str = "scamshield_"):
    """
    Context manager that creates a temp file and cleans it up automatically.

    Usage:
        with temp_file(suffix=".jpg") as path:
            shutil.copy(source, path)
            result = process_image(path)
        # temp file is deleted here, even if an exception occurred
    """
    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(suffix=suffix, prefix=prefix)
        os.close(fd)
        logger.debug(f"file_handler: created temp file {tmp_path}")
        yield tmp_path
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
            logger.debug(f"file_handler: deleted temp file {tmp_path}")


def save_upload_to_temp(upload_file, input_type: str = "generic") -> dict:
    """
    Save a FastAPI UploadFile to a temp file for processing.
    Validates size and extension.

    Parameters
    ----------
    upload_file : FastAPI UploadFile
    input_type  : "image" | "audio" | "document" | "generic"

    Returns
    -------
    dict:
        success   (bool)
        tmp_path  (str)    — path to temp file (caller must delete)
        filename  (str)    — original filename
        extension (str)    — lowercase extension
        size_bytes (int)
        error     (str)    — only if success is False
    """
    filename = upload_file.filename or "upload"
    extension = Path(filename).suffix.lower()

    # Extension check
    allowed = ALLOWED_EXTENSIONS.get(input_type, set())
    if allowed and extension not in allowed:
        return {
            "success": False,
            "error": f"File type '{extension}' not allowed for {input_type}. Allowed: {allowed}",
        }

    # Read bytes
    try:
        content = upload_file.file.read()
    except Exception as e:
        return {"success": False, "error": f"Could not read uploaded file: {str(e)}"}

    # Size check
    max_size = MAX_SIZES.get(input_type, MAX_SIZES["generic"])
    if len(content) > max_size:
        mb = max_size // (1024 * 1024)
        return {
            "success": False,
            "error": f"File too large. Max size for {input_type}: {mb} MB",
        }

    # Write to temp file
    try:
        fd, tmp_path = tempfile.mkstemp(suffix=extension, prefix="scamshield_")
        with os.fdopen(fd, "wb") as f:
            f.write(content)
    except Exception as e:
        return {"success": False, "error": f"Could not write temp file: {str(e)}"}

    return {
        "success": True,
        "tmp_path": tmp_path,
        "filename": filename,
        "extension": extension,
        "size_bytes": len(content),
    }


def bytes_to_temp(data: bytes, suffix: str = ".bin") -> str:
    """
    Write raw bytes to a temp file. Returns the temp file path.
    Caller is responsible for deleting: os.unlink(path)
    """
    fd, path = tempfile.mkstemp(suffix=suffix, prefix="scamshield_")
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    return path


def validate_file_path(path: Union[str, Path], input_type: str = "generic") -> dict:
    """
    Validate a file path before processing.
    Returns dict with 'success' and 'error' if invalid.
    """
    path = Path(path)

    if not path.exists():
        return {"success": False, "error": f"File not found: {path}"}

    extension = path.suffix.lower()
    allowed = ALLOWED_EXTENSIONS.get(input_type, set())
    if allowed and extension not in allowed:
        return {
            "success": False,
            "error": f"Unsupported extension '{extension}'. Allowed: {allowed}",
        }

    max_size = MAX_SIZES.get(input_type, MAX_SIZES["generic"])
    if path.stat().st_size > max_size:
        mb = max_size // (1024 * 1024)
        return {"success": False, "error": f"File too large (max {mb} MB)"}

    return {"success": True, "path": str(path), "extension": extension}


def ensure_dir(directory: Union[str, Path]) -> Path:
    """Create a directory if it doesn't exist. Returns Path."""
    path = Path(directory)
    path.mkdir(parents=True, exist_ok=True)
    return path


# ── Quick test ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Test temp_file context manager
    with temp_file(suffix=".txt") as path:
        with open(path, "w") as f:
            f.write("test content")
        print(f"Temp file exists: {os.path.exists(path)} → path: {path}")
    print(f"Temp file deleted: {not os.path.exists(path)}")