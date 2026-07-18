"""Shopify OAuth 2.0 authorization-code flow.

This is the correct way to access *arbitrary merchant stores* (client stores
that aren't in your Dev Dashboard org, where the client-credentials grant is
rejected with `shop_not_permitted`).

Flow:
  1. Redirect the merchant to the authorize URL (build_install_url).
  2. Merchant approves; Shopify redirects back to our callback with
     ?code&shop&state&hmac.
  3. Verify the HMAC (proves the request came from Shopify) and our signed
     state (proves we started it), then exchange the code for an offline
     access token (exchange_code_for_token).

The resulting offline token is long-lived and stored like any other Shopify
credential ({"access_token": ...}); the existing token resolver serves it
directly.
"""
from __future__ import annotations

import hashlib
import hmac
import re
from urllib.parse import urlencode

from app.config import settings

SHOPIFY_API_VERSION = "2024-10"
_SHOP_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9-]*\.myshopify\.com$")

# Signed-state settings for the OAuth install/callback handshake.
STATE_SALT = "shopify-oauth"
STATE_TTL_SECONDS = 600


def is_valid_shop(shop: str | None) -> bool:
    """Guard against open-redirect / injection via the shop parameter."""
    return bool(shop and _SHOP_RE.match(shop))


def redirect_uri() -> str:
    if settings.shopify_redirect_uri:
        return settings.shopify_redirect_uri
    return f"{settings.app_base_url}/api/integrations/shopify/callback"


def build_install_url(shop: str, state: str) -> str:
    params = {
        "client_id": settings.shopify_api_key,
        "scope": settings.shopify_scopes,
        "redirect_uri": redirect_uri(),
        "state": state,
    }
    return f"https://{shop}/admin/oauth/authorize?{urlencode(params)}"


def verify_hmac(params: dict[str, str]) -> bool:
    """Verify the HMAC Shopify appends to the callback query string."""
    provided = params.get("hmac", "")
    message = "&".join(
        f"{k}={v}"
        for k, v in sorted(params.items())
        if k not in ("hmac", "signature")
    )
    digest = hmac.new(
        settings.shopify_api_secret.encode(), message.encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(digest, provided)


def exchange_code_for_token(shop: str, code: str) -> dict:
    """Exchange the authorization code for an offline access token.

    Returns Shopify's JSON: {"access_token": "...", "scope": "..."}.
    """
    import httpx

    resp = httpx.post(
        f"https://{shop}/admin/oauth/access_token",
        json={
            "client_id": settings.shopify_api_key,
            "client_secret": settings.shopify_api_secret,
            "code": code,
        },
        headers={"Accept": "application/json"},
        timeout=20,
    )
    if resp.status_code >= 400:
        raise RuntimeError(
            f"Shopify code exchange failed ({resp.status_code}): {resp.text}"
        )
    return resp.json()
