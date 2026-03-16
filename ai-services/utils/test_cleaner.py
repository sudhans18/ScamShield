"""
utils/text_cleaner.py
---------------------
Cleans and normalizes raw text before it goes to the classifier.

Handles:
  - OCR artefacts (misread characters, noise)
  - Code-mixed Hindi/English (Hinglish)
  - Number normalization (Indian lakh/crore notation)
  - Whitespace and punctuation cleanup
  - Deduplication of repeated forwarded-message headers

Called by: image_pipeline.py, audio_pipeline.py, doc_pipeline.py
"""

import re
import unicodedata


def clean_text(text: str, source: str = "generic") -> str:
    """
    Full cleaning pipeline. Source hint lets us apply source-specific rules.

    Parameters
    ----------
    text   : str — raw text to clean
    source : str — "ocr" | "audio" | "whatsapp" | "generic"

    Returns
    -------
    str — cleaned text
    """
    if not text:
        return ""

    # 1. Unicode normalization (handles weird Unicode look-alike chars scammers use)
    text = unicodedata.normalize("NFKC", text)

    # 2. Remove WhatsApp forwarded message headers
    # (these appear when a message is forwarded many times)
    text = _remove_forward_headers(text)

    # 3. Source-specific cleanup
    if source == "ocr":
        text = _clean_ocr_artefacts(text)

    # 4. Normalize Indian number notation
    text = _normalize_indian_numbers(text)

    # 5. Normalize phone number formats
    text = _normalize_phones(text)

    # 6. Collapse whitespace
    text = _normalize_whitespace(text)

    return text.strip()


def _remove_forward_headers(text: str) -> str:
    """
    Remove WhatsApp "Forwarded" / "Forwarded many times" headers.
    These add noise and no information.
    """
    patterns = [
        r"Forwarded\s*\n",
        r"Forwarded many times\s*\n",
        r"🔁\s*Forwarded\s*\n",
        r"\[Forwarded from .+?\]\s*\n",
    ]
    for pat in patterns:
        text = re.sub(pat, "", text, flags=re.IGNORECASE)
    return text


def _clean_ocr_artefacts(text: str) -> str:
    """
    Fix common Tesseract misreads for scam message content.

    Common OCR errors on low-quality phone photos:
      '0' → 'O' (zero vs letter O) — only in number contexts
      'l' → '1' (lowercase L vs one) — only in number contexts
      '|' → 'I' (pipe vs capital I)
      Spurious '~', '_', random punctuation
    """
    # Fix pipe characters that should be I
    text = re.sub(r"(?<=[A-Za-z])\|(?=[A-Za-z])", "I", text)

    # Fix 'S' misread as '5' in words (Salary → 5alary)
    text = re.sub(r"\b5alary\b", "Salary", text, flags=re.IGNORECASE)
    text = re.sub(r"\b5eat\b", "Seat", text, flags=re.IGNORECASE)

    # Remove isolated noise characters on their own lines
    text = re.sub(r"^[|~_\-=]{1,3}$", "", text, flags=re.MULTILINE)

    return text


def _normalize_indian_numbers(text: str) -> str:
    """
    Normalize Indian lakh/crore notation to plain numbers.

    Examples:
      "1.5 lakh" → "150000"
      "1 crore"  → "10000000"
      "Rs.1,500" → "Rs.1500" (remove commas)

    This makes the NER fee/salary extraction more reliable.
    """
    # Remove commas in numbers: "1,500" → "1500"
    text = re.sub(r"(\d),(\d{3})\b", r"\1\2", text)

    # "X lakh" → X * 100000
    def expand_lakh(m):
        try:
            return str(int(float(m.group(1)) * 100_000))
        except ValueError:
            return m.group(0)

    text = re.sub(r"(\d+(?:\.\d+)?)\s*(?:lakh|lac)\b", expand_lakh, text, flags=re.IGNORECASE)

    # "X crore" → X * 10000000
    def expand_crore(m):
        try:
            return str(int(float(m.group(1)) * 10_000_000))
        except ValueError:
            return m.group(0)

    text = re.sub(r"(\d+(?:\.\d+)?)\s*crore\b", expand_crore, text, flags=re.IGNORECASE)

    return text


def _normalize_phones(text: str) -> str:
    """
    Standardize phone number formats so NER can reliably extract them.

    Handles:
      +91-9876543210  →  9876543210
      091 9876543210  →  9876543210
      98765 43210     →  9876543210 (spaced format)
    """
    # Remove country code prefix
    text = re.sub(r"(?:\+91|0091|91)[\s\-]?([6-9]\d{9})", r"\1", text)

    # Remove spaces within 10-digit numbers (98765 43210 → 9876543210)
    def remove_spaces_in_number(m):
        return m.group(0).replace(" ", "")

    text = re.sub(r"\b[6-9]\d{4}\s\d{5}\b", remove_spaces_in_number, text)

    return text


def _normalize_whitespace(text: str) -> str:
    """Collapse multiple spaces/tabs, normalize line endings."""
    # Multiple spaces → single space (but preserve newlines)
    text = re.sub(r"[ \t]+", " ", text)
    # Multiple blank lines → max 2
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def extract_hindi_text(text: str) -> str:
    """
    Extract only Devanagari (Hindi) text from a mixed text.
    Useful for feeding just the Hindi part to a Hindi-only model.
    """
    devanagari_pattern = re.compile(r"[\u0900-\u097F\s।॥]+")
    matches = devanagari_pattern.findall(text)
    return " ".join(m.strip() for m in matches if m.strip())


def extract_english_text(text: str) -> str:
    """Extract only ASCII/English text from mixed text."""
    ascii_pattern = re.compile(r"[A-Za-z0-9\s.,!?;:'\"-]+")
    matches = ascii_pattern.findall(text)
    return " ".join(m.strip() for m in matches if m.strip())


# ── Quick test ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    samples = [
        ("ocr", "Forwarded many times\nURGENT VACANCY- 5ecurity Guard Dubai\nSalary Rs 80,000 | Registration Fee Rs 8,000\nCall +91-9876543210 Limited 5eats"),
        ("whatsapp", "Gulf mein 1.5 lakh salary milega. Registration ke liye 8,000 bhejo. Jaldi karo!"),
        ("whatsapp", "Salary: 1 crore per annum. No fee."),
    ]

    for source, text in samples:
        print(f"\nSource: {source}")
        print(f"Before: {text}")
        print(f"After:  {clean_text(text, source)}")