"""GA4 connected with a service-account key — the shape the onboarding guide produces.

The client downloads a JSON key and grants that service account Viewer on the
property, so nothing about the connection expires and no human ever re-pastes
anything. The runtime already minted tokens from such a key; these cover the
connect path that accepts one.
"""
from __future__ import annotations

import json

import pytest

from app.connectors.ga4 import GA4Connector

KEY = {
    "type": "service_account",
    "project_id": "nq-client",
    "client_email": "nq@nq-client.iam.gserviceaccount.com",
    "private_key": "-----BEGIN PRIVATE KEY-----\nstub\n-----END PRIVATE KEY-----\n",
    "token_uri": "https://oauth2.googleapis.com/token",
}


@pytest.fixture()
def offline(monkeypatch):
    """Neither minting nor verification should touch the network."""
    from app import services

    monkeypatch.setattr(services, "mint_access_token", lambda *a, **k: ("minted", 3600))
    monkeypatch.setattr(
        GA4Connector,
        "verify_connection",
        lambda self: {"property_id": self.config.get("property_id"), "name": "p"},
    )


def test_service_account_key_is_stored_verbatim(offline):
    from app import services

    config, creds = services.prepare_ga4_connection(
        {"property_id": "264779386"}, {"service_account": KEY}
    )
    assert config["property_id"] == "264779386"
    assert creds == {"service_account": KEY}
    assert "access_token" not in creds      # nothing expiring is persisted


def test_service_account_key_accepted_as_pasted_json_text(offline):
    """The UI collects a downloaded .json file, so a string is just as likely."""
    from app import services

    _, creds = services.prepare_ga4_connection(
        {"property_id": "264779386"}, {"service_account": json.dumps(KEY)}
    )
    assert creds["service_account"]["client_email"] == KEY["client_email"]


def test_service_account_wins_over_a_stale_pasted_token(offline):
    from app import services

    _, creds = services.prepare_ga4_connection(
        {"property_id": "1"},
        {"service_account": KEY, "access_token": "expires_in_an_hour"},
    )
    assert "service_account" in creds
    assert "access_token" not in creds


def test_malformed_service_account_json_is_rejected():
    from app import services

    with pytest.raises(ValueError, match="not valid JSON"):
        services.prepare_ga4_connection(
            {"property_id": "1"}, {"service_account": "{not json"}
        )


def test_service_account_details_page_instead_of_the_key_is_rejected():
    """A common mix-up: the account's page has client_email but no private_key."""
    from app import services

    with pytest.raises(ValueError, match="private_key"):
        services.prepare_ga4_connection(
            {"property_id": "1"},
            {"service_account": {"client_email": "nq@x.iam.gserviceaccount.com"}},
        )


def test_minted_token_is_what_verifies_the_property(monkeypatch):
    """The key is proven end to end: mint, then read the property with it."""
    from app import services

    monkeypatch.setattr(services, "mint_access_token", lambda *a, **k: ("minted", 3600))
    seen = {}

    def _verify(self):
        seen["token"] = self.credentials.get("access_token")
        return {"property_id": "1", "name": "p"}

    monkeypatch.setattr(GA4Connector, "verify_connection", _verify)
    services.prepare_ga4_connection({"property_id": "1"}, {"service_account": KEY})
    assert seen["token"] == "minted"
