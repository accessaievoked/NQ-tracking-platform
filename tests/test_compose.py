"""Tests for the report composer (computed metrics -> section-keyed facts)."""
from __future__ import annotations

from app.compute.money_flow import AdSpend, OrderAggregate, compute_money_flow
from app.models import ReportType
from app.reports.compose import compose_facts


def _money():
    orders = OrderAggregate(total_orders=10, gross_sales=30000, collected_orders=8,
                            collected_amount=25000, returns_amount=2000)
    ads = AdSpend(reported_spend=10000, reported_revenue=40000, connected=True)
    return compute_money_flow(orders, ads)


def test_money_flow_composer_fills_sections():
    facts = compose_facts(ReportType.money_flow_report, _money())
    assert facts is not None
    for key in ("the_money_story", "bottom_line", "the_gap", "gst_correction", "campaign_level_roas"):
        assert key in facts
    assert facts["the_money_story"]["total_orders"] == 10
    # net = collected - returns = 25000 - 2000 = 23000
    assert "Rs.23,000 reached your store" in facts["the_money_story"]["headline"]
    assert facts["the_gap"]["dashboard_roas"] == 4.0  # 40000 / 10000


def test_no_composer_returns_none():
    assert compose_facts(ReportType.weekly_performance, _money()) is None
