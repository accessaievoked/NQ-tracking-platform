"""Generate any spec-backed AI report for a brand from a facts JSON file.

The facts file is a PRE-COMPUTED bundle (the deterministic numbers). Keys are
matched to the report's sections by slugified section name, e.g. a
"METRICS BLOCK" section reads facts["metrics_block"]. See
scripts/sample_facts/ for examples, and app/reports/specs.py for section names.

Usage:
    python -m scripts.ai_report <brand_id> <report_type> <facts.json> [days]
    python -m scripts.ai_report --list        # list available report types

With ANTHROPIC_API_KEY set, Claude writes the prose; otherwise a deterministic
template renders the facts under each section.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone

from app.db import SessionLocal
from app.models import Brand, ReportType
from app.reports.specs import SPECS, get_spec
from app.services import generate_ai_report


def _list() -> None:
    print("Available report types:\n")
    for key, spec in sorted(SPECS.items(), key=lambda kv: (kv[1].cadence, kv[1].title)):
        print(f"  {key.value:<26} [{spec.cadence:<7}] {spec.title}")
        print(f"  {'':<26} sections: {', '.join(spec.section_names)}")


def main() -> None:
    if len(sys.argv) >= 2 and sys.argv[1] in ("--list", "-l"):
        _list()
        return
    if len(sys.argv) < 4:
        print("Usage: python -m scripts.ai_report <brand_id> <report_type> <facts.json> [days]")
        print("       python -m scripts.ai_report --list")
        raise SystemExit(1)

    brand_id, type_str, facts_path = sys.argv[1], sys.argv[2], sys.argv[3]
    days = int(sys.argv[4]) if len(sys.argv) > 4 else 30

    try:
        report_type = ReportType(type_str)
        get_spec(report_type)
    except (ValueError, KeyError):
        print(f"Unknown report type: {type_str!r}. Run with --list to see options.")
        raise SystemExit(1)

    with open(facts_path, encoding="utf-8") as fh:
        facts = json.load(fh)

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)

    with SessionLocal() as db:
        brand = db.get(Brand, brand_id)
        if not brand:
            print("Brand not found:", brand_id)
            raise SystemExit(1)
        report = generate_ai_report(db, brand, report_type, start, end, facts)
        status = report.status.value if hasattr(report.status, "value") else report.status
        print("Status:", status)
        if report.error:
            print("Error:", report.error)
        print("\n=== NARRATIVE ===")
        print(report.narrative_md or "(none)")


if __name__ == "__main__":
    main()
