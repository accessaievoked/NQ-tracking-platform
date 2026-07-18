"""Tests for the Meta Ads connector."""
from __future__ import annotations

from app.connectors.meta_ads import MetaAdsConnector, _normalize_account


def test_normalize_account():
    assert _normalize_account("123") == "act_123"
    assert _normalize_account("act_123") == "act_123"


def test_fetch_without_creds_returns_sample():
    conn = MetaAdsConnector()
    payload = conn.fetch(None, None)
    assert payload["source"] == "sample"
    assert payload["data"] == []


def test_to_ad_spend_sums_spend_and_purchase_value():
    conn = MetaAdsConnector()
    payload = {
        "data": [
            {
                "spend": "1500.50",
                "action_values": [
                    {"action_type": "omni_purchase", "value": "9000.00"},
                    {"action_type": "landing_page_view", "value": "50.00"},
                ],
            }
        ]
    }
    ads = conn.to_ad_spend(payload)
    assert ads.connected is True
    assert ads.reported_spend == 1500.5
    assert ads.reported_revenue == 9000.0        # non-purchase actions ignored
    assert ads.by_platform == {"meta_ads": 1500.5}


def test_to_ad_spend_empty_is_zero_but_connected():
    ads = MetaAdsConnector().to_ad_spend({"data": []})
    assert ads.reported_spend == 0.0
    assert ads.connected is True
