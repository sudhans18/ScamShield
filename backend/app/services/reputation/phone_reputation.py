from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from anyio import to_thread

from app.services.supabase_client import supabase


def _resolve_reputation(trust_score: float) -> str:
    if trust_score < 1:
        return "UNKNOWN"
    if trust_score <= 3:
        return "SUSPICIOUS"
    return "CONFIRMED_SCAM"


def _calculate_from_reports(phone: str, reports: list[dict[str, Any]]) -> dict[str, Any]:
    trust_score = round(sum(float(report.get("trust_weight") or 0) for report in reports), 2)
    report_count = len(reports)

    return {
        "phone": phone,
        "report_count": report_count,
        "trust_score": trust_score,
        "reputation": _resolve_reputation(trust_score),
    }


def _fetch_reports(phone: str) -> list[dict[str, Any]]:
    result = (
        supabase.table("scam_reports")
        .select("trust_weight")
        .eq("scam_phone", phone)
        .execute()
    )
    return result.data or []


def check_phone_reputation(phone: str) -> dict[str, Any]:
    """Synchronous reputation lookup (matches existing sync pipeline)."""
    reports = _fetch_reports(phone)
    return _calculate_from_reports(phone=phone, reports=reports)


def upsert_phone_reputation(phone: str) -> dict[str, Any]:
    reputation = check_phone_reputation(phone)
    payload = {
        "phone_number": phone,
        "report_count": reputation["report_count"],
        "trust_score": reputation["trust_score"],
        "last_reported": datetime.now(UTC).isoformat(),
    }
    supabase.table("phone_reputation").upsert(payload).execute()
    return reputation


async def check_phone_reputation_async(phone: str) -> dict[str, Any]:
    """Async-friendly wrapper around the sync Supabase client."""
    reports = await to_thread.run_sync(_fetch_reports, phone)
    return _calculate_from_reports(phone=phone, reports=reports)
