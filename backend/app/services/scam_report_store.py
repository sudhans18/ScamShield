from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.models.schemas import ScamReportCreate
from app.services.reputation.phone_reputation import upsert_phone_reputation
from app.services.supabase_client import supabase


def _first_phone(entities: dict[str, Any]) -> str | None:
    phones = entities.get("phones", [])
    if isinstance(phones, list) and phones:
        phone = str(phones[0]).strip()
        return phone or None
    return None


def store_scam_report(
    entities: dict[str, Any], risk_score: float, reporter_hash: str
) -> dict[str, Any] | None:
    scam_phone = _first_phone(entities)
    if scam_phone is None:
        return None

    payload = {
        "scam_phone": scam_phone,
        "company_name": entities.get("company"),
        "job_role": entities.get("role"),
        "salary": entities.get("salary"),
        "fee": entities.get("fee"),
        "location": entities.get("location"),
        "risk_score": float(risk_score),
        "trust_weight": 0.1,
        "report_time": datetime.now(timezone.utc).isoformat(),
    }

    _ = reporter_hash
    result = supabase.table("scam_reports").insert(payload).execute()
    data = result.data or []
    if scam_phone:
        upsert_phone_reputation(scam_phone)
    return data[0] if data else payload


def create_scam_report(report: ScamReportCreate) -> dict[str, Any]:
    payload = report.model_dump(exclude_none=True)
    payload.setdefault("report_time", datetime.now(timezone.utc).isoformat())

    result = supabase.table("scam_reports").insert(payload).execute()
    data = result.data or []
    created = data[0] if data else payload

    scam_phone = created.get("scam_phone")
    if scam_phone:
        upsert_phone_reputation(str(scam_phone))

    return created
