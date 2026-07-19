"""Tests for the GA4-vs-Shopify tracking-reality compute."""
from __future__ import annotations

from app.compute.money_flow import aggregate_orders
from app.compute.tracking import compute_tracking_reality


def _orders(n_paid: int):
    return [
        {"total_price": 1000, "total_discounts": 0, "total_refunded": 0,
         "is_cancelled": False, "financial_status": "paid", "fulfillment": "fulfilled"}
        for _ in range(n_paid)
    ]


def test_under_tracking_gap():
    orders = aggregate_orders(_orders(100))  # 100 real orders, gross 100000
    ga4 = {"sessions": 5000, "ecommercePurchases": 80, "purchaseRevenue": 78000}
    m = compute_tracking_reality(orders, ga4)

    assert m["shopify"]["orders"] == 100
    assert m["ga4"]["purchases"] == 80
    assert m["gap"]["order_capture_rate_pct"] == 80.0
    assert m["gap"]["untracked_orders"] == 20
    assert m["gap"]["verdict"] == "under-tracking"
    assert m["gap"]["revenue_capture_rate_pct"] == 78.0
    assert m["conversion"]["ga4_reported_cvr_pct"] == 1.6   # 80/5000
    assert m["conversion"]["true_cvr_pct"] == 2.0           # 100/5000


def test_aligned_verdict():
    orders = aggregate_orders(_orders(100))
    ga4 = {"sessions": 5000, "ecommercePurchases": 98, "purchaseRevenue": 100000}
    m = compute_tracking_reality(orders, ga4)
    assert m["gap"]["verdict"] == "aligned"


def test_handles_zero_sessions():
    orders = aggregate_orders(_orders(10))
    m = compute_tracking_reality(orders, {"sessions": 0, "ecommercePurchases": 0, "purchaseRevenue": 0})
    assert m["conversion"]["ga4_reported_cvr_pct"] == 0.0
