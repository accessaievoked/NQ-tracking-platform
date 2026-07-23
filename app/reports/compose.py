"""Report composer: shape deterministic compute output into a report's SECTION
facts, keyed to the section names in app/reports/specs.py.

Bridges the compute layer (money_flow) and the narrator: the narrator/template
look up facts by slugified section name (e.g. "THE GAP" -> "the_gap"), so a
composer turns raw metric blocks into exactly those keys. The LLM only narrates
— every value here comes straight from the computed metrics.
"""
from __future__ import annotations

from typing import Any

from app.models import ReportType


def _r(x, n=2):
    return round(float(x), n) if x is not None else None


def compose_money_flow_facts(money: dict) -> dict[str, Any]:
    """Build Money Flow Report section facts from compute_money_flow() output.
    (order_health is added by the service; actions are written by the AI.)"""
    mi = money["money_in"]
    mo = money["money_out"]
    eff = money["efficiency"]
    gst = mo.get("gst_rate", 0.18)

    spend = mo.get("reported_ad_spend")
    real = mo.get("real_ad_cost")
    net = mi["net_sales"]
    gross = mi["gross_sales"]
    reported_roas = eff.get("reported_roas")
    real_roas = eff.get("real_roas")
    gst_corr = _r(reported_roas / (1 + gst)) if reported_roas else None
    gst_on_spend = _r(real - spend) if (real is not None and spend is not None) else None

    money_in = [
        {"category": r["category"], "orders": r["orders"], "amount": r["amount"], "pct_of_gross": r["pct_of_gross"]}
        for r in mi["breakdown"] if r["kind"] in ("total", "partition")
    ]
    headline = (
        f"You spent Rs.{spend:,.0f} on ads. Rs.{net:,.0f} reached your store (net)."
        if spend is not None
        else f"Rs.{net:,.0f} reached your store; ad spend not connected yet."
    )

    bottom_line = None
    if real:
        bottom_line = f"For every Rs.1 spent (incl. GST), Rs.{_r(net / real):.2f} in real revenue reached your store."

    the_gap = None
    if reported_roas is not None:
        the_gap = {
            "dashboard_roas": reported_roas,
            "true_roas": real_roas,
            "roas_overstatement_pct": eff.get("roas_overstatement_pct"),
            "cause": "Gap driven by returns, cancellations, and GST on ad spend.",
        }

    gst_correction = [
        {"metric": "Revenue", "platform": gross, "gst_corrected": _r(gross / (1 + gst)), "shopify_verified": net},
        {"metric": "Ad Spend", "platform": spend, "gst_corrected": real, "shopify_verified": None},
        {"metric": "ROAS", "platform": reported_roas, "gst_corrected": gst_corr, "shopify_verified": real_roas},
    ]

    reported_revenue = _r(reported_roas * spend) if (reported_roas and spend) else None
    gap_amount = _r(reported_revenue - net) if reported_revenue is not None else None

    return {
        "currency": "INR",
        # Structured blocks for the frontend's card layout.
        "hero": {"headline": headline, "reported_roas": reported_roas,
                 "true_roas": real_roas, "gap_amount": gap_amount},
        "headline_metrics": {"net_revenue": net, "total_ad_spend": spend,
                             "total_ad_cost": real, "gross_sales": gross},
        # Section-keyed facts for the narrator + template.
        "the_money_story": {
            "headline": headline,
            "total_orders": mi["total_orders"],
            "gross_sales": gross,
            "money_in": money_in,
            "money_out": {"ad_spend_reported": spend, "gst_on_ad_spend": gst_on_spend, "total_actual_ad_cost": real},
        },
        "bottom_line": bottom_line,
        "the_gap": the_gap,
        "gst_correction": gst_correction,
        "campaign_level_roas": "UTM tracking not connected — campaign-level ROAS unavailable; account-level shown.",
    }


# report type -> composer (only the Money Flow report has a live composer today).
_COMPOSERS = {
    ReportType.money_flow_report: compose_money_flow_facts,
}


def compose_facts(report_type: ReportType, money: dict) -> dict[str, Any] | None:
    """Return section-keyed facts for a report type, or None if no composer yet."""
    fn = _COMPOSERS.get(report_type)
    return fn(money) if fn else None
