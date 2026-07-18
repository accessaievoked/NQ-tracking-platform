"""Tests for Shopify Dev Dashboard token exchange + caching."""
from __future__ import annotations

import json
import time

from app import services
from app.connectors.shopify import TokenBundle, exchange_client_credentials
from app.models import Integration, IntegrationProvider
from app.security import encrypt


def _integ(db, creds, config=None):
    integ = Integration(
        brand_id="b1",
        provider=IntegrationProvider.shopify,
        config=config or {"shop_domain": "x.myshopify.com"},
        encrypted_tokens=encrypt(json.dumps(creds)),
    )
    db.add(integ)
    db.commit()
    db.refresh(integ)
    return integ


def test_exchange_parses_response(monkeypatch):
    import httpx

    class FakeResp:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"access_token": "shpat_x", "scope": "read_orders", "expires_in": 86399}

    monkeypatch.setattr(httpx, "post", lambda *a, **k: FakeResp())
    bundle = exchange_client_credentials("x.myshopify.com", "id", "sec")
    assert bundle.access_token == "shpat_x"
    assert bundle.expires_in == 86399
    assert bundle.expires_at(1000.0) == 1000.0 + 86399


def test_legacy_token_passthrough(db_session):
    integ = _integ(db_session, {"access_token": "shpat_legacy"})
    assert services.get_valid_shopify_token(db_session, integ) == "shpat_legacy"


def test_client_credentials_exchange_and_cache(db_session, monkeypatch):
    calls = {"n": 0}

    def fake_exchange(shop, cid, csecret):
        calls["n"] += 1
        return TokenBundle(access_token=f"tok{calls['n']}", scope="read_orders", expires_in=86399)

    monkeypatch.setattr(services, "exchange_client_credentials", fake_exchange)

    integ = _integ(db_session, {"client_id": "id", "client_secret": "sec"})
    t1 = services.get_valid_shopify_token(db_session, integ)
    t2 = services.get_valid_shopify_token(db_session, integ)

    assert t1 == "tok1"
    assert t2 == "tok1"       # served from cache
    assert calls["n"] == 1    # exchanged only once


def test_expired_cache_triggers_refresh(db_session, monkeypatch):
    calls = {"n": 0}

    def fake_exchange(shop, cid, csecret):
        calls["n"] += 1
        return TokenBundle(access_token=f"tok{calls['n']}", scope="", expires_in=86399)

    monkeypatch.setattr(services, "exchange_client_credentials", fake_exchange)

    creds = {
        "client_id": "id",
        "client_secret": "sec",
        "_cache": {"token": "old", "expires_at": time.time() - 10},  # already expired
    }
    integ = _integ(db_session, creds)
    assert services.get_valid_shopify_token(db_session, integ) == "tok1"
    assert calls["n"] == 1
