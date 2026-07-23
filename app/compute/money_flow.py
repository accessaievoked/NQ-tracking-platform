"""Deterministic Money Flow computation.

The heart of the reporting engine: *the LLM never does arithmetic*. Every figure
here is computed in code and only then handed to the narrative generator.

Methodology (documented + defensible):

  "Money that reached the store" is about **cash actually collected**, not orders
  merely placed. Orders are partitioned by payment state:

    collected (paid)   financial_status in {paid, partially_refunded}, not cancelled
    pending            not cancelled, not yet collected (COD/authorized/pending)
    cancelled/voided   cancelled, or financial_status == voided

    net_sales_reached  = collected_amount - returns_amount

  collected + pending + cancelled == gross (a clean partition), so the breakdown
  never sums past 100%. Returns and discounts are shown as *adjustments*:
    - returns reduce collected cash (subtracted in net)
    - discounts are informational only (Shopify total_price is already
      post-discount, so they are NOT subtracted again)

  real_ad_cost   = reported_spend * (1 + gst_rate)   (Indian ad platforms bill GST)
  real_roas      = net_sales_reached / real_ad_cost
  reported_roas  = platform_reported_revenue / reported_spend

  If ad spend is not connected (placeholder), ROAS is withheld rather than
  printing a meaningless number.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Shopify financial_status values that mean the money was actually captured.
_PAID_STATES = {"paid", "partially_refunded"}
_VOID_STATES = {"voided"}


def _round(x: float, ndigits: int = 2) -> float:
    return round(float(x), ndigits)


def _pct(part: float, whole: float) -> float:
    return _round((part / whole * 100.0) if whole else 0.0)


@dataclass
class OrderAggregate:
    total_orders: int = 0
    gross_sales: float = 0.0
    collected_orders: int = 0
    collected_amount: float = 0.0
    pending_orders: int = 0
    pending_amount: float = 0.0
    cancelled_orders: int = 0
    cancelled_amount: float = 0.0
    returns_amount: float = 0.0
    discounts_amount: float = 0.0
    # Secondary (shipping) view, independent of payment state.
    fulfilled_orders: int = 0
    fulfilled_amount: float = 0.0


@dataclass
class AdSpend:
    reported_spend: float = 0.0
    reported_revenue: float = 0.0  # platform-attributed revenue (for dashboard ROAS)
    by_platform: dict[str, float] = field(default_factory=dict)
    connected: bool = False  # False -> ROAS withheld


def aggregate_orders(orders: list[dict[str, Any]]) -> OrderAggregate:
    """Aggregate normalized order dicts.

    Expected fields per order:
        total_price:      float  (amount charged, post-discount)
        total_discounts:  float
        total_refunded:   float
        is_cancelled:     bool
        financial_status: str | None  (paid, pending, authorized, refunded, ...)
        fulfillment:      "fulfilled" | "partial" | "unfulfilled"
    """
    agg = OrderAggregate()
    for o in orders:
        total = float(o.get("total_price", 0) or 0)
        fin = (o.get("financial_status") or "").lower()

        agg.total_orders += 1
        agg.gross_sales += total
        agg.discounts_amount += float(o.get("total_discounts", 0) or 0)
        agg.returns_amount += float(o.get("total_refunded", 0) or 0)

        if o.get("fulfillment") == "fulfilled":
            agg.fulfilled_orders += 1
            agg.fulfilled_amount += total

        if o.get("is_cancelled") or fin in _VOID_STATES:
            agg.cancelled_orders += 1
            agg.cancelled_amount += total
        elif fin in _PAID_STATES:
            agg.collected_orders += 1
            agg.collected_amount += total
        else:  # pending / authorized / unpaid / unknown
            agg.pending_orders += 1
            agg.pending_amount += total

    for f in (
        "gross_sales", "collected_amount", "pending_amount", "cancelled_amount",
        "returns_amount", "discounts_amount", "fulfilled_amount",
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
    net_reached = _round(orders.collected_amount - orders.returns_amount)

    money_in = {
        "currency": "INR",
        "total_orders": orders.total_orders,
        "gross_sales": gross,
        "breakdown": [
            {"category": "Total Orders (placed)", "kind": "total",
             "orders": orders.total_orders, "amount": gross, "pct_of_gross": 100.0},
            {"category": "Collected (paid)", "kind": "partition",
             "orders": orders.collected_orders, "amount": orders.collected_amount,
             "pct_of_gross": _pct(orders.collected_amount, gross)},
            {"category": "Pending / not yet collected", "kind": "partition",
             "orders": orders.pending_orders, "amount": orders.pending_amount,
             "pct_of_gross": _pct(orders.pending_amount, gross)},
            {"category": "Cancelled / voided", "kind": "partition",
             "orders": orders.cancelled_orders, "amount": orders.cancelled_amount,
             "pct_of_gross": _pct(orders.cancelled_amount, gross)},
            {"category": "Returns & refunds", "kind": "adjustment",
             "orders": None, "amount": orders.returns_amount,
             "pct_of_gross": _pct(orders.returns_amount, gross)},
            {"category": "Discounts (informational)", "kind": "informational",
             "orders": None, "amount": orders.discounts_amount,
             "pct_of_gross": _pct(orders.discounts_amount, gross)},
        ],
        "net_sales": net_reached,
        "net_sales_pct_of_gross": _pct(net_reached, gross),
        "fulfilled_amount": orders.fulfilled_amount,
    }

    money_out = {
        "ad_spend_connected": ads.connected,
        "reported_ad_spend": _round(ads.reported_spend) if ads.connected else None,
        "gst_rate": gst_rate,
        "real_ad_cost": _round(ads.reported_spend * (1 + gst_rate)) if ads.connected else None,
        "by_platform": {k: _round(v) for k, v in ads.by_platform.items()} if ads.connected else {},
    }

    if ads.connected and ads.reported_spend > 0:
        real_ad_cost = _round(ads.reported_spend * (1 + gst_rate))
        real_roas = _round(net_reached / real_ad_cost, 2)
        reported_roas = _round(ads.reported_revenue / ads.reported_spend, 2)
        overstatement = (
            _round((reported_roas - real_roas) / reported_roas * 100.0)
            if reported_roas else 0.0
        )
        efficiency = {
            "ad_spend_connected": True,
            "reported_roas": reported_roas,
            "real_roas": real_roas,
            "roas_overstatement_pct": overstatement,
            "net_profit_after_ads": _round(net_reached - real_ad_cost),
        }
    else:
        efficiency = {
            "ad_spend_connected": False,
            "note": "Ad spend not connected — ROAS unavailable until Meta/Google is linked.",
            "reported_roas": None,
            "real_roas": None,
            "roas_overstatement_pct": None,
            "net_profit_after_ads": None,
        }

    return {"currency": "INR", "money_in": money_in, "money_out": money_out,
            "efficiency": efficiency}


def compute_order_health(agg: OrderAggregate) -> dict[str, Any]:
    """Order-health tiles: fulfilment, returns, AOV. UTM coverage needs a UTM
    matcher (not connected yet), so it's withheld."""
    total = agg.total_orders
    fulfilled = agg.fulfilled_orders
    unfulfilled = total - fulfilled
    return {
        "fulfilled_pct": _pct(fulfilled, total),
        "fulfilled_orders": fulfilled,
        "unfulfilled_pct": _pct(unfulfilled, total),
        "unfulfilled_orders": unfulfilled,
        "return_rate_pct": _pct(agg.returns_amount, agg.gross_sales),
        "returns_amount": agg.returns_amount,
        "aov": _round(agg.gross_sales / total) if total else 0.0,
        "total_orders": total,
        "utm_coverage_pct": None,  # withheld until UTM tracking is connected
    }


def daily_series(orders: list[dict[str, Any]], real_ad_cost: float | None = None,
                 ad_connected: bool = False) -> list[dict[str, Any]]:
    """Per-day net sales (collected cash) from normalized orders. Ad spend per
    day is estimated by spreading the period's real ad cost evenly (labelled
    'est.') when ads are connected, else withheld."""
    from collections import defaultdict
    from datetime import datetime as _dt

    by_day: dict[str, float] = defaultdict(float)
    for o in orders:
        ca = o.get("created_at")
        if not ca:
            continue
        fin = (o.get("financial_status") or "").lower()
        if o.get("is_cancelled") or fin in _VOID_STATES:
            continue
        if fin in _PAID_STATES:
            day = str(ca)[:10]
            by_day[day] += float(o.get("total_price", 0) or 0) - float(o.get("total_refunded", 0) or 0)

    days = sorted(by_day)
    if not days:
        return []
    spend = _round(real_ad_cost / len(days)) if (ad_connected and real_ad_cost) else None
    best = max(by_day.values())
    out = []
    for d in days:
        try:
            label = _dt.strptime(d, "%Y-%m-%d").strftime("%b %d")
        except ValueError:
            label = d
        out.append({"label": label, "net": _round(by_day[d]), "spend": spend, "best": by_day[d] == best})
    return out
