"""Report composer: shape deterministic compute output into a report's SECTION
facts, keyed to the section names in app/reports/specs.py.

This is the bridge between the compute layer (money_flow) and the narrator. The
narrator/template look up facts by slugified section name (e.g. "THE ROAS
REALITY" -> "the_roas_reality"), so a composer turns raw metric blocks into
exactly those keys. The LLM still only narrates — every value here comes
straight from the computed metrics.
"""
from __future__ import annotations

from typing import Any

from app.models import ReportType


def _r(x, n=2):
    return round(float(x), n) if x is not None else None


def compose_true_roas_facts(money: dict) -> dict[str, Any]:
    """Build True ROAS / Money Flow section facts from compute_money_flow output."""
    mi = money["money_in"]
    mo = money["money_out"]
    eff = money["efficiency"]

    spend = mo.get("reported_ad_spend")
    real_ad_cost = mo.get("real_ad_cost")
    net = mi["net_sales"]

    reported_roas = eff.get("reported_roas")
    real_roas = eff.get("real_roas")
    # GST-corrected ROAS = reported revenue / ad cost incl. GST = reported_roas / (1+gst).
    gst_corr = _r(reported_roas / (1 + mo.get("gst_rate", 0.18))) if reported_roas else None

    if spend is not None:
        headline = f"You spent Rs.{spend:,.0f} on ads. Rs.{net:,.0f} net revenue reached your store (net)."
    else:
        headline = f"Rs.{net:,.0f} net revenue reached your store; ad spend not connected yet."

    roas_reality = []
    if reported_roas is not None:
        roas_reality = [
            {"metric": "Dashboard-Claimed ROAS", "value": f"{reported_roas}x", "meaning": "Platform-reported, gross and pre-GST."},
            {"metric": "GST-Corrected ROAS", "value": f"{gst_corr}x" if gst_corr else "n/a", "meaning": "Reported revenue / ad cost incl. 18% GST."},
            {"metric": "True Store ROAS", "value": f"{real_roas}x" if real_roas else "n/a", "meaning": "Net Shopify revenue collected / ad cost incl. GST."},
        ]

    money_story = {
        "net_revenue_shopify": net,
        "total_ad_spend_excl_gst": spend,
        "total_ad_cost_incl_gst": real_ad_cost,
        "gross_sales": mi["gross_sales"],
    }

    table = [
        {"category": row["category"], "orders": row["orders"], "amount": row["amount"], "pct_of_gross": row["pct_of_gross"]}
        for row in mi["breakdown"] if row["kind"] in ("total", "partition")
    ]

    gap_callout = None
    if reported_roas is not None and spend is not None:
        reported_revenue = _r(reported_roas * spend)
        gap_callout = {
            "dashboard_claimed_revenue": reported_revenue,
            "shopify_net_revenue": net,
            "reported_minus_net": _r(reported_revenue - net),
            "roas_overstatement_pct": eff.get("roas_overstatement_pct"),
            "cause": "Gap driven by returns, cancellations, GST on ad spend, and unattributed orders.",
        }

    return {
        "currency": "INR",
        "headline": headline,
        "utm_coverage_check": "UTM capture not connected — campaign-level ROAS unavailable; account-level True ROAS shown.",
        "the_roas_reality": roas_reality,
        "the_money_story": money_story,
        "gap_callout": gap_callout,
        "money_in_order_reality_table": table,
    }


# report type -> composer. Money-flow family shares the True ROAS composer.
_COMPOSERS = {
    ReportType.true_roas_money_flow: compose_true_roas_facts,
    ReportType.money_flow_weekly: compose_true_roas_facts,
    ReportType.monthly_money_flow: compose_true_roas_facts,
}


def compose_facts(report_type: ReportType, money: dict) -> dict[str, Any] | None:
    """Return section-keyed facts for a report type, or None if no composer yet."""
    fn = _COMPOSERS.get(report_type)
    return fn(money) if fn else None
