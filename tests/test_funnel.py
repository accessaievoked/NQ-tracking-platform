"""Funnel compute tests — the numbers on the Data Insights page.

Nothing here touches the network: GA4 responses are canned and fed through the
same parser the connector uses.
"""
from __future__ import annotations

import pytest

from app.compute.funnel import (
    LAYOUTS,
    VIEW_ORDER,
    VIEWS,
    build_row,
    build_table,
    format_dim,
    list_views,
)
from app.connectors.ga4 import and_filters, in_list_filter, parse_rows


def _ev(dim, event, users, events):
    return {"dimensions": [dim, event], "metrics": {"totalUsers": users, "eventCount": events}}


def _total(event, users, events):
    return {"dimensions": [event], "metrics": {"totalUsers": users, "eventCount": events}}


# --- rate maths -----------------------------------------------------------

def test_rates_are_relative_to_item_views():
    row = build_row(
        "20260811",
        {"item_view": 1000, "add_to_cart": 100, "begin_checkout": 60, "purchase": 20},
        {"add_to_cart": 260, "purchase": 20},
        total_users=2000,
    )
    assert row["atc_pct"] == 10.0
    assert row["checkout_pct"] == 6.0
    assert row["purchase_pct"] == 2.0
    # "Add to baskets" is an event count, deliberately larger than ATC users.
    assert row["add_to_baskets"] == 260
    assert row["item_view_rate_pct"] == 50.0
    assert row["site_cvr_pct"] == 1.0


def test_step_chain_multiplies_out_to_purchase_pct():
    """ATC% x ATC->Checkout% x Checkout->Purchase% == Purchase%.

    This is the relationship the source Looker report shows across its two rows
    of tables; if it ever breaks, the two tables disagree with each other.
    """
    row = build_row(
        "20260811",
        {"item_view": 111889, "add_to_cart": 6859, "begin_checkout": 4428, "purchase": 1745},
        {},
    )
    chained = (row["atc_pct"] / 100) * (row["atc_to_checkout_pct"] / 100) \
        * (row["checkout_to_purchase_pct"] / 100) * 100
    assert chained == pytest.approx(row["purchase_pct"], abs=0.01)


def test_zero_denominators_render_as_none_not_zero():
    row = build_row("x", {"item_view": 0, "add_to_cart": 0}, {})
    assert row["atc_pct"] is None
    assert row["atc_to_checkout_pct"] is None
    assert row["checkout_dropout_pct"] is None


def test_checkout_dropout_is_the_share_that_did_not_advance():
    row = build_row(
        "20260811",
        {"begin_checkout": 400, "add_shipping": 300, "add_payment": 240, "purchase": 120},
        {},
    )
    assert row["shipping_dropout_pct"] == 25.0     # 400 -> 300
    assert row["payment_dropout_pct"] == 20.0      # 300 -> 240
    assert row["purchase_dropout_pct"] == 50.0     # 240 -> 120
    assert row["checkout_dropout_pct"] == 70.0     # 400 -> 120


# --- table assembly -------------------------------------------------------

SPEC = {"key": "by_date", "title": "Item View --> Purchase (By Date)", "dimension": "date",
        "layout": "basic", "sort": "dim_desc", "limit": 5000, "source": "events"}


def test_build_table_pivots_events_and_sorts_newest_first():
    events = [
        _ev("20260810", "view_item", 500, 900), _ev("20260810", "add_to_cart", 50, 120),
        _ev("20260810", "begin_checkout", 30, 40), _ev("20260810", "purchase", 10, 10),
        _ev("20260811", "view_item", 400, 700), _ev("20260811", "add_to_cart", 60, 150),
        _ev("20260811", "begin_checkout", 40, 55), _ev("20260811", "purchase", 20, 20),
    ]
    base = [
        {"dimensions": ["20260810"], "metrics": {"totalUsers": 800, "sessions": 950}},
        {"dimensions": ["20260811"], "metrics": {"totalUsers": 700, "sessions": 810}},
    ]
    totals = [_total("view_item", 800, 1600), _total("add_to_cart", 100, 270),
              _total("begin_checkout", 65, 95), _total("purchase", 28, 30)]

    table = build_table(SPEC, events, base, totals, {"totalUsers": 1300, "sessions": 1760})

    assert [r["dim"] for r in table["rows"]] == ["Aug 11, 2026", "Aug 10, 2026"]
    aug11 = table["rows"][0]
    assert aug11["item_view_users"] == 400
    assert aug11["add_to_baskets"] == 150
    assert aug11["atc_pct"] == 15.0
    assert aug11["total_users"] == 700


def test_grand_total_is_deduplicated_not_a_row_sum():
    """800 total item-view users < 500 + 400 daily — the same people came back."""
    events = [
        _ev("20260810", "view_item", 500, 900), _ev("20260811", "view_item", 400, 700),
    ]
    base = []
    totals = [_total("view_item", 800, 1600), _total("purchase", 28, 30)]
    table = build_table(SPEC, events, base, totals, {"totalUsers": 1300})

    row_sum = sum(r["item_view_users"] for r in table["rows"])
    assert row_sum == 900
    assert table["totals"]["item_view_users"] == 800
    assert table["totals"]["purchase_pct"] == 3.5


def test_item_scoped_tables_use_item_metrics():
    spec = {**SPEC, "key": "by_product", "dimension": "itemName", "layout": "items",
            "sort": "item_views_desc", "source": "items"}
    rows = [
        {"dimensions": ["QUE GEHAN"], "metrics": {
            "itemsViewed": 8685, "itemsAddedToCart": 553, "itemsCheckedOut": 340,
            "itemsPurchased": 101, "itemRevenue": 250000}},
        {"dimensions": ["QUE SURKH"], "metrics": {
            "itemsViewed": 7446, "itemsAddedToCart": 636, "itemsCheckedOut": 400,
            "itemsPurchased": 110, "itemRevenue": 270000}},
    ]
    totals = [{"dimensions": [], "metrics": {
        "itemsViewed": 111889, "itemsAddedToCart": 11982, "itemsCheckedOut": 7000,
        "itemsPurchased": 1745, "itemRevenue": 4000000}}]

    table = build_table(spec, rows, [], totals, {})

    assert table["rows"][0]["dim"] == "QUE GEHAN"
    assert table["rows"][0]["item_view_users"] == 8685
    assert table["rows"][0]["add_to_baskets"] == 553
    assert table["rows"][0]["atc_pct"] == pytest.approx(6.37, abs=0.01)
    assert table["rows"][0]["item_revenue"] == 250000
    assert table["totals"]["item_view_users"] == 111889


def test_columns_carry_heat_and_inverse_flags():
    """The dropout/failure columns flip the heat scale — high is bad there."""
    table = build_table({**SPEC, "layout": "micro"}, [], [], [], {})
    by_key = {c["key"]: c for c in table["columns"]}
    assert by_key["atc_to_caf_pct"]["heat"] is True
    assert by_key["atc_to_caf_pct"]["inverse"] is True
    assert by_key["atc_to_gci_pct"]["inverse"] is False
    assert by_key["dim"]["label"] == "Date"


# --- specs / plumbing -----------------------------------------------------

def test_every_view_is_listed_and_uses_a_real_layout():
    keys = {v["key"] for v in list_views()}
    assert keys == set(VIEW_ORDER)
    assert len(VIEW_ORDER) == 11  # the source report's 10 pages + Overview
    known = set(LAYOUTS)
    for view in VIEWS.values():
        for table in view["tables"]:
            assert table["layout"] in known
            assert table["dimensions"], "every table needs at least one dimension"
        for chart in view.get("charts", []):
            assert chart["table"] in {t["key"] for t in view["tables"]}


def test_every_layout_column_is_produced_by_build_row():
    """A layout referencing a key build_row never sets would render a blank column."""
    produced = set(build_row("x", {}, {}))
    produced |= {"dim2"}  # supplied by build_table for two-dimension tables
    for name, columns in LAYOUTS.items():
        missing = [c["key"] for c in columns if c["key"] not in produced]
        assert not missing, f"layout '{name}' references unknown columns: {missing}"


def test_format_dim_handles_ga4_compact_values():
    assert format_dim("date", "20260811") == "Aug 11, 2026"
    assert format_dim("dateHour", "2026081119") == "Aug 11, 7PM"
    # The source report writes hours as 12AM / 1AM / ... / 11PM.
    assert format_dim("hour", "00") == "12AM"
    assert format_dim("hour", "07") == "7AM"
    assert format_dim("hour", "13") == "1PM"
    assert format_dim("yearWeek", "202632") == "32"
    assert format_dim("yearMonth", "202608") == "August"
    assert format_dim("browser", "") == "(not set)"


def test_micro_funnel_rates_use_the_custom_step_mapping():
    """CAS / CAF / GCI / ASI / API columns come from CUSTOM_STEP_EVENTS."""
    row = build_row(
        "20260811",
        {"item_view": 1000, "add_to_cart": 100, "cas": 50, "caf": 6,
         "gci": 64, "asi": 48, "api": 30, "purchase": 20},
        {},
    )
    assert row["atc_to_cas_pct"] == 50.0
    assert row["atc_to_caf_pct"] == 6.0
    assert row["atc_to_gci_pct"] == 64.0
    assert row["gci_to_asi_pct"] == 75.0
    assert row["asi_to_api_pct"] == 62.5
    assert row["api_to_purchase_pct"] == pytest.approx(66.67, abs=0.01)
    assert row["pdp_to_checkout_pct"] == 6.4     # GCI users / item views


def test_website_wide_rates_are_shares_of_all_users():
    row = build_row(
        "20260811",
        {"page_view": 977, "session_start": 860, "first_visit": 576, "scroll": 138,
         "item_view": 817, "add_to_cart": 59, "purchase": 10},
        {}, total_users=1000, engagement_rate=0.8486,
    )
    assert row["page_view_rate_pct"] == 97.7
    assert row["session_start_rate_pct"] == 86.0
    assert row["first_visit_rate_pct"] == 57.6
    assert row["scroll_rate_pct"] == 13.8
    assert row["atc_rate_pct"] == 5.9
    assert row["engagement_rate_pct"] == 84.86


def test_two_dimension_table_carries_both_columns():
    spec = {"key": "cohort", "title": "t", "dimension": "pageTitle",
            "dimensions": ["pageTitle", "yearMonth"], "layout": "cohort",
            "sort": "item_views_desc", "limit": 100, "source": "events"}
    rows = [
        {"dimensions": ["QUE GLOW", "202602", "view_item"],
         "metrics": {"totalUsers": 12238.57, "eventCount": 20000}},
        {"dimensions": ["QUE GLOW", "202602", "add_to_cart"],
         "metrics": {"totalUsers": 914, "eventCount": 1200}},
        {"dimensions": ["QUE GLOW", "202602", "purchase"],
         "metrics": {"totalUsers": 240, "eventCount": 240}},
    ]
    table = build_table(spec, rows, [], [], {})
    row = table["rows"][0]
    assert row["dim"] == "QUE GLOW"
    assert row["dim2"] == "February"
    assert row["atc_to_purchase_pct"] == pytest.approx(26.26, abs=0.01)
    assert [c["label"] for c in table["columns"][:2]] == ["Page title", "Month"]


def test_parse_rows_and_filter_helpers():
    parsed = parse_rows({
        "dimensionHeaders": [{"name": "date"}, {"name": "eventName"}],
        "metricHeaders": [{"name": "totalUsers"}],
        "rows": [{"dimensionValues": [{"value": "20260811"}, {"value": "view_item"}],
                  "metricValues": [{"value": "400"}]}],
    })
    assert parsed[0]["metrics"]["totalUsers"] == 400.0
    assert parsed[0]["keys"]["eventName"] == "view_item"

    f = and_filters(in_list_filter("eventName", ["purchase"]), None)
    assert f == {"filter": {"fieldName": "eventName", "inListFilter": {"values": ["purchase"]}}}
    both = and_filters(in_list_filter("eventName", ["purchase"]), in_list_filter("pageTitle", ["a"]))
    assert len(both["andGroup"]["expressions"]) == 2
    assert and_filters(None, None) is None
