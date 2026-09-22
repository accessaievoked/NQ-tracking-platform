"""Shopify OAuth authorization-code routes.

  GET /api/integrations/shopify/install?brand_id=..&shop=..   (authenticated)
      -> redirects the merchant to Shopify's authorize screen.
  GET /api/integrations/shopify/callback?code&shop&state&hmac  (public)
      -> verifies hmac + our signed state, exchanges the code for an offline
         token, and stores it on the brand's Shopify integration.

The install endpoint is authenticated (so we know which brand to attach the
store to) and encodes the brand id into a signed `state`. The callback is
public (Shopify calls it via browser redirect) and trusts the signed state
plus Shopify's HMAC instead of a session.

Each brand may install its own Shopify app (custom distribution is one store
per app). The callback reads the brand from our signed state first, then checks
Shopify's HMAC against *that* brand's app secret.
"""
from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.connectors.shopify import ShopifyConnector
from app.connectors.shopify_oauth import (
    STATE_SALT,
    STATE_TTL_SECONDS,
    build_install_url,
    exchange_code_for_token,
    is_valid_shop,
    verify_hmac,
)
from app.config import settings
from app.db import get_db
from app.deps import get_current_user
from app.models import Brand, Integration, IntegrationProvider, IntegrationStatus, User
from app.security import encrypt, make_token, read_token
from app.services import shopify_app_for

router = APIRouter(prefix="/api/integrations/shopify", tags=["shopify-oauth"])



@router.get("/install")
def install(
    brand_id: str,
    shop: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not is_valid_shop(shop):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid shop domain")

    brand = db.get(Brand, brand_id)
    if not brand or brand.client_id != user.client_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Brand not found")

    return RedirectResponse(url=_install_url_for(brand, shop))


@router.get("/install-url")
def install_url(
    brand_id: str,
    shop: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return the Shopify authorize URL as JSON so the SPA can redirect the
    browser to it (the /install redirect can't carry the bearer header)."""
    if not is_valid_shop(shop):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid shop domain")
    brand = db.get(Brand, brand_id)
    if not brand or brand.client_id != user.client_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Brand not found")
    return {"url": _install_url_for(brand, shop)}


def _install_url_for(brand: Brand, shop: str) -> str:
    try:
        app = shopify_app_for(brand)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    state = make_token(
        {"brand_id": brand.id, "shop": shop, "nonce": uuid.uuid4().hex},
        salt=STATE_SALT,
    )
    return build_install_url(shop, state, app)


@router.get("/callback", response_class=HTMLResponse)
def callback(request: Request, db: Session = Depends(get_db)):
    params = dict(request.query_params)
    shop = params.get("shop", "")
    code = params.get("code", "")
    state = params.get("state", "")

    if not is_valid_shop(shop):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid shop domain")

    # Our own signed state comes first: it names the brand, and the brand
    # decides which app's secret Shopify signed this request with.
    data = read_token(state, salt=STATE_SALT, max_age_seconds=STATE_TTL_SECONDS)
    if not data or data.get("shop") != shop:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired state")

    brand = db.get(Brand, data["brand_id"])
    if not brand:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Brand not found")
    try:
        app = shopify_app_for(brand)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    if not verify_hmac(params, app):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "HMAC verification failed")

    token_data = exchange_code_for_token(shop, code, app)  # {access_token, scope}

    # Enrich with shop metadata (best-effort). Record which app granted the
    # token, so a mismatch is visible if a brand's app is ever changed.
    config = {"shop_domain": shop, "app_client_id": app.client_id}
    try:
        info = ShopifyConnector(
            credentials={"access_token": token_data["access_token"]},
            config=config,
        ).verify_connection()
        config.update({"shop_name": info.get("name"), "currency": info.get("currency")})
    except Exception:
        pass

    integ = (
        db.query(Integration)
        .filter(
            Integration.brand_id == brand.id,
            Integration.provider == IntegrationProvider.shopify,
        )
        .first()
    )
    if integ is None:
        integ = Integration(brand_id=brand.id, provider=IntegrationProvider.shopify)
        db.add(integ)

    integ.config = config
    integ.encrypted_tokens = encrypt(
        json.dumps({"access_token": token_data["access_token"], "scope": token_data.get("scope", "")})
    )
    integ.status = IntegrationStatus.connected
    integ.last_error = None
    db.commit()

    return RedirectResponse(url=f"{settings.app_base_url}/?connected=shopify")
