"""SQLAlchemy ORM models.

Tenancy model:
  client  ->  many brands
  client  ->  many users
  brand   ->  many integrations / raw_pulls / metrics / reports

Every tenant-scoped row carries brand_id (or client_id) so access can be
filtered in one data-access layer (and later hardened with Postgres RLS).
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

# Postgres gets real JSONB; other engines (e.g. SQLite in tests) get JSON.
JSONType = JSON().with_variant(JSONB, "postgresql")


def _uuid() -> str:
    return str(uuid.uuid4())


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class IntegrationProvider(str, enum.Enum):
    shopify = "shopify"
    meta_ads = "meta_ads"
    google_ads = "google_ads"
    ga4 = "ga4"
    search_console = "search_console"


class IntegrationStatus(str, enum.Enum):
    not_connected = "not_connected"
    connected = "connected"
    error = "error"


class ReportType(str, enum.Enum):
        # --- Legacy / generic (kept for back-compat) ---
    money_flow = "money_flow"
    account_audit = "account_audit"
    product_pl = "product_pl"
    performance = "performance"

    # --- Alerts (event-triggered) ---
    cpa_spike_alert = "cpa_spike_alert"
    creative_fatigue_alert = "creative_fatigue_alert"
    daily_spend_alert = "daily_spend_alert"
    wasted_spend_alert = "wasted_spend_alert"

    # --- Weekly ---
    cod_rto_weekly = "cod_rto_weekly"
    creative_health_weekly = "creative_health_weekly"
    money_flow_weekly = "money_flow_weekly"
    platform_compare_weekly = "platform_compare_weekly"
    weekly_action_plan = "weekly_action_plan"

    # --- Monthly ---
    monthly_customer_quality = "monthly_customer_quality"
    monthly_money_flow = "monthly_money_flow"
    monthly_performance = "monthly_performance"
    monthly_product_pl = "monthly_product_pl"

    # --- Deep-dive / strategy (adverti-style) ---
    # account_audit + product_pl (legacy, above) are the Full Account Audit
    # health-score and Product P&L reports respectively.
    meta_ads_kill_strategy = "meta_ads_kill_strategy"
    campaign_attribution = "campaign_attribution"
    ad_strategy = "ad_strategy"
    true_roas_money_flow = "true_roas_money_flow"
    campaign_revamp = "campaign_revamp"
    meta_ads_performance = "meta_ads_performance"


class ReportStatus(str, enum.Enum):
    pending = "pending"
    generating = "generating"
    ready = "ready"
    failed = "failed"


class Client(TimestampMixin, Base):
    __tablename__ = "clients"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200), nullable=False)

    brands: Mapped[list["Brand"]] = relationship(
        back_populates="client", cascade="all, delete-orphan"
    )
    users: Mapped[list["User"]] = relationship(
        back_populates="client", cascade="all, delete-orphan"
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    client_id: Mapped[str] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), index=True, nullable=False
    )
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    name: Mapped[str | None] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    client: Mapped["Client"] = relationship(back_populates="users")


class Brand(TimestampMixin, Base):
    __tablename__ = "brands"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    client_id: Mapped[str] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    website: Mapped[str | None] = mapped_column(String(300))
    industry: Mapped[str | None] = mapped_column(String(120))
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    client: Mapped["Client"] = relationship(back_populates="brands")
    integrations: Mapped[list["Integration"]] = relationship(
        back_populates="brand", cascade="all, delete-orphan"
    )
    reports: Mapped[list["Report"]] = relationship(
        back_populates="brand", cascade="all, delete-orphan"
    )


class Integration(TimestampMixin, Base):
    __tablename__ = "integrations"
    __table_args__ = (
        UniqueConstraint("brand_id", "provider", name="uq_brand_provider"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    brand_id: Mapped[str] = mapped_column(
        ForeignKey("brands.id", ondelete="CASCADE"), index=True, nullable=False
    )
    provider: Mapped[IntegrationProvider] = mapped_column(
        Enum(IntegrationProvider), nullable=False
    )
    status: Mapped[IntegrationStatus] = mapped_column(
        Enum(IntegrationStatus), default=IntegrationStatus.not_connected, nullable=False
    )
    # Encrypted JSON blob of OAuth tokens / API credentials (see app.security).
    encrypted_tokens: Mapped[str | None] = mapped_column(Text)
    # Non-secret connection config (account id, shop domain, etc.).
    config: Mapped[dict | None] = mapped_column(JSONType)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)

    brand: Mapped["Brand"] = relationship(back_populates="integrations")


class RawPull(TimestampMixin, Base):
    """Staging store of raw API responses so reports can be recomputed
    without re-hitting provider APIs."""

    __tablename__ = "raw_pulls"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    brand_id: Mapped[str] = mapped_column(
        ForeignKey("brands.id", ondelete="CASCADE"), index=True, nullable=False
    )
    provider: Mapped[IntegrationProvider] = mapped_column(
        Enum(IntegrationProvider), nullable=False
    )
    period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict] = mapped_column(JSONType, nullable=False)


class Metric(TimestampMixin, Base):
    """Normalized daily facts derived from raw pulls."""

    __tablename__ = "metrics"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    brand_id: Mapped[str] = mapped_column(
        ForeignKey("brands.id", ondelete="CASCADE"), index=True, nullable=False
    )
    provider: Mapped[IntegrationProvider] = mapped_column(
        Enum(IntegrationProvider), nullable=False
    )
    metric_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Flexible key/value fact bag (spend, orders, revenue, etc.).
    data: Mapped[dict] = mapped_column(JSONType, nullable=False)


class Report(TimestampMixin, Base):
    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    brand_id: Mapped[str] = mapped_column(
        ForeignKey("brands.id", ondelete="CASCADE"), index=True, nullable=False
    )
    type: Mapped[ReportType] = mapped_column(Enum(ReportType), nullable=False)
    status: Mapped[ReportStatus] = mapped_column(
        Enum(ReportStatus), default=ReportStatus.pending, nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Deterministically computed metrics (the numbers the LLM must not invent).
    computed_metrics: Mapped[dict | None] = mapped_column(JSONType)
    narrative_md: Mapped[str | None] = mapped_column(Text)
    artifact_url: Mapped[str | None] = mapped_column(String(500))
    error: Mapped[str | None] = mapped_column(Text)

    brand: Mapped["Brand"] = relationship(back_populates="reports")
