from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from app.services.supabase_client import supabase


def _normalize_phone(phone: str) -> str:
    return "".join(ch for ch in phone if ch.isdigit())


def _risk_label(score: int | float | None) -> str:
    numeric_score = float(score or 0)
    if numeric_score >= 75:
        return "High Risk"
    if numeric_score >= 40:
        return "Suspicious"
    return "Safe"


def _format_report_message(report: dict[str, Any]) -> str:
    parts = [
        report.get("company_name"),
        report.get("job_role"),
        f"Salary {report.get('salary')}" if report.get("salary") else None,
        f"Fee {report.get('fee')}" if report.get("fee") else None,
        report.get("upi_id"),
    ]
    message = " | ".join(str(part) for part in parts if part)
    return message or "Scam report received"


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except ValueError:
        return None


def _fetch_reports(limit: int = 1000) -> list[dict[str, Any]]:
    result = (
        supabase.table("scam_reports")
        .select(
            "id, reporter_hash, scam_phone, upi_id, company_name, job_role, salary, fee, "
            "location, risk_score, trust_weight, report_time"
        )
        .order("report_time", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data or []


def get_dashboard_stats() -> dict[str, int]:
    reports = _fetch_reports()
    suspicious_numbers = {
        _normalize_phone(str(report.get("scam_phone") or ""))
        for report in reports
        if report.get("scam_phone")
    }
    suspicious_numbers.discard("")

    company_counter = Counter(
        str(report.get("company_name")).strip()
        for report in reports
        if report.get("company_name")
    )

    upi_to_phones: dict[str, set[str]] = defaultdict(set)
    company_to_phones: dict[str, set[str]] = defaultdict(set)
    for report in reports:
        phone = _normalize_phone(str(report.get("scam_phone") or ""))
        if not phone:
            continue
        upi = str(report.get("upi_id") or "").strip()
        company = str(report.get("company_name") or "").strip()
        if upi:
            upi_to_phones[upi].add(phone)
        if company:
            company_to_phones[company].add(phone)

    syndicate_count = sum(1 for phones in upi_to_phones.values() if len(phones) > 1)
    syndicate_count += sum(1 for phones in company_to_phones.values() if len(phones) > 1)

    return {
        "totalReports": len(reports),
        "suspiciousNumbers": len(suspicious_numbers),
        "detectedSyndicates": syndicate_count,
        "verifiedCompanies": sum(1 for _, count in company_counter.items() if count == 1),
    }


def get_recent_reports(limit: int = 10) -> list[dict[str, Any]]:
    reports = _fetch_reports(limit=max(limit, 1))
    rows: list[dict[str, Any]] = []
    for report in reports[:limit]:
        timestamp = _parse_timestamp(report.get("report_time"))
        rows.append(
            {
                "id": str(report.get("id")),
                "phone": report.get("scam_phone") or "Unknown",
                "message": _format_report_message(report),
                "riskScore": _risk_label(report.get("risk_score")),
                "location": report.get("location") or "Unknown",
                "timestamp": timestamp.strftime("%Y-%m-%d %I:%M %p") if timestamp else "Unknown",
            }
        )
    return rows


def get_heatmap_data(limit: int = 2000) -> list[dict[str, Any]]:
    reports = _fetch_reports(limit=limit)
    counts = Counter(
        str(report.get("location")).strip()
        for report in reports
        if report.get("location")
    )
    return [
        {"state": state, "count": count}
        for state, count in counts.most_common()
    ]


def get_trend_data(days: int = 7) -> list[dict[str, Any]]:
    safe_days = min(max(days, 1), 30)
    reports = _fetch_reports(limit=3000)
    cutoff = datetime.now(UTC).date() - timedelta(days=safe_days - 1)
    counts: Counter[str] = Counter()

    for report in reports:
        timestamp = _parse_timestamp(report.get("report_time"))
        if not timestamp:
            continue
        report_date = timestamp.astimezone(UTC).date()
        if report_date >= cutoff:
            counts[report_date.isoformat()] += 1

    return [
        {
            "date": (cutoff + timedelta(days=offset)).strftime("%m-%d"),
            "count": counts.get((cutoff + timedelta(days=offset)).isoformat(), 0),
        }
        for offset in range(safe_days)
    ]


def get_network_graph(limit: int = 300) -> dict[str, list[dict[str, Any]]]:
    reports = _fetch_reports(limit=limit)
    nodes: dict[str, dict[str, Any]] = {}
    links: dict[tuple[str, str], int] = defaultdict(int)

    def add_node(node_id: str, group: int, label: str) -> None:
        if node_id and node_id not in nodes:
            nodes[node_id] = {"id": node_id, "group": group, "label": label}

    def add_link(source: str, target: str) -> None:
        if not source or not target or source == target:
            return
        links[(source, target)] += 1

    for report in reports:
        phone = str(report.get("scam_phone") or "").strip()
        upi_id = str(report.get("upi_id") or "").strip()
        company = str(report.get("company_name") or "").strip()
        role = str(report.get("job_role") or "").strip()

        add_node(phone, 1, "Phone Number")
        add_node(upi_id, 2, "UPI ID")
        add_node(role, 3, "Job Role")
        add_node(company, 4, "Company Name")

        add_link(phone, upi_id)
        add_link(phone, role)
        add_link(role, company)
        add_link(upi_id, company)

    return {
        "nodes": list(nodes.values()),
        "links": [
            {"source": source, "target": target, "value": value}
            for (source, target), value in links.items()
        ],
    }


def get_phone_lookup(phone: str) -> dict[str, Any]:
    normalized = _normalize_phone(phone)
    reports = _fetch_reports(limit=2000)
    matched_reports = [
        report for report in reports if _normalize_phone(str(report.get("scam_phone") or "")) == normalized
    ]

    if not matched_reports:
        return {
            "number": phone,
            "normalizedNumber": normalized,
            "riskScore": "Safe",
            "reportCount": 0,
            "trustScore": 0.0,
            "companies": [],
            "upiIds": [],
            "lastSeen": "N/A",
            "recentReports": [],
        }

    trust_score = round(sum(float(report.get("trust_weight") or 0) for report in matched_reports), 2)
    last_seen_dt = _parse_timestamp(matched_reports[0].get("report_time"))
    recent_reports: list[dict[str, Any]] = []
    for report in matched_reports[:5]:
        timestamp = _parse_timestamp(report.get("report_time"))
        recent_reports.append(
            {
                "id": str(report.get("id")),
                "company": report.get("company_name"),
                "jobRole": report.get("job_role"),
                "riskScore": _risk_label(report.get("risk_score")),
                "location": report.get("location"),
                "reportedAt": timestamp.isoformat() if timestamp else None,
            }
        )

    risk_score = "High Risk" if trust_score >= 3 or len(matched_reports) >= 3 else "Suspicious"
    return {
        "number": phone,
        "normalizedNumber": normalized,
        "riskScore": risk_score,
        "reportCount": len(matched_reports),
        "trustScore": trust_score,
        "companies": sorted(
            {
                str(report.get("company_name")).strip()
                for report in matched_reports
                if report.get("company_name")
            }
        ),
        "upiIds": sorted(
            {
                str(report.get("upi_id")).strip()
                for report in matched_reports
                if report.get("upi_id")
            }
        ),
        "lastSeen": last_seen_dt.strftime("%Y-%m-%d %I:%M %p") if last_seen_dt else "Unknown",
        "recentReports": recent_reports,
    }
