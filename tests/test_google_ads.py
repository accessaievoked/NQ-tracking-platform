"""Google Ads connector + connection prep + token refresh.

Everything here is offline: the Ads API is reached only through _search, so
stubbing that (or httpx.post under it) exercises the mapping, the headers and
the credential handling without a live account.
"""
from __future__ import annotations

import json

import pytest

from app.connectors.google_ads import GoogleAdsConnector, _digits


def test_digits_strips_customer_id_formatting():
    assert _digits("123-456-7890") == "1234567890"
    assert _digits(1234567890) == "1234567890"
    assert _digits(None) == ""


def test_fetch_without_creds_returns_sample():
    payload = GoogleAdsConnector().fetch(None, None)
    assert payload["source"] == "sample"
    assert payload["data"] == []


def test_to_ad_spend_converts_micros_and_sums_conversion_value():
    payload = {
        "data": [
            {"metrics": {"costMicros": "1500500000", "conversionsValue": "9000.0"}},
            {"metrics": {"costMicros": "499500000", "conversionsValue": "1000.0"}},
        ]
    }
    ads = GoogleAdsConnector().to_ad_spend(payload)
    assert ads.connected is True
    assert ads.reported_spend == 2000.0       # 1500.50 + 499.50, out of micros
    assert ads.reported_revenue == 10000.0
    assert ads.by_platform == {"google_ads": 2000.0}


def test_to_ad_spend_empty_is_zero_but_connected():
    ads = GoogleAdsConnector().to_ad_spend({"data": []})
    assert ads.reported_spend == 0.0
    assert ads.connected is True


def test_headers_carry_developer_token_and_manager_id():
    conn = GoogleAdsConnector(
        credentials={"access_token": "tok", "developer_token": "dev"},
        config={"customer_id": "123-456-7890", "login_customer_id": "999-888-7777"},
    )
    headers = conn._headers()
    assert headers["Authorization"] == "Bearer tok"
    assert headers["developer-token"] == "dev"
    # The manager id is sent bare, without the display dashes.
    assert headers["login-customer-id"] == "9998887777"


def test_login_customer_id_is_omitted_when_there_is_no_manager():
    conn = GoogleAdsConnector(
        credentials={"access_token": "tok", "developer_token": "dev"},
        config={"customer_id": "1234567890"},
    )
    assert "login-customer-id" not in conn._headers()


def test_search_flattens_stream_chunks(monkeypatch):
    """searchStream answers with a list of chunks, each holding its own rows."""
    import httpx

    class Resp:
        status_code = 200

        def json(self):
            return [
                {"results": [{"metrics": {"costMicros": "1000000"}}]},
                {"results": [{"metrics": {"costMicros": "2000000"}}]},
            ]

    monkeypatch.setattr(httpx, "post", lambda *a, **k: Resp())
    conn = GoogleAdsConnector(
        credentials={"access_token": "tok", "developer_token": "dev"},
        config={"customer_id": "1234567890"},
    )
    assert len(conn._search("SELECT 1")) == 2


def test_verify_connection_requires_full_credentials():
    with pytest.raises(ValueError):
        GoogleAdsConnector(config={"customer_id": "1"}).verify_connection()


def test_prepare_google_ads_connection_stores_oauth_and_developer_token(monkeypatch):
    from app import services

    monkeypatch.setattr(
        services, "refresh_access_token", lambda *a, **k: ("fresh_token", 3600)
    )
    monkeypatch.setattr(
        GoogleAdsConnector,
        "verify_connection",
        lambda self: {"customer_id": "1234567890", "name": "Acme", "currency": "INR"},
    )

    config, creds = services.prepare_google_ads_connection(
        {"customer_id": "123-456-7890", "login_customer_id": "999-888-7777"},
        {
            "client_id": "cid",
            "client_secret": "csec",
            "refresh_token": "1//rtok",
            "developer_token": "dev",
        },
    )
    assert creds["oauth"]["refresh_token"] == "1//rtok"
    assert creds["developer_token"] == "dev"
    assert "access_token" not in creds        # nothing expiring is persisted
    assert config["account_name"] == "Acme"


def test_prepare_google_ads_connection_requires_developer_token():
    from app import services

    with pytest.raises(ValueError, match="developer_token"):
        services.prepare_google_ads_connection(
            {"customer_id": "1"},
            {"client_id": "c", "client_secret": "s", "refresh_token": "r"},
        )


def test_prepare_google_ads_connection_requires_customer_id():
    from app import services

    with pytest.raises(ValueError, match="customer_id"):
        services.prepare_google_ads_connection({}, {"developer_token": "dev"})


def test_get_valid_google_ads_token_refreshes_and_caches(monkeypatch, db_session):
    """First call mints and persists; the second is served from the cache."""
    from app import services
    from app.models import Integration, IntegrationProvider
    from app.security import encrypt

    # Detached on purpose: the token path only reads/writes this row's
    # encrypted_tokens, so there is no need for a brand or a client behind it.
    integ = Integration(
        brand_id="brand-1",
        provider=IntegrationProvider.google_ads,
        config={"customer_id": "1234567890"},
        encrypted_tokens=encrypt(
            json.dumps(
                {
                    "oauth": {
                        "client_id": "cid",
                        "client_secret": "csec",
                        "refresh_token": "1//rtok",
                    },
                    "developer_token": "dev",
                }
            )
        ),
    )

    calls = []

    def _refresh(cid, csec, rtok):
        calls.append((cid, csec, rtok))
        return "minted_token", 3600

    monkeypatch.setattr(services, "refresh_access_token", _refresh)

    assert services.get_valid_google_ads_token(db_session, integ) == "minted_token"
    assert services.get_valid_google_ads_token(db_session, integ) == "minted_token"
    assert len(calls) == 1                     # cached, not re-minted


def test_get_valid_google_ads_token_none_without_integration(db_session):
    from app import services

    assert services.get_valid_google_ads_token(db_session, None) is None
