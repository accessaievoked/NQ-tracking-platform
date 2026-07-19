"""Tracking Reality: reconcile GA4-reported ecommerce vs real Shopify orders.

GA4 tracks purchases client-side (JS/pixel), so ad blockers, consent, and cookie
loss make it systematically under-count real sales. This compares GA4's tracked
purchases + revenue against Shopify's actual orders + collected cash, and
quantifies the gap. Deterministic: the LLM only narrates.
"""
from __future__ import annotations

from typing import Any

from app.compute.money_flow import OrderAggregate


def _round(x: float, n: int = 2) -> float:
    return round(float(x), n)


def _pct(part: float, whole: float) -> float:
    return _round((part / whole * 100.0) if whole else 0.0)


def compute_tracking_reality(orders: OrderAggregate, ga4: dict[str, float]) -> dict[str, Any]:
    shopify_orders = orders.total_orders
    shopify_gross = orders.gross_sales
    shopify_collected = orders.collected_amount

    ga4_purchases = int(ga4.get("ecommercePurchases", 0) or 0)
    ga4_revenue = _round(ga4.get("purchaseRevenue", 0) or 0)
    sessions = int(ga4.get("sessions", 0) or 0)

    order_capture = _pct(ga4_purchases, shopify_orders)
    untracked_orders = shopify_orders - ga4_purchases

    if order_capture < 95:
        verdict = "under-tracking"
    elif order_capture > 105:
        verdict = "over-tracking"
    else:
        verdict = "aligned"

    return {
        "currency": "INR",
        "sessions": sessions,
        "shopify": {
            "orders": shopify_orders,
            "gross_sales": shopify_gross,
            "collected": shopify_collected,
        },
        "ga4": {
            "purchases": ga4_purchases,
            "purchase_revenue": ga4_revenue,
        },
        "gap": {
            "order_capture_rate_pct": order_capture,
            "revenue_capture_rate_pct": _pct(ga4_revenue, shopify_gross),
            "untracked_orders": untracked_orders,
            "untracked_orders_pct": _pct(untracked_orders, shopify_orders),
            "verdict": verdict,
        },
        "conversion": {
            "ga4_reported_cvr_pct": _pct(ga4_purchases, sessions),
            "true_cvr_pct": _pct(shopify_orders, sessions),
        },
    }
