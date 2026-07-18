"""Standalone live-Shopify test (run locally; needs internet).

Usage:
    python -m scripts.test_shopify <shop_domain> <client_id> <client_secret> [days]

Exchanges Dev Dashboard credentials for a token, verifies the shop, pulls recent
orders, and prints the computed Money Flow metrics + narrative. Ad spend is still
the placeholder until the Meta connector is built.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone

from app.compute.money_flow import aggregate_orders, compute_money_flow
from app.connectors.shopify import ShopifyConnector, exchange_client_credentials
from app.reports.generator import generate_narrative
from app.services import _sample_ad_spend


def main() -> None:
    if len(sys.argv) < 4:
        print("Usage: python -m scripts.test_shopify <shop_domain> <client_id> <client_secret> [days]")
        raise SystemExit(1)

    shop, client_id, client_secret = sys.argv[1], sys.argv[2], sys.argv[3]
    days = int(sys.argv[4]) if len(sys.argv) > 4 else 30

    print(f"Exchanging client credentials for {shop} ...")
    bundle = exchange_client_credentials(shop, client_id, client_secret)
    print(f"  token acquired | scope='{bundle.scope}' | expires_in={bundle.expires_in}s")

    conn = ShopifyConnector(
        credentials={"access_token": bundle.access_token},
        config={"shop_domain": shop},
    )
    shop_info = conn.verify_connection()
    print(f"  shop: {shop_info.get('name')} ({shop_info.get('currency')})")

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    print(f"Fetching orders {start.date()} -> {end.date()} ...")
    payload = conn.fetch(start, end)
    orders = conn.normalize(payload)
    print(f"  {len(orders)} orders pulled")

    metrics = compute_money_flow(aggregate_orders(orders), _sample_ad_spend())
    print("\n=== COMPUTED METRICS (ad spend = placeholder) ===")
    print(json.dumps(metrics, indent=2))
    print("\n=== NARRATIVE ===")
    print(generate_narrative(shop_info.get("name", "Store"), f"last {days} days", metrics))


if __name__ == "__main__":
    main()
