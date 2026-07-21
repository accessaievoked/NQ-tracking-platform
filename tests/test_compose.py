"""Tests for the report composer (computed metrics -> section-keyed facts)."""
from __future__ import annotations

from app.compute.money_flow import AdSpend, OrderAggregate, compute_money_flow
from app.models import ReportType
from app.reports.compose import compose_facts
from app.reports.specs import get_spec


def _money():
    orders = OrderAggregate(total_orders=10, gross_sales=30000, collected_orders=8,
                            collected_amount=25000, returns_amount=2000)
    ads = AdSpend(reported_spend=10000, reported_revenue=40000, connected=True)
    return compute_money_flow(orders, ads)


def _slug(name: str) -> str:
    slug = "".join(c if c.isalnum() else "_" for c in name.lower())
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug.strip("_")


def test_composer_fills_every_section_key():
    facts = compose_facts(ReportType.true_roas_money_flow, _money())
    assert facts is not None
    for name in get_spec(ReportType.true_roas_money_flow).section_names:
        assert _slug(name) in facts, f"composer missing section fact: {_slug(name)}"


def test_composer_numbers_from_compute():
    facts = compose_facts(ReportType.true_roas_money_flow, _money())
    assert "You spent Rs.10,000 on ads." in facts["headline"]
    assert facts["the_money_story"]["net_revenue_shopify"] == 23000.0   # 25000 - 2000
    assert facts["the_money_story"]["total_ad_cost_incl_gst"] == 11800.0  # 10000 * 1.18
    values = [c["metric"] for c in facts["the_roas_reality"]]
    assert "Dashboard-Claimed ROAS" in values and "True Store ROAS" in values


def test_no_composer_returns_none():
    assert compose_facts(ReportType.cpa_spike_alert, _money()) is None
