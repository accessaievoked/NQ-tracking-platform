"""Service layer: orchestration used by the API routers."""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.compute.money_flow import (
    AdSpend,
    aggregate_orders,
    compute_money_flow,
    compute_order_health,
    daily_series,
)
from app.compute.tracking import compute_tracking_reality
from app.compute.funnel import (
    EVENT_STEPS,
    FUNNEL_EVENT_NAMES,
    ITEM_METRICS,
    build_table,
    view_spec,
)
from app.config import settings
from app.connectors.google_auth import (
    ANALYTICS_READONLY,
    mint_access_token,
    refresh_access_token,
)
from app.connectors.ga4 import GA4Connector, and_filters, in_list_filter
from app.connectors.meta_ads import MetaAdsConnector
from app.connectors.shopify import ShopifyConnector, exchange_client_credentials
from app.models import (
    Brand,
    Integration,
    IntegrationProvider,
    IntegrationStatus,
    RawPull,
    Report,
    ReportStatus,
    ReportType,
)
from app.reports.generator import (
    generate_narrative,
    generate_report_narrative,
    generate_tracking_narrative,
)
from app.reports.compose import compose_facts
from app.reports.specs import get_spec
from app.security import decrypt, encrypt

# Refresh a client-credentials token this many seconds before it actually expires.
TOKEN_REFRESH_BUFFER = 300


# --- Shopify auth ---------------------------------------------------------

def prepare_shopify_connection(config: dict, credentials: dict) -> tuple[dict, dict]:
    """Validate credentials and return (enriched_config, creds_to_store).

    Accepts either Dev Dashboard client_id/client_secret (exchanged for a token)
    or a legacy static access_token. Raises on any failure.
    """
    config = dict(config)
    creds = dict(credentials)
    shop = config.get("shop_domain")
    if not shop:
        raise ValueError("shop_domain is required in config")

    if creds.get("client_id") and creds.get("client_secret"):
        bundle = exchange_client_credentials(shop, creds["client_id"], creds["client_secret"])
        token = bundle.access_token
        # Seed the cache so we don't immediately re-exchange on first report.
        creds["_cache"] = {"token": token, "expires_at": bundle.expires_at()}
    elif creds.get("access_token"):
        token = creds["access_token"]
    else:
        raise ValueError(
            "Provide client_id+client_secret (Dev Dashboard) or access_token (legacy)"
        )

    info = ShopifyConnector(
        credentials={"access_token": token}, config=config
    ).verify_connection()
    config.update({"shop_name": info.get("name"), "currency": info.get("currency")})
    return config, creds


def prepare_ga4_connection(config: dict, credentials: dict) -> tuple[dict, dict]:
    """Validate GA4 credentials and return (config, creds_to_store).

    Two credential styles are accepted:
      * Durable (recommended): client_id + client_secret + refresh_token
            -> stored as {"oauth": {...}} and refreshed forever by the backend.
      * Legacy/temporary: a raw access_token (e.g. OAuth Playground) that expires
            in ~1 hour. Kept only as a fallback for quick tests.
    Raises on any verification failure.
    """
    config = dict(config)
    creds = dict(credentials)
    prop = config.get("property_id")
    if not prop:
        raise ValueError("property_id is required in config")

    cid, csec, rtok = (
        creds.get("client_id"),
        creds.get("client_secret"),
        creds.get("refresh_token"),
    )
    if cid and csec and rtok:
        token, _ = refresh_access_token(cid, csec, rtok)  # verify the trio works
        creds_to_store = {
            "oauth": {"client_id": cid, "client_secret": csec, "refresh_token": rtok}
        }
    elif creds.get("access_token"):
        token = creds["access_token"]
        creds_to_store = {"access_token": token}
    else:
        raise ValueError(
            "Provide client_id+client_secret+refresh_token (durable) or "
            "access_token (temporary)"
        )

    # Confirm the token can actually read the property.
    GA4Connector(
        credentials={"access_token": token}, config=config
    ).verify_connection()
    return config, creds_to_store


def get_valid_shopify_token(db: Session, integ: Integration | None) -> str | None:
    """Return a usable access token, exchanging/refreshing Dev Dashboard creds
    as needed and persisting the cached token back to the integration."""
    if not integ or not integ.encrypted_tokens:
        return None
    creds = json.loads(decrypt(integ.encrypted_tokens))

    if creds.get("access_token"):  # legacy static token
        return creds["access_token"]

    client_id, client_secret = creds.get("client_id"), creds.get("client_secret")
    if not (client_id and client_secret):
        return None

    now = time.time()
    cache = creds.get("_cache") or {}
    if cache.get("token") and cache.get("expires_at", 0) > now + TOKEN_REFRESH_BUFFER:
        return cache["token"]

    shop = (integ.config or {}).get("shop_domain")
    bundle = exchange_client_credentials(shop, client_id, client_secret)
    creds["_cache"] = {"token": bundle.access_token, "expires_at": bundle.expires_at(now)}
    integ.encrypted_tokens = encrypt(json.dumps(creds))
    db.commit()
    return bundle.access_token


# --- Report pipeline ------------------------------------------------------

def _shopify_connector(db: Session, brand_id: str) -> ShopifyConnector:
    integ = (
        db.query(Integration)
        .filter(
            Integration.brand_id == brand_id,
            Integration.provider == IntegrationProvider.shopify,
        )
        .first()
    )
    token = get_valid_shopify_token(db, integ)
    config = (integ.config or {}) if integ else {}
    creds = {"access_token": token} if token else {}
    return ShopifyConnector(credentials=creds, config=config)


def generate_money_flow_report(
    db: Session,
    brand: Brand,
    period_start: datetime,
    period_end: datetime,
) -> Report:
    """Full pipeline: pull -> normalize -> compute -> narrate -> persist."""
    period_label = f"{period_start:%b %d} - {period_end:%b %d, %Y}"
    report = Report(
        brand_id=brand.id,
        type=ReportType.money_flow_report,
        status=ReportStatus.generating,
        title=f"{brand.name} - Money Flow Report | {period_label}",
        period_start=period_start,
        period_end=period_end,
    )
    db.add(report)
    db.flush()

    try:
        connector = _shopify_connector(db, brand.id)
        payload = connector.fetch(period_start, period_end)

        db.add(
            RawPull(
                brand_id=brand.id,
                provider=IntegrationProvider.shopify,
                period_start=period_start,
                period_end=period_end,
                payload=payload,
            )
        )

        orders = aggregate_orders(connector.normalize(payload))

        ads = get_meta_ad_spend(db, brand.id, period_start, period_end)

        metrics = compute_money_flow(orders, ads, gst_rate=settings.default_gst_rate)
        narrative = generate_narrative(brand.name, period_label, metrics)

        report.computed_metrics = metrics
        report.narrative_md = narrative
        report.status = ReportStatus.ready
    except Exception as exc:  # keep the row, record the failure
        report.status = ReportStatus.failed
        report.error = str(exc)

    db.commit()
    db.refresh(report)
    return report


def generate_ai_report(
    db: Session,
    brand: Brand,
    report_type: ReportType,
    period_start: datetime,
    period_end: datetime,
    facts: dict,
) -> Report:
    """Generic pipeline for spec-backed report types.

    The caller supplies a PRE-COMPUTED ``facts`` bundle (deterministic numbers);
    this narrates it via the report's registered spec and persists the row. The
    facts are stored verbatim in ``computed_metrics`` so a report can be
    re-narrated later without recomputing.
    """
    spec = get_spec(report_type)  # raises for unknown types -> surfaced as 400 by API
    period_label = f"{period_start:%b %d} - {period_end:%b %d, %Y}"
    report = Report(
        brand_id=brand.id,
        type=report_type,
        status=ReportStatus.generating,
        title=f"{brand.name} - {spec.title} | {period_label}",
        period_start=period_start,
        period_end=period_end,
    )
    db.add(report)
    db.flush()

    try:
        narrative = generate_report_narrative(report_type, brand.name, period_label, facts)
        report.computed_metrics = facts
        report.narrative_md = narrative
        report.status = ReportStatus.ready
    except Exception as exc:  # keep the row, record the failure
        report.status = ReportStatus.failed
        report.error = str(exc)

    db.commit()
    db.refresh(report)
    return report


def get_meta_ad_spend(
    db: Session, brand_id: str, period_start: datetime, period_end: datetime
) -> AdSpend:
    """Return real Meta ad spend for the period, or an unconnected AdSpend.

    Unconnected -> Money Flow withholds ROAS instead of printing a bogus number.
    """
    integ = (
        db.query(Integration)
        .filter(
            Integration.brand_id == brand_id,
            Integration.provider == IntegrationProvider.meta_ads,
        )
        .first()
    )
    if not integ or not integ.encrypted_tokens:
        return AdSpend(connected=False)

    creds = json.loads(decrypt(integ.encrypted_tokens))
    token = creds.get("access_token")
    if not token:
        return AdSpend(connected=False)

    connector = MetaAdsConnector(credentials={"access_token": token}, config=integ.config or {})
    try:
        payload = connector.fetch(period_start, period_end)
        return connector.to_ad_spend(payload)
    except Exception:
        return AdSpend(connected=False)


def get_valid_ga4_token(db: Session, integ: Integration | None) -> str | None:
    """Return a usable GA4 access token.

    Service-account creds are minted into a short-lived token and cached (and
    re-minted automatically on expiry) — no human refresh. A raw access_token
    (e.g. from the OAuth Playground) is served directly as a fallback.
    """
    if not integ or not integ.encrypted_tokens:
        return None
    creds = json.loads(decrypt(integ.encrypted_tokens))

    sa = creds.get("service_account")
    if sa:
        now = time.time()
        cache = creds.get("_cache") or {}
        if cache.get("token") and cache.get("expires_at", 0) > now + TOKEN_REFRESH_BUFFER:
            return cache["token"]
        token, expires_in = mint_access_token(sa, ANALYTICS_READONLY)
        creds["_cache"] = {"token": token, "expires_at": now + expires_in}
        integ.encrypted_tokens = encrypt(json.dumps(creds))
        db.commit()
        return token

    oauth = creds.get("oauth")
    if oauth:
        now = time.time()
        cache = creds.get("_cache") or {}
        if cache.get("token") and cache.get("expires_at", 0) > now + TOKEN_REFRESH_BUFFER:
            return cache["token"]
        token, expires_in = refresh_access_token(
            oauth["client_id"], oauth["client_secret"], oauth["refresh_token"]
        )
        creds["_cache"] = {"token": token, "expires_at": now + expires_in}
        integ.encrypted_tokens = encrypt(json.dumps(creds))
        db.commit()
        return token

    return creds.get("access_token")


def get_ga4_summary(
    db: Session, brand_id: str, period_start: datetime, period_end: datetime
) -> dict | None:
    """Return GA4 period totals for a brand, or None if GA4 isn't connected."""
    integ = (
        db.query(Integration)
        .filter(
            Integration.brand_id == brand_id,
            Integration.provider == IntegrationProvider.ga4,
        )
        .first()
    )
    token = get_valid_ga4_token(db, integ)
    if not integ or not token:
        return None
    connector = GA4Connector(credentials={"access_token": token}, config=integ.config or {})
    return connector.summarize(connector.fetch(period_start, period_end))


def compute_tracking(
    db: Session, brand: Brand, period_start: datetime, period_end: datetime
) -> tuple[dict, str]:
    """Reconcile GA4 tracked purchases vs Shopify real orders. Returns (metrics, narrative)."""
    connector = _shopify_connector(db, brand.id)
    orders = aggregate_orders(connector.normalize(connector.fetch(period_start, period_end)))

    ga4 = get_ga4_summary(db, brand.id, period_start, period_end)
    if ga4 is None:
        raise RuntimeError("GA4 is not connected for this brand")

    metrics = compute_tracking_reality(orders, ga4)
    label = f"{period_start:%b %d} - {period_end:%b %d, %Y}"
    narrative = generate_tracking_narrative(brand.name, label, metrics)
    return metrics, narrative


def generate_report_from_data(db: Session, brand: Brand, report_type: ReportType, days: int = 30) -> dict:
    """On-demand report for the Insights page: compute from the brand's live data
    (Shopify orders + Meta ad spend), compose section facts, and narrate.

    Returns {type, title, period, narrative_md, facts}. Money-flow report types
    compose full section facts; others get the raw money_flow block (the AI
    narrates what's available and flags what isn't connected)."""
    spec = get_spec(report_type)  # raises for types without a spec -> 400 in the API
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    label = f"{start:%b %d} - {end:%b %d, %Y}"

    connector = _shopify_connector(db, brand.id)
    normalized = connector.normalize(connector.fetch(start, end))
    orders = aggregate_orders(normalized)
    ads = get_meta_ad_spend(db, brand.id, start, end)
    money = compute_money_flow(orders, ads, gst_rate=settings.default_gst_rate)

    facts = compose_facts(report_type, money)
    if facts is None:
        facts = {"currency": "INR", "money_flow": money}
    facts["brand"] = brand.name
    facts["period"] = label

    # Order-health tiles + daily chart belong ONLY to the Money Flow report
    # (its prompt has an ORDER HEALTH section). No other report gets them.
    if report_type == ReportType.money_flow_report:
        mo = money["money_out"]
        facts["order_health"] = compute_order_health(orders)
        facts["daily"] = daily_series(
            normalized, mo.get("real_ad_cost"), bool(mo.get("ad_spend_connected"))
        )

    narrative = generate_report_narrative(report_type, brand.name, label, facts)
    return {
        "type": report_type.value,
        "title": spec.title,
        "period": label,
        "narrative_md": narrative,
        "facts": facts,
    }


# --- Data Insights: GA4 funnel views --------------------------------------

BASE_METRICS = ["totalUsers", "sessions", "engagementRate"]
EVENT_METRICS = ["totalUsers", "eventCount"]
ITEM_METRIC_NAMES = list(ITEM_METRICS) + ["itemRevenue"]

# Dimensions the Data Insights page can filter on, mirroring the source report's
# three filter controls (Page title / Source-Medium / Browser).
FILTER_FIELDS = {
    "page_title": "pageTitle",
    "source_medium": "sessionSourceMedium",
    "browser": "browser",
    "operating_system": "operatingSystem",
}


def _integration(db: Session, brand_id: str, provider: IntegrationProvider) -> Integration | None:
    return (
        db.query(Integration)
        .filter(Integration.brand_id == brand_id, Integration.provider == provider)
        .first()
    )


def get_ga4_connector(db: Session, brand_id: str) -> GA4Connector | None:
    """A GA4 connector with live credentials, or None when GA4 isn't connected.

    Deliberately returns None rather than a sample-data connector: the Data
    Insights page must not show invented numbers.
    """
    integ = _integration(db, brand_id, IntegrationProvider.ga4)
    token = get_valid_ga4_token(db, integ)
    if not integ or not token or not (integ.config or {}).get("property_id"):
        return None
    return GA4Connector(credentials={"access_token": token}, config=integ.config or {})


def analytics_connection_status(db: Session, brand_id: str) -> dict:
    """What the Data Insights page needs before it can render anything."""
    out: dict[str, Any] = {}
    for provider in (IntegrationProvider.ga4, IntegrationProvider.shopify):
        integ = _integration(db, brand_id, provider)
        out[provider.value] = {
            "status": integ.status.value if integ else "not_connected",
            "connected": bool(integ and integ.status == IntegrationStatus.connected),
            "last_error": integ.last_error if integ else None,
        }

    ga4_integ = _integration(db, brand_id, IntegrationProvider.ga4)
    out["ga4"]["property_id"] = (ga4_integ.config or {}).get("property_id") if ga4_integ else None
    # Marked connected in the DB isn't enough — the token has to actually mint.
    out["ga4"]["connected"] = out["ga4"]["connected"] and get_ga4_connector(db, brand_id) is not None
    # GA4 is the funnel's data source; Shopify only enriches it, so it doesn't gate rendering.
    out["can_render"] = out["ga4"]["connected"]
    return out


def list_dimension_values(
    db: Session, brand_id: str, field: str, start: datetime, end: datetime, limit: int = 250
) -> list[dict]:
    """Values for a filter dropdown, biggest audience first."""
    connector = get_ga4_connector(db, brand_id)
    if connector is None:
        return []
    rows = connector.run_report(
        dimensions=[field],
        metrics=["totalUsers"],
        start=start,
        end=end,
        order_bys=[{"metric": {"metricName": "totalUsers"}, "desc": True}],
        limit=limit,
    )
    return [
        {"value": r["dimensions"][0], "total_users": int(r["metrics"].get("totalUsers", 0))}
        for r in rows
        if r.get("dimensions")
    ]


def list_page_titles(
    db: Session, brand_id: str, start: datetime, end: datetime, limit: int = 250
) -> list[dict]:
    return list_dimension_values(db, brand_id, "pageTitle", start, end, limit)


def list_ga4_events(
    db: Session, brand_id: str, start: datetime, end: datetime, limit: int = 300
) -> list[dict]:
    """Every event name the property actually sends, with user + event counts.

    This is how the checkout micro-funnel (CAS / CAF / GCI / ASI / API) gets
    pinned down: those are custom events, so read the real names here and set
    them in app.compute.funnel.CUSTOM_STEP_EVENTS. ``mapped_to`` shows which
    funnel step, if any, currently consumes each event.
    """
    connector = get_ga4_connector(db, brand_id)
    if connector is None:
        return []
    rows = connector.run_report(
        dimensions=["eventName"],
        metrics=["totalUsers", "eventCount"],
        start=start,
        end=end,
        order_bys=[{"metric": {"metricName": "eventCount"}, "desc": True}],
        limit=limit,
    )
    out = []
    for r in rows:
        if not r.get("dimensions"):
            continue
        name = r["dimensions"][0]
        out.append({
            "event": name,
            "total_users": int(r["metrics"].get("totalUsers", 0)),
            "event_count": int(r["metrics"].get("eventCount", 0)),
            "mapped_to": EVENT_STEPS.get(name, []),
        })
    return out


def _build_tables(
    connector: GA4Connector,
    spec: dict,
    start: datetime,
    end: datetime,
    dim_filter: dict | None,
) -> list[dict]:
    """Fetch and assemble every table for one view over one period.

    GA4 queries are cached per (dimensions, source) for the call, so the four
    Product Funnel tables cost two dimension pulls, not four.
    """
    event_filter = in_list_filter("eventName", FUNNEL_EVENT_NAMES)
    cache: dict[tuple, tuple[list, list]] = {}
    totals_cache: dict[str, list] = {}

    def dimension_data(dimensions: list[str], source: str) -> tuple[list, list]:
        key = (tuple(dimensions), source)
        if key in cache:
            return cache[key]
        if source == "items":
            # Item-scoped: one row per product, no eventName breakdown. The page
            # filter is event-scoped and would drop purchases, so it is not applied.
            rows = connector.run_report(
                dimensions=dimensions,
                metrics=ITEM_METRIC_NAMES,
                start=start,
                end=end,
                order_bys=[{"metric": {"metricName": "itemsViewed"}, "desc": True}],
                limit=5000,
            )
            cache[key] = (rows, [])
            return cache[key]
        events = connector.run_report(
            dimensions=[*dimensions, "eventName"],
            metrics=EVENT_METRICS,
            start=start,
            end=end,
            dimension_filter=and_filters(event_filter, dim_filter),
        )
        base = connector.run_report(
            dimensions=dimensions,
            metrics=BASE_METRICS,
            start=start,
            end=end,
            dimension_filter=dim_filter,
        )
        cache[key] = (events, base)
        return cache[key]

    def totals(source: str) -> list:
        if source not in totals_cache:
            if source == "items":
                totals_cache[source] = connector.run_report(
                    dimensions=[], metrics=ITEM_METRIC_NAMES, start=start, end=end
                )
            else:
                totals_cache[source] = connector.run_report(
                    dimensions=["eventName"],
                    metrics=EVENT_METRICS,
                    start=start,
                    end=end,
                    dimension_filter=and_filters(event_filter, dim_filter),
                )
        return totals_cache[source]

    total_base_rows = connector.run_report(
        dimensions=[], metrics=BASE_METRICS, start=start, end=end, dimension_filter=dim_filter,
    )
    total_base = total_base_rows[0]["metrics"] if total_base_rows else {}

    tables = []
    for table_spec in spec["tables"]:
        source = table_spec.get("source", "events")
        events, base = dimension_data(table_spec["dimensions"], source)
        tables.append(build_table(table_spec, events, base, totals(source), total_base))
    return tables


def build_funnel_view(
    db: Session,
    brand_id: str,
    view: str,
    start: datetime,
    end: datetime,
    filters: dict[str, list[str]] | None = None,
) -> dict:
    """Fetch every table (and, for comparison views, the previous period)."""
    spec = view_spec(view)
    connector = get_ga4_connector(db, brand_id)
    if connector is None:
        raise RuntimeError("GA4 is not connected for this brand")

    active = {k: v for k, v in (filters or {}).items() if v}
    dim_filter = and_filters(*[
        in_list_filter(FILTER_FIELDS[k], v) for k, v in active.items() if k in FILTER_FIELDS
    ])

    tables = _build_tables(connector, spec, start, end, dim_filter)

    prev_tables: list[dict] = []
    prev_period: dict | None = None
    if spec.get("compare"):
        # Same length, immediately before the selected range.
        span = (end - start) + timedelta(days=1)
        prev_end = start - timedelta(days=1)
        prev_start = prev_end - span + timedelta(days=1)
        prev_tables = _build_tables(connector, spec, prev_start, prev_end, dim_filter)
        prev_period = {"start": prev_start.strftime("%Y-%m-%d"),
                       "end": prev_end.strftime("%Y-%m-%d")}

    return {
        "view": view,
        "label": spec["label"],
        "blurb": spec["blurb"],
        "period": {"start": start.strftime("%Y-%m-%d"), "end": end.strftime("%Y-%m-%d")},
        "prev_period": prev_period,
        "filters": active,
        "tables": tables,
        "prev_tables": prev_tables,
        "charts": spec.get("charts", []),
    }
