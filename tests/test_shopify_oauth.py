"""Tests for the Shopify OAuth authorization-code flow."""
from __future__ import annotations

import hashlib
import hmac as hmaclib

from app.config import settings
from app.connectors import shopify_oauth as oauth
from app.security import make_token


def _sign(params: dict) -> str:
    message = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    return hmaclib.new(
        settings.shopify_api_secret.encode(), message.encode(), hashlib.sha256
    ).hexdigest()


def test_is_valid_shop():
    assert oauth.is_valid_shop("three-sixty-leather.myshopify.com")
    assert not oauth.is_valid_shop("evil.com")
    assert not oauth.is_valid_shop("shop.myshopify.com.evil.com")
    assert not oauth.is_valid_shop(None)


def test_build_install_url():
    settings.shopify_api_key = "key123"
    settings.shopify_scopes = "read_orders"
    settings.shopify_redirect_uri = "https://x.test/cb"
    url = oauth.build_install_url("s.myshopify.com", "st8")
    assert url.startswith("https://s.myshopify.com/admin/oauth/authorize?")
    assert "client_id=key123" in url
    assert "scope=read_orders" in url
    assert "state=st8" in url
    assert "redirect_uri=https%3A%2F%2Fx.test%2Fcb" in url


def test_verify_hmac():
    settings.shopify_api_secret = "shhh"
    params = {"code": "abc", "shop": "s.myshopify.com", "state": "xyz", "timestamp": "123"}
    params["hmac"] = _sign(params)
    assert oauth.verify_hmac(params)
    params["code"] = "tampered"
    assert not oauth.verify_hmac(params)


def test_exchange_code_for_token(monkeypatch):
    import httpx

    class FakeResp:
        status_code = 200

        def json(self):
            return {"access_token": "shpat_live", "scope": "read_orders"}

    monkeypatch.setattr(httpx, "post", lambda *a, **k: FakeResp())
    out = oauth.exchange_code_for_token("s.myshopify.com", "code123")
    assert out["access_token"] == "shpat_live"


def test_callback_happy_path(auth_client, monkeypatch):
    settings.shopify_api_secret = "callbacksecret"

    brand = auth_client.post("/api/brands", json={"name": "Leather"}).json()
    brand_id = brand["id"]

    shop = "three-sixty-leather.myshopify.com"
    state = make_token(
        {"brand_id": brand_id, "shop": shop, "nonce": "n1"}, salt=oauth.STATE_SALT
    )

    # Avoid real network in the callback.
    monkeypatch.setattr(
        "app.api.shopify_oauth.exchange_code_for_token",
        lambda s, c: {"access_token": "shpat_live", "scope": "read_orders"},
    )
    monkeypatch.setattr(
        "app.connectors.shopify.ShopifyConnector.verify_connection",
        lambda self: {"name": "Three Sixty Leather", "currency": "INR"},
    )

    params = {"code": "authcode", "shop": shop, "state": state, "timestamp": "1700000000"}
    params["hmac"] = _sign(params)

    r = auth_client.get("/api/integrations/shopify/callback", params=params)
    assert r.status_code == 200, r.text
    assert "Connected" in r.text

    # Integration is now connected for the brand.
    integs = auth_client.get(f"/api/brands/{brand_id}/integrations").json()
    shopify = [i for i in integs if i["provider"] == "shopify"][0]
    assert shopify["status"] == "connected"


def test_callback_rejects_bad_hmac(auth_client):
    settings.shopify_api_secret = "callbacksecret"
    params = {
        "code": "x",
        "shop": "three-sixty-leather.myshopify.com",
        "state": "whatever",
        "hmac": "deadbeef",
    }
    r = auth_client.get("/api/integrations/shopify/callback", params=params)
    assert r.status_code == 401
