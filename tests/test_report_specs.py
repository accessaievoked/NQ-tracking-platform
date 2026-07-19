"""Tests for the adverti-style report spec registry and generic narrator.

These run fully offline (no ANTHROPIC_API_KEY): the narrator falls back to a
deterministic template, so we can assert structure without hitting Claude.
"""
from __future__ import annotations

import pytest

from app.models import ReportType
from app.reports.generator import _fallback_report, _slug
from app.reports.specs import SPECS, get_spec, has_spec

# Every adverti report type the product spec calls for.
EXPECTED_TYPES = {
    ReportType.cpa_spike_alert,
    ReportType.creative_fatigue_alert,
    ReportType.daily_spend_alert,
    ReportType.wasted_spend_alert,
    ReportType.cod_rto_weekly,
    ReportType.creative_health_weekly,
    ReportType.money_flow_weekly,
    ReportType.platform_compare_weekly,
    ReportType.weekly_action_plan,
    ReportType.monthly_customer_quality,
    ReportType.monthly_money_flow,
    ReportType.monthly_performance,
    ReportType.monthly_product_pl,
    ReportType.account_audit,
    ReportType.meta_ads_kill_strategy,
    ReportType.campaign_attribution,
    ReportType.ad_strategy,
    ReportType.true_roas_money_flow,
    ReportType.product_pl,
    ReportType.campaign_revamp,
    ReportType.meta_ads_performance,
}


def test_all_expected_report_types_registered():
    assert EXPECTED_TYPES <= set(SPECS), "missing specs: " + str(EXPECTED_TYPES - set(SPECS))


@pytest.mark.parametrize("rt", sorted(SPECS, key=lambda k: k.value))
def test_every_spec_has_six_sections_and_builds_a_prompt(rt):
    spec = get_spec(rt)
    assert len(spec.sections) == 6, f"{rt.value} should have 6 sections"
    prompt = spec.system_prompt()
    assert spec.title in prompt
    assert "NEVER invent" in prompt  # guardrail present
    for name in spec.section_names:
        assert name in prompt


def test_slug_matches_section_convention():
    assert _slug("METRICS BLOCK") == "metrics_block"
    assert _slug("TOP 3 FATIGUED CREATIVES") == "top_3_fatigued_creatives"
    assert _slug("OWNER/DEADLINE") == "owner_deadline"


def test_fallback_narrative_renders_facts_under_sections():
    facts = {
        "currency": "INR",
        "headline": "CPA up 62% on Summer Sale.",
        "metrics_block": [
            {"metric": "CPA", "baseline_30d": 420, "current": 680, "deviation_pct": 62.0},
        ],
        "recommended_action": "Pause the fatigued ad; save ~Rs. 9,000.",
    }
    # Test the deterministic template directly so the assertion holds regardless
    # of whether ANTHROPIC_API_KEY is set (with a key, the narrator uses Claude).
    spec = get_spec(ReportType.cpa_spike_alert)
    md = _fallback_report(spec, "Acme", "Jul 2026", facts)
    # Title + every section heading present.
    assert "Acme — CPA Spike Alert" in md
    for name in get_spec(ReportType.cpa_spike_alert).section_names:
        assert f"## {name}" in md
    # Supplied facts surfaced; missing ones flagged, never invented.
    assert "CPA up 62%" in md
    assert "62.0" in md
    assert "no `trigger_condition` in facts" in md


def test_money_flow_is_not_treated_as_spec_backed():
    # money_flow keeps its dedicated compute pipeline, not the generic path.
    assert not has_spec(ReportType.money_flow)
