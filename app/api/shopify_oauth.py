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
from app.db import get_db
from app.deps import get_current_user
from app.models import Brand, Integration, IntegrationProvider, IntegrationStatus, User
from app.security import encrypt, make_token, read_token

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

    state = make_token(
        {"brand_id": brand.id, "shop": shop, "nonce": uuid.uuid4().hex},
        salt=STATE_SALT,
    )
    return RedirectResponse(url=build_install_url(shop, state))


@router.get("/callback", response_class=HTMLResponse)
def callback(request: Request, db: Session = Depends(get_db)):
    params = dict(request.query_params)
    shop = params.get("shop", "")
    code = params.get("code", "")
    state = params.get("state", "")

    if not is_valid_shop(shop):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid shop domain")
    if not verify_hmac(params):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "HMAC verification failed")

    data = read_token(state, salt=STATE_SALT, max_age_seconds=STATE_TTL_SECONDS)
    if not data or data.get("shop") != shop:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired state")

    brand = db.get(Brand, data["brand_id"])
    if not brand:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Brand not found")

    token_data = exchange_code_for_token(shop, code)  # {access_token, scope}

    # Enrich with shop metadata (best-effort).
    config = {"shop_domain": shop}
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

    shop_name = config.get("shop_name") or shop
    return HTMLResponse(
        f"<h2>Connected {shop_name} to {brand.name}.</h2>"
        "<p>You can close this window and return to the app.</p>"
    )
