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
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
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

# SQLite only auto-increments a column typed exactly INTEGER (it aliases rowid),
# so a BIGINT primary key never gets a value there. Postgres keeps the bigint.
BigIntPK = BigInteger().with_variant(Integer, "sqlite")


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
    clarity = "clarity"


class IntegrationStatus(str, enum.Enum):
    not_connected = "not_connected"
    connected = "connected"
    error = "error"


class ReportType(str, enum.Enum):
    # --- Account & performance ---
    account_audit = "account_audit"
    weekly_performance = "weekly_performance"
    cpa_diagnosis = "cpa_diagnosis"
    day_of_week = "day_of_week"

    # --- Spend & budget ---
    wasted_spend = "wasted_spend"
    budget_reallocation = "budget_reallocation"
    scaling_opportunities = "scaling_opportunities"
    diminishing_returns = "diminishing_returns"

    # --- Creative ---
    creative_fatigue = "creative_fatigue"
    ad_ranking = "ad_ranking"
    messaging_angles = "messaging_angles"
    creative_briefs = "creative_briefs"

    # --- Audience & targeting ---
    audience_analysis = "audience_analysis"
    demographic_breakdown = "demographic_breakdown"
    retargeting_audit = "retargeting_audit"
    geographic_performance = "geographic_performance"
    advantage_plus_readiness = "advantage_plus_readiness"
    placement_analysis = "placement_analysis"

    # --- Google-specific ---
    search_terms_audit = "search_terms_audit"
    shopping_pmax_products = "shopping_pmax_products"
    impression_share = "impression_share"
    keyword_opportunities = "keyword_opportunities"

    # --- Cross-platform & planning ---
    weekly_action_plan = "weekly_action_plan"
    platform_comparison = "platform_comparison"
    cross_platform_budget = "cross_platform_budget"
    funnel_mapping = "funnel_mapping"

    # --- Commerce / money ---
    money_flow_report = "money_flow_report"
    product_pl = "product_pl"
    reality_check = "reality_check"
    cod_prepaid = "cod_prepaid"
    customer_quality = "customer_quality"


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
    # Public write-only key embedded in the storefront pixel. It identifies the
    # brand on ingest so the pixel needs no session token (it runs in the
    # shopper's browser, where nothing is secret). Rotatable from the UI.
    live_ingest_key: Mapped[str | None] = mapped_column(
        String(48), unique=True, index=True
    )

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


class LiveEvent(Base):
    """One storefront pixel hit, kept only for a short rolling window.

    Deliberately *not* a TimestampMixin: this is the highest-write table in the
    schema and ``ts`` (the event's own time) is the only time that matters, so
    two extra timestamp columns per row would be pure overhead. For the same
    reason the primary key is an identity bigint rather than the UUID string
    used elsewhere — UUID PKs fragment the index badly under append-heavy load.

    Rows older than ``settings.live_retention_minutes`` are pruned on ingest;
    this table is a buffer, not a historical record.
    """

    __tablename__ = "live_events"
    __table_args__ = (
        # The only query this table serves: one brand, one time window.
        Index("ix_live_events_brand_ts", "brand_id", "ts"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    brand_id: Mapped[str] = mapped_column(
        ForeignKey("brands.id", ondelete="CASCADE"), nullable=False
    )
    # Shopify web-pixel clientId — the thread that makes journeys possible.
    visitor_id: Mapped[str] = mapped_column(String(64), nullable=False)
    session_id: Mapped[str | None] = mapped_column(String(64))
    # Populated only once a shopper logs in; enables cross-device stitching.
    customer_id: Mapped[str | None] = mapped_column(String(64))
    event_name: Mapped[str] = mapped_column(String(64), nullable=False)
    # Derived server-side (never trusted from the client) — see compute.live_journey.
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    path: Mapped[str | None] = mapped_column(String(512))
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


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
