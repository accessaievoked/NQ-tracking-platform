"""Service layer: orchestration used by the API routers."""
from __future__ import annotations

import json
import time
from datetime import datetime

from sqlalchemy.orm import Session

from app.compute.money_flow import AdSpend, aggregate_orders, compute_money_flow
from app.config import settings
from app.connectors.meta_ads import MetaAdsConnector
from app.connectors.shopify import ShopifyConnector, exchange_client_credentials
from app.models import (
    Brand,
    Integration,
    IntegrationProvider,
    RawPull,
    Report,
    ReportStatus,
    ReportType,
)
from app.reports.generator import generate_narrative
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
        type=ReportType.money_flow,
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
