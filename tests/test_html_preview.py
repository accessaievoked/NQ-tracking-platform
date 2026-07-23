"""Tests for the HTML report preview builder (scripts/preview_report.py).

These validate the Markdown->HTML conversion and the full page build offline;
no browser is opened.
"""
from __future__ import annotations

from app.models import ReportType
from app.reports.generator import generate_report_narrative
from scripts.preview_report import build_html, markdown_to_html


def test_markdown_headings_and_bold():
    html = markdown_to_html("# Title\n\n## Section\n\nSome **bold** text.")
    assert "<h1>Title</h1>" in html
    assert "<h2>Section</h2>" in html
    assert "<strong>bold</strong>" in html


def test_markdown_table():
    md = "| A | B |\n| --- | --- |\n| 1 | 2 |"
    html = markdown_to_html(md)
    assert "<table>" in html
    assert "<th>A</th>" in html
    assert "<td>1</td>" in html and "<td>2</td>" in html


def test_markdown_blockquote_and_list():
    html = markdown_to_html("> note here\n\n- one\n- two")
    assert "<blockquote>note here</blockquote>" in html
    assert "<ul><li>one</li><li>two</li></ul>" in html


def test_markdown_escapes_html():
    # Raw HTML in the source must be escaped, not passed through.
    html = markdown_to_html("a <script>alert(1)</script> b")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_build_html_wraps_a_real_report():
    facts = {
        "bottom_line": "You spent Rs.4,43,544 on ads. Rs.9,62,679 reached your store.",
        "gst_correction": [
            {"metric": "ROAS", "platform": "3.03x", "shopify_verified": "1.84x"},
        ],
    }
    md = generate_report_narrative(ReportType.money_flow_report, "Covera", "Jul 2026", facts)
    page = build_html("Money Flow Report", "Covera", md)
    assert page.startswith("<!doctype html>")
    assert "<title>Covera — Money Flow Report</title>" in page
    assert "You spent Rs.4,43,544" in page
    # Section headings from the spec are rendered as <h2>.
    assert "<h2>BOTTOM LINE</h2>" in page
    assert "<table>" in page  # the gst_correction list-of-dicts becomes a table
