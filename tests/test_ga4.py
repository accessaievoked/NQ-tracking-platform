"""Tests for the GA4 connector."""
from __future__ import annotations

from app.connectors.ga4 import GA4Connector


def test_fetch_without_creds_returns_sample():
    payload = GA4Connector().fetch(None, None)
    assert payload["source"] == "sample"
    assert payload["report"]["rows"]


def test_summarize_maps_headers_to_values():
    conn = GA4Connector()
    payload = {
        "report": {
            "metricHeaders": [{"name": "sessions"}, {"name": "purchaseRevenue"}],
            "rows": [{"metricValues": [{"value": "1000"}, {"value": "250000"}]}],
        }
    }
    summary = conn.summarize(payload)
    assert summary == {"sessions": 1000.0, "purchaseRevenue": 250000.0}


def test_summarize_handles_empty_report():
    summary = GA4Connector().summarize({"report": {"metricHeaders": [], "rows": []}})
    assert summary == {}


def test_sample_summarize_has_expected_metrics():
    conn = GA4Connector()
    summary = conn.summarize(conn.fetch(None, None))
    assert summary["sessions"] == 12450.0
    assert summary["purchaseRevenue"] == 1863500.0


def test_prepare_ga4_connection_stores_oauth_refresh_token(monkeypatch):
    """A refresh-token trio is verified and stored as durable oauth creds."""
    from app import services

    monkeypatch.setattr(
        services, "refresh_access_token", lambda *a, **k: ("fresh_token", 3600)
    )
    monkeypatch.setattr(
        GA4Connector, "verify_connection", lambda self: {"property_id": "1", "name": "p"}
    )

    config, creds = services.prepare_ga4_connection(
        {"property_id": "264779386"},
        {"client_id": "cid", "client_secret": "csec", "refresh_token": "1//rtok"},
    )
    assert config["property_id"] == "264779386"
    assert creds == {
        "oauth": {"client_id": "cid", "client_secret": "csec", "refresh_token": "1//rtok"}
    }
    assert "access_token" not in creds  # nothing expiring is persisted


def test_prepare_ga4_connection_requires_creds():
    from app import services

    import pytest

    with pytest.raises(ValueError):
        services.prepare_ga4_connection({"property_id": "1"}, {})
