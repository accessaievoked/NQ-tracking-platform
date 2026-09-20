"""Meta token longevity, and ad spend summed across platforms.

Meta gives no refresh token — a long-lived user token runs ~60 days and has to
be re-exchanged while still valid. These cover that renewal and the multi-
platform AdSpend the Money Flow report is built from. All offline.
"""
from __future__ import annotations

import json
import time

import pytest

from app.compute.money_flow import AdSpend
from app.connectors.meta_ads import LONG_LIVED_TTL, MetaAdsConnector


def _integration(creds: dict, provider=None):
    from app.models import Integration, IntegrationProvider
    from app.security import encrypt

    return Integration(
        brand_id="brand-1",
        provider=provider or IntegrationProvider.meta_ads,
        config={"ad_account_id": "act_123"},
        encrypted_tokens=encrypt(json.dumps(creds)),
    )


# --- exchanging ------------------------------------------------------------

def test_exchange_long_lived_token_defaults_ttl_when_graph_omits_it(monkeypatch):
    """Some token types answer expires_in=0, meaning "no stated expiry"."""
    import httpx
    from app.connectors import meta_ads

    class Resp:
        status_code = 200

        def json(self):
            return {"access_token": "long_lived", "expires_in": 0}

    monkeypatch.setattr(httpx, "get", lambda *a, **k: Resp())
    token, expires_in = meta_ads.exchange_long_lived_token("app", "secret", "short")
    assert token == "long_lived"
    assert expires_in == LONG_LIVED_TTL


def test_exchange_long_lived_token_raises_on_error(monkeypatch):
    import httpx
    from app.connectors import meta_ads

    class Resp:
        status_code = 400
        text = "bad app secret"

    monkeypatch.setattr(httpx, "get", lambda *a, **k: Resp())
    with pytest.raises(RuntimeError, match="Meta token exchange failed"):
        meta_ads.exchange_long_lived_token("app", "secret", "short")


def test_prepare_meta_connection_exchanges_and_stores_app_creds(monkeypatch):
    from app import services

    monkeypatch.setattr(
        services, "exchange_long_lived_token", lambda *a: ("long_lived", 5_184_000)
    )
    monkeypatch.setattr(
        MetaAdsConnector,
        "verify_connection",
        lambda self: {"name": "Acme Ads", "currency": "INR"},
    )

    config, creds = services.prepare_meta_connection(
        {"ad_account_id": "act_123"},
        {"app_id": "app", "app_secret": "secret", "access_token": "pasted"},
    )
    assert creds["access_token"] == "long_lived"   # the pasted one is not kept
    assert creds["app_id"] == "app"
    assert creds["expires_at"] > time.time()
    assert config["account_name"] == "Acme Ads"


def test_prepare_meta_connection_without_app_creds_keeps_token_as_is(monkeypatch):
    """Still connectable, but nothing can renew it — that's the trade-off."""
    from app import services

    monkeypatch.setattr(
        MetaAdsConnector, "verify_connection", lambda self: {"name": "Acme"}
    )
    _, creds = services.prepare_meta_connection(
        {"ad_account_id": "act_123"}, {"access_token": "pasted"}
    )
    assert creds == {"access_token": "pasted"}
    assert "expires_at" not in creds


def test_prepare_meta_connection_requires_account_and_token():
    from app import services

    with pytest.raises(ValueError, match="ad_account_id"):
        services.prepare_meta_connection({}, {"access_token": "t"})
    with pytest.raises(ValueError, match="access_token"):
        services.prepare_meta_connection({"ad_account_id": "act_1"}, {})


# --- renewing --------------------------------------------------------------

def test_get_valid_meta_token_renews_inside_the_buffer(monkeypatch, db_session):
    from app import services

    integ = _integration(
        {
            "access_token": "old",
            "app_id": "app",
            "app_secret": "secret",
            "expires_at": time.time() + 60,     # inside TOKEN_REFRESH_BUFFER
        }
    )
    monkeypatch.setattr(
        services, "exchange_long_lived_token", lambda *a: ("renewed", LONG_LIVED_TTL)
    )
    assert services.get_valid_meta_token(db_session, integ) == "renewed"

    # The new token is persisted, so the next call serves it from storage.
    stored = json.loads(services.decrypt(integ.encrypted_tokens))
    assert stored["access_token"] == "renewed"
    assert stored["expires_at"] > time.time() + LONG_LIVED_TTL - 60


def test_get_valid_meta_token_leaves_a_fresh_token_alone(monkeypatch, db_session):
    from app import services

    integ = _integration(
        {
            "access_token": "fresh",
            "app_id": "app",
            "app_secret": "secret",
            "expires_at": time.time() + LONG_LIVED_TTL,
        }
    )

    def _boom(*a):
        raise AssertionError("should not renew a token with weeks left")

    monkeypatch.setattr(services, "exchange_long_lived_token", _boom)
    assert services.get_valid_meta_token(db_session, integ) == "fresh"


def test_get_valid_meta_token_survives_a_failed_renewal(monkeypatch, db_session):
    """A renewal outage shouldn't kill a token that may still have life in it."""
    from app import services

    integ = _integration(
        {
            "access_token": "old",
            "app_id": "app",
            "app_secret": "secret",
            "expires_at": time.time() + 60,
        }
    )

    def _fail(*a):
        raise RuntimeError("Meta is down")

    monkeypatch.setattr(services, "exchange_long_lived_token", _fail)
    assert services.get_valid_meta_token(db_session, integ) == "old"


def test_get_valid_meta_token_without_app_creds_serves_stored_token(db_session):
    from app import services

    integ = _integration({"access_token": "legacy"})
    assert services.get_valid_meta_token(db_session, integ) == "legacy"


def test_get_valid_meta_token_none_without_integration(db_session):
    from app import services

    assert services.get_valid_meta_token(db_session, None) is None


# --- summing across platforms ---------------------------------------------

def _stub_spend(monkeypatch, meta: AdSpend, google: AdSpend):
    from app import services

    monkeypatch.setattr(services, "get_meta_ad_spend", lambda *a: meta)
    monkeypatch.setattr(services, "get_google_ads_spend", lambda *a: google)


def test_get_ad_spend_sums_both_platforms(monkeypatch, db_session):
    from app import services

    _stub_spend(
        monkeypatch,
        AdSpend(120000.0, 480000.0, {"meta_ads": 120000.0}, True),
        AdSpend(80000.0, 240000.0, {"google_ads": 80000.0}, True),
    )
    ads = services.get_ad_spend(db_session, "brand-1", None, None)
    assert ads.connected is True
    assert ads.reported_spend == 200000.0
    assert ads.reported_revenue == 720000.0
    assert ads.by_platform == {"meta_ads": 120000.0, "google_ads": 80000.0}


def test_get_ad_spend_reports_one_platform_when_only_one_is_connected(
    monkeypatch, db_session
):
    """Meta-only brands still get a ROAS — not a withheld one."""
    from app import services

    _stub_spend(
        monkeypatch,
        AdSpend(120000.0, 480000.0, {"meta_ads": 120000.0}, True),
        AdSpend(connected=False),
    )
    ads = services.get_ad_spend(db_session, "brand-1", None, None)
    assert ads.connected is True
    assert ads.reported_spend == 120000.0
    assert ads.by_platform == {"meta_ads": 120000.0}


def test_get_ad_spend_is_unconnected_when_no_platform_answers(monkeypatch, db_session):
    from app import services

    _stub_spend(monkeypatch, AdSpend(connected=False), AdSpend(connected=False))
    ads = services.get_ad_spend(db_session, "brand-1", None, None)
    assert ads.connected is False
    assert ads.reported_spend == 0.0
    assert ads.by_platform == {}
