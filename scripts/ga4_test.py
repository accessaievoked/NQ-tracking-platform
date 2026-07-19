"""Standalone GA4 test (run locally; needs internet).

Usage:
    python -m scripts.ga4_test <property_id> <access_token> [days]

Pulls period totals from the GA4 Analytics Data API and prints them.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone

from app.connectors.ga4 import GA4Connector


def main() -> None:
    if len(sys.argv) < 3:
        print("Usage: python -m scripts.ga4_test <property_id> <access_token> [days]")
        raise SystemExit(1)
    prop, token = sys.argv[1], sys.argv[2]
    days = int(sys.argv[3]) if len(sys.argv) > 3 else 30

    conn = GA4Connector(credentials={"access_token": token}, config={"property_id": prop})
    print("Verifying GA4 access ...")
    info = conn.verify_connection()
    print(f"  OK: property {info['property_id']}")

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    summary = conn.summarize(conn.fetch(start, end))
    print(f"\n=== GA4 totals ({start.date()} -> {end.date()}) ===")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
