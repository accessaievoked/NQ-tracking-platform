"""Deterministic Money Flow computation.

This module is the heart of the reporting engine and the reason reports can be
trusted: *the LLM never does arithmetic*. All figures below are computed here,
in code, and only then handed to the narrative generator.

Methodology (documented + configurable so it can be defended to a client):

    gross_sales        = sum of placed order totals (amount charged, post-discount)
    cancelled          = orders with a cancellation, and their value
    returns            = refunded / reversed amount across all orders
    discounts          = total discounts granted (shown for insight)
    net_sales          = gross_sales - cancelled_value - returns
                         ("revenue that actually reached the store")

    real_ad_cost       = reported_ad_spend * (1 + gst_rate)
                         (Indian ad platforms bill GST on top of spend)
    real_roas          = net_sales / real_ad_cost
    reported_roas      = platform_reported_revenue / reported_ad_spend
                         (what the ad dashboards claim)
    roas_overstatement = (reported_roas - real_roas) / reported_roas

Every assumption is explicit and every input is passed in, so unit tests fully
pin the behaviour without any external API.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _round(x: float, ndigits: int = 2) -> float:
    return round(float(x), ndigits)


def _pct(part: float, whole: float) -> float:
    return _round((part / whole * 100.0) if whole else 0.0)


@dataclass
class OrderAggregate:
    """Aggregated Shopify order facts for a period (already normalized)."""

    total_orders: int = 0
    gross_sales: float = 0.0
    fulfilled_orders: int = 0
    fulfilled_amount: float = 0.0
    partial_orders: int = 0
    partial_amount: float = 0.0
    cancelled_orders: int = 0
    cancelled_amount: float = 0.0
    returns_amount: float = 0.0
    discounts_amount: float = 0.0


@dataclass
class AdSpend:
    """Ad-platform spend + the revenue the platform *claims* it drove."""

    reported_spend: float = 0.0
    reported_revenue: float = 0.0  # platform-attributed revenue (for dashboard ROAS)
    by_platform: dict[str, float] = field(default_factory=dict)


def aggregate_orders(orders: list[dict[str, Any]]) -> OrderAggregate:
    """Build an OrderAggregate from a list of normalized order dicts.

    Expected normalized order fields (see connectors/shopify.normalize):
        total_price:      float  (amount charged, after discounts)
        total_discounts:  float
        total_refunded:   float
        is_cancelled:     bool
        fulfillment:      "fulfilled" | "partial" | "unfulfilled"
    """
    agg = OrderAggregate()
    for o in orders:
        total = float(o.get("total_price", 0) or 0)
        agg.total_orders += 1
        agg.gross_sales += total
        agg.discounts_amount += float(o.get("total_discounts", 0) or 0)
        agg.returns_amount += float(o.get("total_refunded", 0) or 0)

        if o.get("is_cancelled"):
            agg.cancelled_orders += 1
            agg.cancelled_amount += total
            continue

        fulfillment = o.get("fulfillment", "unfulfilled")
        if fulfillment == "fulfilled":
            agg.fulfilled_orders += 1
            agg.fulfilled_amount += total
        else:  # partial or unfulfilled/pending
            agg.partial_orders += 1
            agg.partial_amount += total

    # tidy rounding
    for f in (
        "gross_sales",
        "fulfilled_amount",
        "partial_amount",
        "cancelled_amount",
        "returns_amount",
        "discounts_amount",
    ):
        setattr(agg, f, _round(getattr(agg, f)))
    return agg


def compute_money_flow(
    orders: OrderAggregate,
    ads: AdSpend,
    gst_rate: float = 0.18,
) -> dict[str, Any]:
    """Return a fully computed, JSON-serializable Money Flow metrics block."""
    gross = orders.gross_sales
    net_sales = _round(gross - orders.cancelled_amount - orders.returns_amount)

    real_ad_cost = _round(ads.reported_spend * (1 + gst_rate))
    real_roas = _round(net_sales / real_ad_cost, 2) if real_ad_cost else 0.0
    reported_roas = (
        _round(ads.reported_revenue / ads.reported_spend, 2)
        if ads.reported_spend
        else 0.0
    )
    roas_overstatement_pct = (
        _round((reported_roas - real_roas) / reported_roas * 100.0)
        if reported_roas
        else 0.0
    )

    return {
        "currency": "INR",
        "money_in": {
            "total_orders": orders.total_orders,
            "gross_sales": gross,
            "breakdown": [
                {
                    "category": "Total Orders (placed)",
                    "orders": orders.total_orders,
                    "amount": gross,
                    "pct_of_gross": 100.0,
                },
                {
                    "category": "Successfully Fulfilled",
                    "orders": orders.fulfilled_orders,
                    "amount": orders.fulfilled_amount,
                    "pct_of_gross": _pct(orders.fulfilled_amount, gross),
                },
                {
                    "category": "Partial / Pending",
                    "orders": orders.partial_orders,
                    "amount": orders.partial_amount,
                    "pct_of_gross": _pct(orders.partial_amount, gross),
                },
                {
                    "category": "Cancelled",
                    "orders": orders.cancelled_orders,
                    "amount": orders.cancelled_amount,
                    "pct_of_gross": _pct(orders.cancelled_amount, gross),
                },
                {
                    "category": "Returns & Reversals",
                    "orders": None,
                    "amount": orders.returns_amount,
                    "pct_of_gross": _pct(orders.returns_amount, gross),
                },
                {
                    "category": "Discounts Given",
                    "orders": None,
                    "amount": orders.discounts_amount,
                    "pct_of_gross": _pct(orders.discounts_amount, gross),
                },
            ],
            "net_sales": net_sales,
            "net_sales_pct_of_gross": _pct(net_sales, gross),
        },
        "money_out": {
            "reported_ad_spend": _round(ads.reported_spend),
            "gst_rate": gst_rate,
            "real_ad_cost": real_ad_cost,
            "by_platform": {k: _round(v) for k, v in ads.by_platform.items()},
        },
        "efficiency": {
            "reported_roas": reported_roas,
            "real_roas": real_roas,
            "roas_overstatement_pct": roas_overstatement_pct,
            "net_profit_after_ads": _round(net_sales - real_ad_cost),
        },
    }
