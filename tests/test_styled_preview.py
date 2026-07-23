"""Tests for the styled (adverti-look) preview renderer."""
from __future__ import annotations

from scripts.styled_preview import inline, render_styled, render_true_roas

_MIN_FACTS = {
    "brand": "Covera",
    "hero": {"spent": "Rs.4,43,544", "net_revenue": "Rs.9,62,679",
             "dashboard_roas": "3.03x", "true_roas": "1.84x", "note": "n"},
    "roas_cards": [
        {"label": "Dashboard Claims", "value": "3.03x", "caption": "c", "color": "red"},
        {"label": "True Store ROAS", "value": "1.84x", "caption": "c", "color": "purple"},
    ],
    "campaign_table": {
        "cols": ["Campaign", "Platform", "Spend", "GST-Adj Spend", "Reported Rev", "GST-Corr ROAS", "Status"],
        "rows": [{"campaign": "Brand Search", "platform": "Google", "spend": "Rs.5,450",
                  "gst_adj_spend": "Rs.6,431", "reported_rev": "Rs.79,224",
                  "gst_roas": "12.32x", "status": "Scale"}],
        "total": {"campaign": "TOTAL", "spend": "Rs.4,43,544", "status": "True: 1.84x"},
    },
}


def test_render_true_roas_has_core_blocks():
    html = render_true_roas(_MIN_FACTS)
    assert html.startswith("<!doctype html>")
    assert "class='hero'" in html
    assert "Rs.4,43,544" in html
    assert "class='rcard'" in html          # ROAS tiles
    assert "class='ctable'" in html          # campaign table
    assert "Brand Search" in html


def test_render_styled_needs_hero():
    # Non-rich facts (no 'hero') -> None so caller falls back to Markdown.
    assert render_styled("true_roas_money_flow", {"headline": "x"}) is None
    # Unknown report type -> None.
    assert render_styled("cpa_spike_alert", _MIN_FACTS) is None
    # Rich facts + supported type -> HTML.
    assert render_styled("true_roas_money_flow", _MIN_FACTS) is not None


def test_inline_bold_and_escape():
    out = inline("a **bold** <x>")
    assert "<strong>bold</strong>" in out
    assert "&lt;x&gt;" in out
