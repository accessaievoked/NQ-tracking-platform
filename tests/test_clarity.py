"""Tests for the Microsoft Clarity connector (offline sample data)."""
from __future__ import annotations

from app.connectors.clarity import ClarityConnector, ClaritySummary


def test_clarity_summarize_sample():
    c = ClarityConnector()
    summary = c.summarize(c.fetch())
    assert isinstance(summary, ClaritySummary)
    assert summary.connected
    assert summary.sessions == 6420
    assert summary.bot_sessions == 310
    assert summary.distinct_users == 5180
    assert summary.pages_per_session == 2.7
    assert summary.avg_scroll_depth_pct == 58.4
    assert summary.dead_click_sessions == 512
    assert summary.rage_click_sessions == 188


def test_clarity_normalize_maps_metric_names():
    c = ClarityConnector()
    m = c.normalize(c.fetch())
    assert "Traffic" in m and "RageClickCount" in m
    assert m["Traffic"]["totalSessionCount"] == "6420"


def test_clarity_unconnected_without_token():
    # No token -> sample source; a bare summary before fetch is 'not connected'.
    assert ClaritySummary().connected is False
    payload = ClarityConnector().fetch()
    assert payload["source"] == "sample"
