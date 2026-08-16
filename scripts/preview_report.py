"""Preview a generated report as an HTML page in your browser.

This is a developer preview tool, not a product frontend: it renders a report's
Markdown narrative into a styled, self-contained HTML file and opens it so you
can eyeball what a report looks like while testing.

Usage:
    python -m scripts.preview_report <report_type> <facts.json> [--brand NAME] [--no-open]
    python -m scripts.preview_report --list

Examples:
    python -m scripts.preview_report true_roas_money_flow scripts/sample_facts/true_roas_money_flow.json
    python -m scripts.preview_report cpa_spike_alert scripts/sample_facts/cpa_spike_alert.json --brand Covera

With ANTHROPIC_API_KEY set the prose is Claude-written; otherwise the offline
template is rendered. Either way the numbers come only from the facts JSON.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
import webbrowser
from pathlib import Path

from app.models import ReportType
from app.reports.generator import generate_report_narrative
from app.reports.specs import SPECS, get_spec

PREVIEW_DIR = Path("previews")


# --------------------------------------------------------------------------
# Minimal, dependency-free Markdown -> HTML (covers what the templates emit:
# headings, italic sub-title, blockquote, tables, bullet lists, bold/italic).
# --------------------------------------------------------------------------

def _inline(text: str) -> str:
    text = html.escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\w)_(.+?)_(?!\w)", r"<em>\1</em>", text)
    return text


def markdown_to_html(md: str) -> str:
    lines = md.split("\n")
    out: list[str] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        # Table: a header row followed by a |---| separator row.
        if stripped.startswith("|") and i + 1 < n and re.match(r"^\|[\s:|-]+\|$", lines[i + 1].strip()):
            header = [c.strip() for c in stripped.strip("|").split("|")]
            rows = []
            i += 2
            while i < n and lines[i].strip().startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            thead = "".join(f"<th>{_inline(c)}</th>" for c in header)
            tbody = "".join(
                "<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in r) + "</tr>" for r in rows
            )
            out.append(f"<table><thead><tr>{thead}</tr></thead><tbody>{tbody}</tbody></table>")
            continue

        if stripped.startswith("### "):
            out.append(f"<h3>{_inline(stripped[4:])}</h3>"); i += 1; continue
        if stripped.startswith("## "):
            out.append(f"<h2>{_inline(stripped[3:])}</h2>"); i += 1; continue
        if stripped.startswith("# "):
            out.append(f"<h1>{_inline(stripped[2:])}</h1>"); i += 1; continue

        if stripped.startswith("> "):
            quote = []
            while i < n and lines[i].strip().startswith(">"):
                quote.append(lines[i].strip().lstrip(">").strip()); i += 1
            out.append(f"<blockquote>{_inline(' '.join(quote))}</blockquote>")
            continue

        if stripped.startswith("- "):
            items = []
            while i < n and lines[i].strip().startswith("- "):
                items.append(f"<li>{_inline(lines[i].strip()[2:])}</li>"); i += 1
            out.append("<ul>" + "".join(items) + "</ul>")
            continue

        # Plain paragraph (may span consecutive non-empty, non-special lines).
        para = []
        while i < n and lines[i].strip() and not re.match(r"^(#|>|\||- )", lines[i].strip()):
            para.append(lines[i].strip()); i += 1
        out.append(f"<p>{_inline(' '.join(para))}</p>")
    return "\n".join(out)


_CSS = """
:root { color-scheme: dark; }
* { box-sizing: border-box; }
body { margin: 0; background: #0a0a0f; color: #e6e6ef;
       font: 15px/1.6 -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif; }
.wrap { max-width: 860px; margin: 0 auto; padding: 40px 24px 80px; }
.badge { display: inline-block; font-size: 11px; letter-spacing: .08em; text-transform: uppercase;
         color: #c4b5fd; background: rgba(124,58,237,.15); border: 1px solid rgba(124,58,237,.4);
         padding: 4px 10px; border-radius: 999px; margin-bottom: 18px; }
h1 { font-size: 26px; margin: 6px 0 2px; line-height: 1.25; }
h2 { font-size: 13px; letter-spacing: .06em; text-transform: uppercase; color: #8b8b9e;
     margin: 30px 0 10px; padding-top: 18px; border-top: 1px solid #1e1e2a; }
h3 { font-size: 15px; margin: 18px 0 8px; }
p { margin: 8px 0; }
strong { color: #fff; }
em { color: #a0a0b4; font-style: normal; }
blockquote { margin: 14px 0; padding: 12px 16px; background: rgba(245,166,35,.08);
             border-left: 3px solid #f5a623; border-radius: 8px; color: #d8c9a8; font-size: 13.5px; }
ul { margin: 8px 0; padding-left: 0; list-style: none; }
li { padding: 6px 0; border-bottom: 1px solid #16161f; }
table { width: 100%; border-collapse: collapse; margin: 12px 0; font-size: 14px;
        background: #12121a; border: 1px solid #1e1e2a; border-radius: 10px; overflow: hidden; }
th { text-align: left; font-size: 11px; letter-spacing: .05em; text-transform: uppercase;
     color: #8b8b9e; background: #16161f; padding: 10px 12px; }
td { padding: 10px 12px; border-top: 1px solid #1e1e2a; }
tr td:not(:first-child), tr th:not(:first-child) { text-align: right; }
.meta { color: #6b6b80; font-size: 12px; margin-top: 40px; }
"""


def build_html(spec_title: str, brand: str, narrative_md: str) -> str:
    body = markdown_to_html(narrative_md)
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>{html.escape(brand)} — {html.escape(spec_title)}</title>"
        f"<style>{_CSS}</style></head><body><div class='wrap'>"
        f"<span class='badge'>{html.escape(brand)}</span>"
        f"{body}"
        "<div class='meta'>NQ Tracking Platform — report preview. "
        "Figures come only from the computed facts bundle.</div>"
        "</div></body></html>"
    )


def _list() -> None:
    print("Available report types:\n")
    for key, spec in sorted(SPECS.items(), key=lambda kv: (kv[1].cadence, kv[1].title)):
        print(f"  {key.value:<26} [{spec.cadence:<9}] {spec.title}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Preview a report as HTML in the browser.")
    parser.add_argument("report_type", nargs="?", help="e.g. true_roas_money_flow")
    parser.add_argument("facts", nargs="?", help="path to a facts JSON file")
    parser.add_argument("--brand", default="Demo Brand")
    parser.add_argument("--period", default="Preview period")
    parser.add_argument("--no-open", action="store_true", help="write the file but don't open a browser")
    parser.add_argument("--list", action="store_true", help="list report types and exit")
    args = parser.parse_args(argv)

    if args.list or not args.report_type:
        _list()
        return
    if not args.facts:
        parser.error("a facts JSON path is required (or use --list)")

    try:
        report_type = ReportType(args.report_type)
        spec = get_spec(report_type)
    except (ValueError, KeyError):
        print(f"Unknown report type: {args.report_type!r}. Use --list to see options.")
        raise SystemExit(1)

    facts = json.loads(Path(args.facts).read_text(encoding="utf-8"))

    # Rich, card-based layout when the report has a styled composer AND the facts
    # bundle is rich (contains a 'hero'); otherwise the plain Markdown preview.
    from scripts.styled_preview import render_styled
    page = render_styled(report_type.value, facts)
    if page is None:
        narrative = generate_report_narrative(report_type, args.brand, args.period, facts)
        page = build_html(spec.title, args.brand, narrative)

    PREVIEW_DIR.mkdir(exist_ok=True)
    out = PREVIEW_DIR / f"{report_type.value}.html"
    out.write_text(page, encoding="utf-8")
    resolved = out.resolve()
    print(f"Wrote {resolved}")
    if not args.no_open:
        webbrowser.open(resolved.as_uri())
        print("Opened in your browser.")


if __name__ == "__main__":
    main(sys.argv[1:])
