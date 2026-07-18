"""Unit tests for the deterministic Money Flow compute + Shopify normalize.

These pin the exact numbers, which is the whole point: the figures must be
reproducible and independent of any LLM or external API.
"""
from __future__ import annotations

from app.compute.money_flow import AdSpend, aggregate_orders, compute_money_flow
from app.connectors.shopify import ShopifyConnector


def _orders():
    return [
        {"total_price": 10000, "total_discounts": 0, "total_refunded": 0,
         "is_cancelled": False, "fulfillment": "fulfilled"},
        {"total_price": 5000, "total_discounts": 0, "total_refunded": 0,
         "is_cancelled": False, "fulfillment": "partial"},
        {"total_price": 3000, "total_discounts": 0, "total_refunded": 3000,
         "is_cancelled": False, "fulfillment": "fulfilled"},
        {"total_price": 2000, "total_discounts": 0, "total_refunded": 0,
         "is_cancelled": True, "fulfillment": "unfulfilled"},
    ]


def test_aggregate_orders():
    agg = aggregate_orders(_orders())
    assert agg.total_orders == 4
    assert agg.gross_sales == 20000
    assert (agg.fulfilled_orders, agg.fulfilled_amount) == (2, 13000)
    assert (agg.partial_orders, agg.partial_amount) == (1, 5000)
    assert (agg.cancelled_orders, agg.cancelled_amount) == (1, 2000)
    assert agg.returns_amount == 3000


def test_compute_money_flow_numbers():
    agg = aggregate_orders(_orders())
    ads = AdSpend(reported_spend=5000, reported_revenue=20000,
                  by_platform={"meta_ads": 5000})
    m = compute_money_flow(agg, ads, gst_rate=0.18)

    assert m["money_in"]["net_sales"] == 15000
    assert m["money_in"]["net_sales_pct_of_gross"] == 75.0
    assert m["money_out"]["real_ad_cost"] == 5900.0
    assert m["efficiency"]["real_roas"] == 2.54
    assert m["efficiency"]["reported_roas"] == 4.0
    assert m["efficiency"]["roas_overstatement_pct"] == 36.5
    assert m["efficiency"]["net_profit_after_ads"] == 9100.0


def test_roas_overstatement_is_positive_when_platform_overclaims():
    agg = aggregate_orders(_orders())
    ads = AdSpend(reported_spend=5000, reported_revenue=30000)
    m = compute_money_flow(agg, ads)
    assert m["efficiency"]["reported_roas"] > m["efficiency"]["real_roas"]
    assert m["efficiency"]["roas_overstatement_pct"] > 0


def test_shopify_sample_normalize():
    conn = ShopifyConnector()  # no creds -> sample data
    payload = conn.fetch(None, None)
    norm = conn.normalize(payload)
    assert len(norm) == 6
    cancelled = [o for o in norm if o["is_cancelled"]]
    assert len(cancelled) == 1
    refunded = [o for o in norm if o["total_refunded"] > 0]
    assert refunded and refunded[0]["total_refunded"] == 1799.0


def test_shopify_live_refunds_shape():
    """Live Shopify orders express refunds as nested transactions; the
    normalizer must sum them (not the sample's flat total_refunded)."""
    conn = ShopifyConnector()
    payload = {
        "orders": [
            {
                "id": 99,
                "total_price": "5000.00",
                "total_discounts": "0",
                "cancelled_at": None,
                "fulfillment_status": "fulfilled",
                "refunds": [
                    {"transactions": [{"amount": "1200.00"}, {"amount": "300.00"}]}
                ],
            }
        ]
    }
    norm = conn.normalize(payload)
    assert norm[0]["total_refunded"] == 1500.0
