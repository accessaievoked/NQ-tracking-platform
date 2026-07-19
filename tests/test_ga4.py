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
