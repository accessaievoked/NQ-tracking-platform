"""Unit tests for the payment-state Money Flow compute + Shopify normalize."""
from __future__ import annotations

from app.compute.money_flow import AdSpend, aggregate_orders, compute_money_flow
from app.connectors.shopify import ShopifyConnector


def _orders():
    return [
        {"total_price": 10000, "total_discounts": 0, "total_refunded": 0,
         "is_cancelled": False, "financial_status": "paid", "fulfillment": "fulfilled"},
        {"total_price": 5000, "total_discounts": 0, "total_refunded": 0,
         "is_cancelled": False, "financial_status": "pending", "fulfillment": "partial"},
        {"total_price": 3000, "total_discounts": 0, "total_refunded": 500,
         "is_cancelled": False, "financial_status": "partially_refunded", "fulfillment": "fulfilled"},
        {"total_price": 2000, "total_discounts": 0, "total_refunded": 0,
         "is_cancelled": True, "financial_status": "voided", "fulfillment": "unfulfilled"},
    ]


def test_aggregate_partitions_by_payment_state():
    agg = aggregate_orders(_orders())
    assert agg.total_orders == 4
    assert agg.gross_sales == 20000
    assert (agg.collected_orders, agg.collected_amount) == (2, 13000)
    assert (agg.pending_orders, agg.pending_amount) == (1, 5000)
    assert (agg.cancelled_orders, agg.cancelled_amount) == (1, 2000)
    assert agg.returns_amount == 500
    # partition sums to gross (never > 100%)
    assert agg.collected_amount + agg.pending_amount + agg.cancelled_amount == agg.gross_sales


def test_net_sales_is_collected_minus_returns():
    agg = aggregate_orders(_orders())
    ads = AdSpend(reported_spend=5000, reported_revenue=20000, connected=True)
    m = compute_money_flow(agg, ads, gst_rate=0.18)

    assert m["money_in"]["net_sales"] == 12500        # 13000 collected - 500 returns
    assert m["money_in"]["net_sales_pct_of_gross"] == 62.5
    assert m["money_out"]["ad_spend_connected"] is True
    assert m["money_out"]["real_ad_cost"] == 5900.0
    assert m["efficiency"]["real_roas"] == 2.12         # 12500 / 5900
    assert m["efficiency"]["reported_roas"] == 4.0
    assert m["efficiency"]["roas_overstatement_pct"] == 47.0
    assert m["efficiency"]["net_profit_after_ads"] == 6600.0


def test_roas_withheld_when_ad_spend_not_connected():
    agg = aggregate_orders(_orders())
    m = compute_money_flow(agg, AdSpend(connected=False))
    assert m["efficiency"]["ad_spend_connected"] is False
    assert m["efficiency"]["real_roas"] is None
    assert m["efficiency"]["reported_roas"] is None
    assert m["money_out"]["real_ad_cost"] is None
    # net sales still computed from orders
    assert m["money_in"]["net_sales"] == 12500


def test_shopify_sample_normalize_and_aggregate():
    conn = ShopifyConnector()  # no creds -> sample
    norm = conn.normalize(conn.fetch(None, None))
    assert len(norm) == 6
    assert norm[0]["financial_status"] == "paid"
    assert [o for o in norm if o["is_cancelled"]]  # order 5 cancelled

    agg = aggregate_orders(norm)
    assert agg.collected_orders == 3   # paid + partially_refunded
    assert agg.pending_orders == 2     # pending
    assert agg.cancelled_orders == 1   # voided/cancelled
    assert agg.returns_amount == 500.0


def test_shopify_live_refunds_shape():
    conn = ShopifyConnector()
    payload = {
        "orders": [
            {"id": 99, "total_price": "5000.00", "total_discounts": "0",
             "cancelled_at": None, "financial_status": "paid", "fulfillment_status": "fulfilled",
             "refunds": [{"transactions": [{"amount": "1200.00"}, {"amount": "300.00"}]}]},
        ]
    }
    norm = conn.normalize(payload)
    assert norm[0]["total_refunded"] == 1500.0
