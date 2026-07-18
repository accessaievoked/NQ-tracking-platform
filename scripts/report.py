"""Generate and print a Money Flow report for a brand (uses its stored token).

Usage:
    python -m scripts.report <brand_id> [days]
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone

from app.db import SessionLocal
from app.models import Brand
from app.services import generate_money_flow_report


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m scripts.report <brand_id> [days]")
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
        report = generate_money_flow_report(db, brand, start, end)
        print("Status:", report.status.value if hasattr(report.status, "value") else report.status)
        if report.error:
            print("Error:", report.error)
        print("\n=== COMPUTED METRICS (ad spend = placeholder) ===")
        print(json.dumps(report.computed_metrics, indent=2, default=str) if report.computed_metrics else "(none)")
        print("\n=== NARRATIVE ===")
        print(report.narrative_md or "(none)")


if __name__ == "__main__":
    main()
