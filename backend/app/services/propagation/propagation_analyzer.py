from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from typing import Any

from app.services.supabase_client import supabase


def _normalize_text(text: str) -> str:
    compact = re.sub(r"\s+", " ", (text or "").strip().lower())
    return compact


def _message_hash(text: str) -> str:
    normalized = _normalize_text(text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _safe_channels(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _compute_score(
    forwarded_many_times: bool,
    seen_count: int,
    channel_count: int,
    text_len: int,
) -> tuple[float, list[str]]:
    score = 0.0
    signals: list[str] = []

    if forwarded_many_times:
        score += 0.30
        signals.append("whatsapp_forwarded_many_times")
    if seen_count >= 3:
        score += 0.20
        signals.append("seen_in_3_or_more_messages")
    if seen_count >= 10:
        score += 0.20
        signals.append("high_repeat_volume")
    if channel_count >= 2:
        score += 0.15
        signals.append("cross_channel_spread")
    if text_len < 180:
        score += 0.15
        signals.append("short_broadcast_style_message")

    score = max(0.0, min(1.0, score))
    return round(score, 2), signals


def analyze_propagation(
    message_text: str,
    forwarded_many_times: bool = False,
    source_channel: str = "dashboard",
) -> dict:
    """
    Track fingerprint usage and return propagation behavior score.
    """
    normalized_text = _normalize_text(message_text)
    msg_hash = _message_hash(normalized_text)
    channel = (source_channel or "dashboard").strip().lower() or "dashboard"

    try:
        existing_rows = (
            supabase.table("message_fingerprints")
            .select("*")
            .eq("message_hash", msg_hash)
            .limit(1)
            .execute()
            .data
            or []
        )

        is_new_message = not existing_rows
        if is_new_message:
            payload = {
                "message_hash": msg_hash,
                "first_seen_at": datetime.now(UTC).isoformat(),
                "last_seen_at": datetime.now(UTC).isoformat(),
                "seen_count": 1,
                "forwarded_flag": bool(forwarded_many_times),
                "source_channels": [channel],
            }
            supabase.table("message_fingerprints").insert(payload).execute()
            seen_count = 1
            forwarded_flag = bool(forwarded_many_times)
            channels = [channel]
        else:
            row = existing_rows[0]
            current_seen = int(row.get("seen_count") or 0)
            current_forwarded = bool(row.get("forwarded_flag"))
            channels = _safe_channels(row.get("source_channels"))
            if channel not in channels:
                channels.append(channel)
            seen_count = current_seen + 1
            forwarded_flag = current_forwarded or bool(forwarded_many_times)

            update_payload = {
                "last_seen_at": datetime.now(UTC).isoformat(),
                "seen_count": seen_count,
                "forwarded_flag": forwarded_flag,
                "source_channels": channels,
            }
            supabase.table("message_fingerprints").update(update_payload).eq("message_hash", msg_hash).execute()
    except Exception:
        is_new_message = True
        seen_count = 1
        forwarded_flag = bool(forwarded_many_times)
        channels = [channel]

    propagation_score, signals = _compute_score(
        forwarded_many_times=forwarded_flag,
        seen_count=seen_count,
        channel_count=len(channels),
        text_len=len(normalized_text),
    )

    result = {
        "propagation_score": propagation_score,
        "signals": signals,
        "is_broadcast": propagation_score >= 0.5,
        "seen_count": seen_count,
        "is_new_message": is_new_message,
        "source_channels_count": len(channels),
        "message_hash": msg_hash,
        "forwarded_many_times": forwarded_flag,
    }
    return result
