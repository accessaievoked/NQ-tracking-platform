"""Integration connect routes.

Shopify supports two credential styles:
  - Dev Dashboard app: {"client_id": "...", "client_secret": "..."}  (recommended)
  - Legacy custom app: {"access_token": "shpat_..."}
Both are validated on connect. Other providers store credentials directly for now.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_owned_brand
from app.models import Brand, Integration, IntegrationProvider, IntegrationStatus
from app.schemas import IntegrationOut
from app.security import encrypt
from app.services import (
    prepare_ga4_connection,
    prepare_google_ads_connection,
    prepare_meta_connection,
    prepare_shopify_connection,
)

# Providers that verify their credentials on connect, so a bad paste fails here
# rather than silently producing an empty report a week later.
VERIFIERS = {
    IntegrationProvider.shopify: ("Shopify", prepare_shopify_connection),
    IntegrationProvider.ga4: ("GA4", prepare_ga4_connection),
    IntegrationProvider.meta_ads: ("Meta", prepare_meta_connection),
    IntegrationProvider.google_ads: ("Google Ads", prepare_google_ads_connection),
}

router = APIRouter(prefix="/api/brands/{brand_id}/integrations", tags=["integrations"])


class ConnectBody(BaseModel):
    # Non-secret connection config (e.g. {"shop_domain": "x.myshopify.com"}).
    config: dict = {}
    # Secret credentials. Shopify Dev Dashboard: {"client_id", "client_secret"}.
    credentials: dict = {}


@router.post("/{provider}/connect", response_model=IntegrationOut)
def connect(
    provider: IntegrationProvider,
    body: ConnectBody,
    brand: Brand = Depends(get_owned_brand),
    db: Session = Depends(get_db),
):
    integ = (
        db.query(Integration)
        .filter(Integration.brand_id == brand.id, Integration.provider == provider)
        .first()
    )
    if integ is None:
        integ = Integration(brand_id=brand.id, provider=provider)
        db.add(integ)

    config = dict(body.config)
    creds_to_store = dict(body.credentials)
    status = IntegrationStatus.connected
    error: str | None = None

    if provider in VERIFIERS and body.credentials:
        label, prepare = VERIFIERS[provider]
        try:
            config, creds_to_store = prepare(config, body.credentials)
        except Exception as exc:
            status = IntegrationStatus.error
            error = f"{label} verification failed: {exc}"

    integ.config = config
    if creds_to_store:
        integ.encrypted_tokens = encrypt(json.dumps(creds_to_store))
    integ.status = status
    integ.last_error = error
    db.commit()
    db.refresh(integ)
    return integ


@router.post("/{provider}/disconnect", response_model=IntegrationOut)
def disconnect(
    provider: IntegrationProvider,
    brand: Brand = Depends(get_owned_brand),
    db: Session = Depends(get_db),
):
    integ = (
        db.query(Integration)
        .filter(Integration.brand_id == brand.id, Integration.provider == provider)
        .first()
    )
    if integ:
        integ.encrypted_tokens = None
        integ.config = None
        integ.status = IntegrationStatus.not_connected
        integ.last_error = None
        db.commit()
        db.refresh(integ)
    return integ
