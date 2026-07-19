"""Print the GA4-vs-Shopify tracking-reality report for a brand.

Usage:
    python -m scripts.tracking_report <brand_id> [days]
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone

from app.db import SessionLocal
from app.models import Brand
from app.services import compute_tracking


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m scripts.tracking_report <brand_id> [days]")
        raise SystemExit(1)
    brand_id = sys.argv[1]
    days = int(sys.argv[2]) if len(sys.argv) > 2 else 30

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    with SessionLocal() as db:
        brand = db.get(Brand, brand_id)
        if not brand:
            print("Brand not found:", brand_id)
            raise SystemExit(1)
        metrics, narrative = compute_tracking(db, brand, start, end)
        print("=== METRICS ===")
        print(json.dumps(metrics, indent=2, default=str))
        print("\n=== NARRATIVE ===")
        print(narrative)


if __name__ == "__main__":
    main()
