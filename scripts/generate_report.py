"""Generate an AI-written report from COMPUTED data, and render it to HTML.

Unlike scripts/ai_report.py (which narrates a facts JSON you supply), this
computes the facts bundle live from Shopify orders + Meta ad spend, then hands
it to the AI narrator. With ANTHROPIC_API_KEY set the report is Claude-written;
otherwise the deterministic template is used. Either way the numbers come only
from the computed facts. The report is also written to previews/<type>.html and
opened in the browser.

Usage:
    python -m scripts.generate_report <brand_id|demo> [report_type] [days] [--no-ai] [--no-open]

Examples:
    python -m scripts.generate_report demo true_roas_money_flow
    python -m scripts.generate_report demo true_roas_money_flow --no-ai
    python -m scripts.generate_report 9dad3cd1-... true_roas_money_flow 30
"""
from __future__ import annotations

import json
import sys
import webbrowser
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.compute.money_flow import AdSpend, aggregate_orders, compute_money_flow
from app.config import settings
from app.connectors.shopify import ShopifyConnector
from app.models import ReportType
from app.reports.compose import compose_facts
from app.reports.generator import generate_report_narrative
from app.reports.specs import get_spec


# Report types that render in the styled adverti-style card layout.
_STYLED_MONEY_FLOW = {
    ReportType.money_flow_report,
}


def _build_facts(report_type, brand_name, label, money):
    composed = compose_facts(report_type, money)
    if composed is not None:
        composed.update({"brand": brand_name, "period": label})
        return composed
    return {"currency": "INR", "brand": brand_name, "period": label, "money_flow": money}


def _demo_inputs():
    sc = ShopifyConnector()
    orders = aggregate_orders(sc.normalize(sc.fetch(None, None)))
    # A coherent sample ad spend so ROAS is shown (Meta not really connected).
    ads = AdSpend(reported_spend=8000, reported_revenue=32000,
                  by_platform={"meta_ads": 8000}, connected=True)
    return "Demo Brand", orders, ads


def main() -> None:
    args = list(sys.argv[1:])
    force_template = "--no-ai" in args          # deterministic template, zero network
    no_open = "--no-open" in args                # write the HTML but don't launch a browser
    args = [a for a in args if a not in ("--no-ai", "--no-open")]
    if not args:
        print("Usage: python -m scripts.generate_report <brand_id|demo> [report_type] [days] [--no-ai] [--no-open]")
        raise SystemExit(1)
    target = args[0]
    type_str = args[1] if len(args) > 1 else "money_flow_report"
    days = int(args[2]) if len(args) > 2 else 30

    try:
        report_type = ReportType(type_str)
        spec = get_spec(report_type)
    except (ValueError, KeyError):
        print(f"Unknown report type: {type_str!r}.")
        raise SystemExit(1)

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    label = f"{start:%b %d} - {end:%b %d, %Y}"

    if target == "demo":
        brand_name, orders, ads = _demo_inputs()
    else:
        from app.db import SessionLocal
        from app.models import Brand
        from app.services import get_meta_ad_spend, _shopify_connector
        with SessionLocal() as db:
            brand = db.get(Brand, target)
            if not brand:
                print("Brand not found:", target)
                raise SystemExit(1)
            brand_name = brand.name
            conn = _shopify_connector(db, brand.id)
            orders = aggregate_orders(conn.normalize(conn.fetch(start, end)))
            ads = get_meta_ad_spend(db, brand.id, start, end)

    money = compute_money_flow(orders, ads, gst_rate=settings.default_gst_rate)
    facts = _build_facts(report_type, brand_name, label, money)
    if force_template:
        from app.reports.generator import _fallback_report
        narrative = _fallback_report(spec, brand_name, label, facts)
    else:
        narrative = generate_report_narrative(report_type, brand_name, label, facts)

    engine = ("offline template (--no-ai)" if force_template
              else "Claude" if settings.anthropic_api_key
              else "offline template (set ANTHROPIC_API_KEY for AI prose)")
    print(f"# Report: {spec.title}   |   engine: {engine}\n")
    print("=== COMPUTED FACTS (all the AI receives; it may not invent or alter any number) ===")
    print(json.dumps(facts, indent=2, default=str))
    print("\n=== GENERATED REPORT (prose written by the engine from the facts above) ===")
    print(narrative)

    # Money-flow reports get the styled adverti-style card layout (data cards +
    # the AI narrative as a 'Full analysis' section). Everything else gets the
    # plain markdown HTML.
    if report_type in _STYLED_MONEY_FLOW:
        from scripts.preview_report import markdown_to_html
        from scripts.styled_preview import render_money_flow_from_compute
        page = render_money_flow_from_compute(money, brand_name, label, markdown_to_html(narrative))
    else:
        # Every other report type gets the adverti card style too: hero + one
        # styled card per section, rendered from the AI/template narrative.
        from scripts.styled_preview import render_narrative_report
        page = render_narrative_report(brand_name, spec.title, label, narrative)
    out_dir = Path("previews")
    out_dir.mkdir(exist_ok=True)
    out_path = (out_dir / f"{report_type.value}.html").resolve()
    out_path.write_text(page, encoding="utf-8")
    print(f"\nHTML report written to: {out_path}")
    if not no_open:
        webbrowser.open(out_path.as_uri())
        print("Opened in your browser.")


if __name__ == "__main__":
    main()
