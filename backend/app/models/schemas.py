from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    text: str
    source: str = "dashboard"


class ScamReportCreate(BaseModel):
    reporter_hash: str | None = None
    scam_phone: str | None = None
    upi_id: str | None = None
    company_name: str | None = None
    job_role: str | None = None
    salary: int | None = None
    fee: int | None = None
    location: str | None = None
    risk_score: int | None = None
    trust_weight: float = 1.0


class ScamReportResponse(BaseModel):
    id: UUID | None = None
    reporter_hash: str | None = None
    scam_phone: str | None = None
    upi_id: str | None = None
    company_name: str | None = None
    job_role: str | None = None
    salary: int | None = None
    fee: int | None = None
    location: str | None = None
    risk_score: int | None = None
    trust_weight: float | None = None
    report_time: datetime | None = None


class DashboardStats(BaseModel):
    totalReports: int
    suspiciousNumbers: int
    detectedSyndicates: int
    verifiedCompanies: int


class DashboardReportRow(BaseModel):
    id: str
    phone: str
    message: str
    riskScore: str
    location: str
    timestamp: str


class HeatmapPoint(BaseModel):
    state: str
    count: int


class TrendPoint(BaseModel):
    date: str
    count: int


class NetworkNode(BaseModel):
    id: str
    group: int
    label: str


class NetworkLink(BaseModel):
    source: str
    target: str
    value: int = 1


class NetworkGraphResponse(BaseModel):
    nodes: list[NetworkNode]
    links: list[NetworkLink]


class PhoneLookupResponse(BaseModel):
    number: str
    normalizedNumber: str
    riskScore: str
    reportCount: int
    trustScore: float
    companies: list[str]
    upiIds: list[str]
    lastSeen: str
    recentReports: list[dict[str, Any]] = Field(default_factory=list)
