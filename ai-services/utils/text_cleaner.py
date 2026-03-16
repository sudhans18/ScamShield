import re
import unicodedata


def clean_text(text: str, source: str = "generic") -> str:
    if not text:
        return ""

    text = unicodedata.normalize("NFKC", text)
    text = _remove_forward_headers(text)

    if source == "ocr":
        text = _clean_ocr_artefacts(text)

    text = _normalize_indian_numbers(text)
    text = _normalize_phones(text)
    text = _normalize_whitespace(text)

    return text.strip()


def _remove_forward_headers(text: str) -> str:
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
    text = re.sub(r"(?<=[A-Za-z])\|(?=[A-Za-z])", "I", text)
    text = re.sub(r"\b5alary\b", "Salary", text, flags=re.IGNORECASE)
    text = re.sub(r"\b5eat\b", "Seat", text, flags=re.IGNORECASE)
    text = re.sub(r"^[|~_\-=]{1,3}$", "", text, flags=re.MULTILINE)
    return text


def _normalize_indian_numbers(text: str) -> str:
    text = re.sub(r"(\d),(\d{3})\b", r"\1\2", text)

    def expand_lakh(match: re.Match[str]) -> str:
        try:
            return str(int(float(match.group(1)) * 100_000))
        except ValueError:
            return match.group(0)

    text = re.sub(r"(\d+(?:\.\d+)?)\s*(?:lakh|lac)\b", expand_lakh, text, flags=re.IGNORECASE)

    def expand_crore(match: re.Match[str]) -> str:
        try:
            return str(int(float(match.group(1)) * 10_000_000))
        except ValueError:
            return match.group(0)

    text = re.sub(r"(\d+(?:\.\d+)?)\s*crore\b", expand_crore, text, flags=re.IGNORECASE)

    return text


def _normalize_phones(text: str) -> str:
    text = re.sub(r"(?:\+91|0091|91)[\s\-]?([6-9]\d{9})", r"\1", text)

    def remove_spaces_in_number(match: re.Match[str]) -> str:
        return match.group(0).replace(" ", "")

    text = re.sub(r"\b[6-9]\d{4}\s\d{5}\b", remove_spaces_in_number, text)
    return text


def _normalize_whitespace(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def extract_hindi_text(text: str) -> str:
    devanagari_pattern = re.compile(r"[\u0900-\u097F\s।॥]+")
    matches = devanagari_pattern.findall(text)
    return " ".join(segment.strip() for segment in matches if segment.strip())


def extract_english_text(text: str) -> str:
    ascii_pattern = re.compile(r"[A-Za-z0-9\s.,!?;:'\"-]+")
    matches = ascii_pattern.findall(text)
    return " ".join(segment.strip() for segment in matches if segment.strip())
