from __future__ import annotations

from datetime import datetime, timezone
from itertools import combinations
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
        "risk_score": _risk_score_to_db_int(risk_score),
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
    payload["risk_score"] = _risk_score_to_db_int(payload.get("risk_score"))

    result = supabase.table("scam_reports").insert(payload).execute()
    data = result.data or []
    created = data[0] if data else payload

    scam_phone = created.get("scam_phone")
    if scam_phone:
        upsert_phone_reputation(str(scam_phone))

    return created


def _safe_int(value: Any) -> int | None:
    try:
        if value is None or str(value).strip() == "":
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _risk_score_to_db_int(value: Any) -> int:
    """Normalize risk score to 0-100 integer for int4 DB columns."""
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0

    if score <= 1:
        score *= 100
    return max(0, min(100, int(round(score))))


def _normalize_source(source: str | None) -> str:
    value = (source or "dashboard").strip().lower()
    if value in {"browser_extension", "extension"}:
        return "extension"
    if value in {"whatsapp", "dashboard"}:
        return value
    return "dashboard"


def store_analysis_report(result: dict[str, Any], source: str | None) -> dict[str, Any] | None:
    """Store high-risk analysis output as a scam report."""
    entities = result.get("entities")
    if not isinstance(entities, dict):
        entities = {}

    phones = entities.get("phone")
    if not isinstance(phones, list):
        phones = entities.get("phones")
    if not isinstance(phones, list):
        phones = []
    scam_phone = str(phones[0]).strip() if phones else None
    company_name = str(entities.get("company") or "").strip() or None
    location = str(entities.get("location") or "").strip() or None
    job_role = str(entities.get("role") or "").strip() or None

    salary_values = entities.get("salary")
    fee_values = entities.get("fee")
    salary = _safe_int(salary_values[0] if isinstance(salary_values, list) and salary_values else salary_values)
    fee = _safe_int(fee_values[0] if isinstance(fee_values, list) and fee_values else fee_values)

    risk_score = _risk_score_to_db_int(result.get("risk_score"))
    payload = {
        "scam_phone": scam_phone,
        "company_name": company_name,
        "job_role": job_role,
        "location": location,
        "salary": salary,
        "fee": fee,
        "risk_score": risk_score,
        "report_time": datetime.now(timezone.utc).isoformat(),
        "source": _normalize_source(source),
    }

    try:
        insert_result = supabase.table("scam_reports").insert(payload).execute()
    except Exception:
        fallback_payload = dict(payload)
        fallback_payload.pop("source", None)
        insert_result = supabase.table("scam_reports").insert(fallback_payload).execute()

    created_rows = insert_result.data or []
    created = created_rows[0] if created_rows else payload
    if scam_phone:
        upsert_phone_reputation(scam_phone)
    return created


def store_report_edges(entities: dict[str, Any]) -> None:
    """Create graph edges for co-occurring entities in a single report."""
    phones = entities.get("phone") if isinstance(entities.get("phone"), list) else []
    upis = entities.get("upi") if isinstance(entities.get("upi"), list) else []
    if not upis and isinstance(entities.get("upi_ids"), list):
        upis = entities.get("upi_ids")

    agent_value = entities.get("agent")
    agents: list[str] = []
    if isinstance(agent_value, str) and agent_value.strip():
        agents = [agent_value.strip()]
    elif isinstance(agent_value, list):
        agents = [str(item).strip() for item in agent_value if str(item).strip()]

    nodes: list[tuple[str, str]] = []
    nodes.extend([("phone", str(item).strip()) for item in phones if str(item).strip()])
    nodes.extend([("upi", str(item).strip()) for item in upis if str(item).strip()])
    nodes.extend([("agent", str(item).strip()) for item in agents if str(item).strip()])
    unique_nodes = list(dict.fromkeys(nodes))

    if len(unique_nodes) < 2:
        return

    now = datetime.now(timezone.utc).isoformat()
    rows: list[dict[str, Any]] = []
    for (type_a, value_a), (type_b, value_b) in combinations(unique_nodes, 2):
        left = f"{type_a}:{value_a}"
        right = f"{type_b}:{value_b}"
        if left == right:
            continue
        src, dst = sorted([left, right])
        rows.append(
            {
                "entity_a": src,
                "entity_b": dst,
                "entity_a_type": type_a,
                "entity_b_type": type_b,
                "weight": 1,
                "last_seen": now,
            }
        )

    if not rows:
        return

    try:
        supabase.table("scam_network_edges").insert(rows).execute()
    except Exception:
        # Edge persistence is best-effort and must not block analysis.
        return
