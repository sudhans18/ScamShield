from __future__ import annotations

import json
import os
import re
from typing import Any

import requests

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODEL = "llama3-70b-8192"

SYSTEM_PROMPT = (
    "You are an expert in detecting labour job scams targeting migrant workers in India."
)

USER_PROMPT_TEMPLATE = """Analyze the following message and determine if it is a scam job offer.

Return JSON with:

risk_score (0-1)
reason
signals detected

Message:
{message}"""


def _extract_json_from_text(content: str) -> dict[str, Any]:
    """Extract the first JSON object from model text output."""
    content = content.strip()

    # Fast path: content is plain JSON.
    try:
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    # Handle markdown fenced JSON blocks.
    fenced_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, flags=re.DOTALL | re.IGNORECASE)
    if fenced_match:
        return json.loads(fenced_match.group(1))

    # Fallback: first curly-brace JSON object in text.
    object_match = re.search(r"(\{.*\})", content, flags=re.DOTALL)
    if object_match:
        return json.loads(object_match.group(1))

    raise ValueError("LLM response did not contain valid JSON.")


def _normalize_output(parsed: dict[str, Any]) -> dict[str, Any]:
    """Normalize key variants into a stable response schema."""
    risk_score = parsed.get("risk_score")
    reason = parsed.get("reason")
    signals = (
        parsed.get("signals")
        if parsed.get("signals") is not None
        else parsed.get("signals_detected")
    )

    if isinstance(signals, str):
        signals = [signals]
    if not isinstance(signals, list):
        signals = []

    # Keep risk_score in range [0, 1] when possible.
    if isinstance(risk_score, (int, float)):
        risk_score = max(0.0, min(1.0, float(risk_score)))

    return {
        "risk_score": risk_score,
        "reason": reason,
        "signals": signals,
    }


def classify_with_llm(text: str) -> dict[str, Any]:
    """Classify job message scam risk with Groq LLaMA 3 and return parsed JSON."""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY environment variable is not set.")

    model = os.getenv("GROQ_MODEL", DEFAULT_MODEL)
    user_prompt = USER_PROMPT_TEMPLATE.format(message=text)

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.1,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    response = requests.post(
        GROQ_API_URL,
        headers=headers,
        json=payload,
        timeout=30,
    )
    response.raise_for_status()

    data = response.json()
    content = data["choices"][0]["message"]["content"]
    parsed = _extract_json_from_text(content)
    return _normalize_output(parsed)
