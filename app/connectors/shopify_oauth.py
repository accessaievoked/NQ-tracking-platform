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

Which app: custom-distribution apps are locked to a single store, so every
client store has its own app. Each function takes an optional ShopifyAppCreds;
omitted, it falls back to the default app in SHOPIFY_API_KEY/SECRET.
"""
from __future__ import annotations

import hashlib
import hmac
import re
from dataclasses import dataclass
from urllib.parse import urlencode

from app.config import settings

SHOPIFY_API_VERSION = "2024-10"
_SHOP_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9-]*\.myshopify\.com$")

# Signed-state settings for the OAuth install/callback handshake.
STATE_SALT = "shopify-oauth"
STATE_TTL_SECONDS = 600


@dataclass(frozen=True)
class ShopifyAppCreds:
    client_id: str
    client_secret: str


def default_app() -> ShopifyAppCreds:
    """The app configured in the environment (SHOPIFY_API_KEY / SECRET)."""
    return ShopifyAppCreds(settings.shopify_api_key, settings.shopify_api_secret)


def is_valid_shop(shop: str | None) -> bool:
    """Guard against open-redirect / injection via the shop parameter."""
    return bool(shop and _SHOP_RE.match(shop))


def redirect_uri() -> str:
    if settings.shopify_redirect_uri:
        return settings.shopify_redirect_uri
    return f"{settings.app_base_url}/api/integrations/shopify/callback"


def build_install_url(shop: str, state: str, app: ShopifyAppCreds | None = None) -> str:
    app = app or default_app()
    params = {
        "client_id": app.client_id,
        "scope": settings.shopify_scopes,
        "redirect_uri": redirect_uri(),
        "state": state,
    }
    return f"https://{shop}/admin/oauth/authorize?{urlencode(params)}"


def verify_hmac(params: dict[str, str], app: ShopifyAppCreds | None = None) -> bool:
    """Verify the HMAC Shopify appends to the callback query string.

    Shopify signs with the secret of the app that was installed, so this must be
    checked against that app — not whichever app is the default.
    """
    app = app or default_app()
    if not app.client_secret:
        return False
    provided = params.get("hmac", "")
    message = "&".join(
        f"{k}={v}"
        for k, v in sorted(params.items())
        if k not in ("hmac", "signature")
    )
    digest = hmac.new(
        app.client_secret.encode(), message.encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(digest, provided)


def exchange_code_for_token(shop: str, code: str, app: ShopifyAppCreds | None = None) -> dict:
    """Exchange the authorization code for an offline access token.

    Returns Shopify's JSON: {"access_token": "...", "scope": "..."}.
    """
    import httpx

    app = app or default_app()
    resp = httpx.post(
        f"https://{shop}/admin/oauth/access_token",
        json={
            "client_id": app.client_id,
            "client_secret": app.client_secret,
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
