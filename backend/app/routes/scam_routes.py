from __future__ import annotations

from fastapi import APIRouter, Query

from app.models.schemas import (
    DashboardReportRow,
    DashboardStats,
    HeatmapPoint,
    NetworkGraphResponse,
    PhoneLookupResponse,
    ScamReportCreate,
    ScamReportResponse,
    TrendPoint,
)
from app.services.dashboard_service import (
    get_dashboard_stats,
    get_heatmap_data,
    get_network_graph,
    get_phone_lookup,
    get_recent_reports,
    get_trend_data,
)
from app.services.scam_report_store import create_scam_report

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.post("/reports", response_model=ScamReportResponse)
def create_report(report: ScamReportCreate):
    return create_scam_report(report)


@router.get("/dashboard/stats", response_model=DashboardStats)
def dashboard_stats():
    return get_dashboard_stats()


@router.get("/dashboard/reports", response_model=list[DashboardReportRow])
def dashboard_reports(limit: int = Query(default=10, ge=1, le=100)):
    return get_recent_reports(limit=limit)


@router.get("/dashboard/heatmap", response_model=list[HeatmapPoint])
def dashboard_heatmap():
    return get_heatmap_data()


@router.get("/dashboard/trends", response_model=list[TrendPoint])
def dashboard_trends(days: int = Query(default=7, ge=1, le=30)):
    return get_trend_data(days=days)


@router.get("/dashboard/network", response_model=NetworkGraphResponse)
def dashboard_network():
    return get_network_graph()


@router.get("/lookup/phone/{phone}", response_model=PhoneLookupResponse)
def lookup_phone(phone: str):
    return get_phone_lookup(phone)


@router.get("/check-phone/{phone}")
def check_phone(phone: str):
    lookup = get_phone_lookup(phone)
    if lookup["reportCount"] > 0:
        return {
            "status": "reported",
            "data": lookup["recentReports"],
            "summary": lookup,
        }
    return {
        "status": "not_reported",
        "summary": lookup,
    }
