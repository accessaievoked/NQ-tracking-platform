"""Tests for the report spec registry and generic narrator.

Run fully offline (conftest clears ANTHROPIC_API_KEY): the narrator falls back
to a deterministic template, so we assert structure without hitting Claude.
"""
from __future__ import annotations

import pytest

from app.models import ReportType
from app.reports.generator import _fallback_report, _slug
from app.reports.specs import SPECS, get_spec, has_spec

# The 31 report types the account-audit suite defines.
EXPECTED_TYPES = {
    ReportType.account_audit, ReportType.weekly_performance, ReportType.cpa_diagnosis,
    ReportType.day_of_week, ReportType.wasted_spend, ReportType.budget_reallocation,
    ReportType.scaling_opportunities, ReportType.diminishing_returns, ReportType.creative_fatigue,
    ReportType.ad_ranking, ReportType.messaging_angles, ReportType.creative_briefs,
    ReportType.audience_analysis, ReportType.demographic_breakdown, ReportType.retargeting_audit,
    ReportType.geographic_performance, ReportType.advantage_plus_readiness, ReportType.placement_analysis,
    ReportType.search_terms_audit, ReportType.shopping_pmax_products, ReportType.impression_share,
    ReportType.keyword_opportunities, ReportType.weekly_action_plan, ReportType.platform_comparison,
    ReportType.cross_platform_budget, ReportType.funnel_mapping, ReportType.money_flow_report,
    ReportType.product_pl, ReportType.reality_check, ReportType.cod_prepaid, ReportType.customer_quality,
}


def test_all_expected_report_types_registered():
    assert EXPECTED_TYPES == set(SPECS), "spec set mismatch: " + str(EXPECTED_TYPES ^ set(SPECS))


@pytest.mark.parametrize("rt", sorted(SPECS, key=lambda k: k.value))
def test_every_spec_builds_a_prompt(rt):
    spec = get_spec(rt)
    assert 3 <= len(spec.sections) <= 8, f"{rt.value} has {len(spec.sections)} sections"
    prompt = spec.system_prompt()
    assert spec.title in prompt
    assert "NEVER invent" in prompt
    for name in spec.section_names:
        assert name in prompt


def test_slug_matches_section_convention():
    assert _slug("THE MONEY STORY") == "the_money_story"
    assert _slug("TOP 15 CITIES") == "top_15_cities"
    assert _slug("GST CORRECTION") == "gst_correction"


def test_fallback_narrative_renders_sections():
    spec = get_spec(ReportType.money_flow_report)
    facts = {"bottom_line": "For every Rs.1 spent, Rs.0.9 reached the store.",
             "the_gap": {"dashboard_roas": 3.0, "true_roas": 1.8}}
    md = _fallback_report(spec, "Acme", "Jul 2026", facts)
    assert "Acme — Money Flow Report" in md
    for name in spec.section_names:
        assert f"## {name}" in md
    assert "For every Rs.1 spent" in md


def test_get_spec_raises_for_unknown():
    # A provider enum value is not a report type -> KeyError via get_spec.
    class Fake:
        value = "nope"
    with pytest.raises(KeyError):
        get_spec(Fake())
