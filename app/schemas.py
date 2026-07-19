"""Pydantic request/response schemas for the API."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr

from app.models import (
    IntegrationProvider,
    IntegrationStatus,
    ReportStatus,
    ReportType,
)


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- Auth ---
class MagicLinkRequest(BaseModel):
    email: EmailStr


class MagicLinkIssued(BaseModel):
    sent: bool
    # In local dev we return the link directly so there's no email dependency.
    dev_login_url: str | None = None


class SessionOut(BaseModel):
    token: str
    user_id: str
    client_id: str
    email: str


# --- Brands ---
class BrandCreate(BaseModel):
    name: str
    website: str | None = None
    industry: str | None = None


class IntegrationOut(ORMModel):
    id: str
    provider: IntegrationProvider
    status: IntegrationStatus
    last_synced_at: datetime | None = None
    last_error: str | None = None


class BrandOut(ORMModel):
    id: str
    client_id: str
    name: str
    website: str | None = None
    industry: str | None = None
    is_active: bool
    created_at: datetime


class BrandDetail(BrandOut):
    integrations: list[IntegrationOut] = []


# --- Reports ---
class ReportCreate(BaseModel):
    type: ReportType = ReportType.money_flow
    period_start: datetime
    period_end: datetime
    # For spec-backed report types that don't yet have a live compute path,
    # the caller passes a PRE-COMPUTED facts bundle to be narrated. Ignored for
    # money_flow, which computes its own metrics from connected data.
    facts: dict | None = None


class ReportSummary(ORMModel):
    id: str
    brand_id: str
    type: ReportType
    status: ReportStatus
    title: str
    period_start: datetime
    period_end: datetime
    created_at: datetime


class ReportDetail(ReportSummary):
    computed_metrics: dict | None = None
    narrative_md: str | None = None
    artifact_url: str | None = None
    error: str | None = None
