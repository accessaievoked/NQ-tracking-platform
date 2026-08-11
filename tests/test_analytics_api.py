"""Data Insights API: the connection guard, and a full view built from a stub GA4.

The GA4 connector is replaced with a stub that answers runReport from canned
data, so the route + service + compute wiring is exercised without the network.
"""
from __future__ import annotations

import app.services as services


class StubGA4:
    """Answers run_report() based on the dimensions asked for."""

    def __init__(self):
        self.calls = []

    def run_report(self, *, dimensions, metrics, start, end, dimension_filter=None,
                   order_bys=None, limit=100000):
        self.calls.append(tuple(dimensions))

        # item-scoped product tables
        if "itemName" in dimensions:
            return [{"dimensions": ["QUE GEHAN"], "metrics": {
                "itemsViewed": 8685, "itemsAddedToCart": 553, "itemsCheckedOut": 340,
                "itemsPurchased": 101, "itemRevenue": 250000}}]
        if not dimensions and "itemsViewed" in metrics:
            return [{"dimensions": [], "metrics": {
                "itemsViewed": 111889, "itemsAddedToCart": 11982, "itemsCheckedOut": 7000,
                "itemsPurchased": 1745, "itemRevenue": 4000000}}]
        # period totals, no breakdown
        if not dimensions:
            return [{"dimensions": [], "metrics": {"totalUsers": 119372, "sessions": 140000}}]
        # de-duplicated event totals
        if dimensions == ["eventName"]:
            return [
                {"dimensions": ["view_item"], "metrics": {"totalUsers": 111889, "eventCount": 220000}},
                {"dimensions": ["add_to_cart"], "metrics": {"totalUsers": 6859, "eventCount": 11982}},
                {"dimensions": ["begin_checkout"], "metrics": {"totalUsers": 5885, "eventCount": 7000}},
                {"dimensions": ["purchase"], "metrics": {"totalUsers": 1745, "eventCount": 1800}},
            ]
        if dimensions == ["pageTitle"]:
            return [{"dimensions": ["QUE GEHAN | MEDIUM"], "metrics": {"totalUsers": 8800}}]
        # breakdown + eventName
        if len(dimensions) == 2:
            by_page = dimensions[0] == "pageTitle"
            keys = (("QUE GEHAN | MEDIUM", "QUE SURKH | MEDIUM") if by_page
                    else ("20260810", "20260811"))
            # Page rows get different volumes so the "most viewed first" sort has
            # something to order by; the date rows stay equal.
            scales = (1.0, 0.5) if by_page else (1.0, 1.0)
            out = []
            for scale, key in zip(scales, keys):
                for event, users, count in (
                    ("view_item", 5000, 9000), ("add_to_cart", 300, 480),
                    ("begin_checkout", 250, 300), ("purchase", 70, 72),
                ):
                    out.append({"dimensions": [key, event],
                                "metrics": {"totalUsers": users * scale,
                                            "eventCount": count * scale}})
            return out
        # breakdown base row
        return [
            {"dimensions": ["20260810"], "metrics": {"totalUsers": 5137, "sessions": 6000}},
            {"dimensions": ["20260811"], "metrics": {"totalUsers": 2839, "sessions": 3200}},
        ]


def _brand(auth_client) -> str:
    return auth_client.post("/api/brands", json={"name": "Que Universe"}).json()["id"]


def _connect_ga4(auth_client, brand_id: str) -> None:
    """Mark GA4 connected on the brand (the token itself is stubbed out)."""
    r = auth_client.post(
        f"/api/brands/{brand_id}/integrations/ga4/connect",
        json={"config": {"property_id": "123456"},
              "credentials": {"access_token": "test-token"}},
    )
    assert r.status_code == 200, r.text


def test_views_option_bar_lists_every_tab(auth_client):
    brand_id = _brand(auth_client)
    r = auth_client.get(f"/api/brands/{brand_id}/analytics/views")
    assert r.status_code == 200
    views = r.json()
    # The source report's 10 pages, plus an Overview tab.
    assert len(views) == 11
    assert views[0]["key"] == "overview"
    labels = {v["label"] for v in views}
    assert {"Product Funnel", "Funnel - Long View", "Hourly Dashboard", "Weekly Trends",
            "Website Funnel", "Device Brand", "Browser Funnel", "Checkout Dropout Funnel",
            "Daily Checkout Funnel"} <= labels
    # Each view carries the horizon it is meant to be read over.
    by_key = {v["key"]: v for v in views}
    assert by_key["hourly"]["default_days"] == 1
    assert by_key["weekly_trends"]["compare"] is True


def test_status_reports_ga4_not_connected(auth_client):
    brand_id = _brand(auth_client)
    body = auth_client.get(f"/api/brands/{brand_id}/analytics/status").json()
    assert body["can_render"] is False
    assert body["ga4"]["connected"] is False


def test_funnel_is_refused_when_ga4_is_not_connected(auth_client):
    """No sample-data fallback: an unconnected brand gets 409, not fake numbers."""
    brand_id = _brand(auth_client)
    r = auth_client.get(f"/api/brands/{brand_id}/analytics/funnel/product_funnel")
    assert r.status_code == 409
    assert "not connected" in r.json()["detail"]


def test_product_funnel_view_with_stubbed_ga4(auth_client, monkeypatch):
    brand_id = _brand(auth_client)
    _connect_ga4(auth_client, brand_id)
    stub = StubGA4()
    monkeypatch.setattr(services, "get_ga4_connector", lambda db, bid: stub)

    r = auth_client.get(f"/api/brands/{brand_id}/analytics/funnel/product_funnel"
                        f"?start=2026-07-13&end=2026-08-11")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["label"] == "Product Funnel"
    assert [t["key"] for t in body["tables"]] == [
        "by_date", "by_product", "by_date_steps", "by_product_steps"]

    by_date = body["tables"][0]
    assert by_date["rows"][0]["dim"] == "Aug 11, 2026"
    assert by_date["rows"][0]["total_users"] == 2839
    assert by_date["rows"][0]["add_to_baskets"] == 480
    assert by_date["rows"][0]["atc_pct"] == 6.0        # 300 / 5000
    assert by_date["totals"]["item_view_users"] == 111889
    assert by_date["totals"]["purchase_pct"] == 1.56   # 1745 / 111889

    # By Products is the same user-based funnel broken down by page title, so
    # its grand-total row matches the by-date table exactly (as in the source
    # report), and it carries no Total users column.
    by_product = body["tables"][1]
    assert by_product["scope"] == "users"
    assert by_product["columns"][0]["label"] == "Page title"
    assert [c["key"] for c in by_product["columns"]] == [
        "dim", "item_view_users", "add_to_baskets", "atc_pct", "checkout_pct", "purchase_pct"]
    assert by_product["totals"]["item_view_users"] == by_date["totals"]["item_view_users"]
    assert by_product["totals"]["atc_pct"] == by_date["totals"]["atc_pct"]
    assert by_product["rows"][0]["dim"] == "QUE GEHAN | MEDIUM"

    # Step-to-step by page title stops at Checkout -> Purchase, as the source does.
    assert [c["key"] for c in body["tables"][3]["columns"]] == [
        "dim", "item_view_users", "atc_pct", "atc_to_checkout_pct", "checkout_to_purchase_pct"]

    # Four tables, two dimensions: each dimension is pulled once, not per table.
    assert stub.calls.count(("date", "eventName")) == 1
    assert stub.calls.count(("pageTitle", "eventName")) == 1


def test_page_titles_endpoint(auth_client, monkeypatch):
    brand_id = _brand(auth_client)
    _connect_ga4(auth_client, brand_id)
    monkeypatch.setattr(services, "get_ga4_connector", lambda db, bid: StubGA4())
    r = auth_client.get(f"/api/brands/{brand_id}/analytics/page-titles")
    assert r.status_code == 200
    assert r.json()[0] == {"value": "QUE GEHAN | MEDIUM", "total_users": 8800}


def test_bad_date_range_is_rejected(auth_client, monkeypatch):
    brand_id = _brand(auth_client)
    _connect_ga4(auth_client, brand_id)
    monkeypatch.setattr(services, "get_ga4_connector", lambda db, bid: StubGA4())
    r = auth_client.get(f"/api/brands/{brand_id}/analytics/funnel/overview"
                        f"?start=2026-08-11&end=2026-07-13")
    assert r.status_code == 400
    r = auth_client.get(f"/api/brands/{brand_id}/analytics/funnel/nope")
    assert r.status_code == 404


def test_weekly_trends_returns_a_comparison_period(auth_client, monkeypatch):
    """Views marked `compare` also pull the preceding period of equal length."""
    brand_id = _brand(auth_client)
    _connect_ga4(auth_client, brand_id)
    monkeypatch.setattr(services, "get_ga4_connector", lambda db, bid: StubGA4())

    body = auth_client.get(
        f"/api/brands/{brand_id}/analytics/funnel/weekly_trends"
        f"?start=2026-08-01&end=2026-08-31"
    ).json()
    assert body["prev_period"] == {"start": "2026-07-01", "end": "2026-07-31"}
    assert {t["key"] for t in body["prev_tables"]} == {t["key"] for t in body["tables"]}


def test_checkout_dropout_exposes_the_micro_funnel_columns(auth_client, monkeypatch):
    brand_id = _brand(auth_client)
    _connect_ga4(auth_client, brand_id)
    monkeypatch.setattr(services, "get_ga4_connector", lambda db, bid: StubGA4())

    body = auth_client.get(
        f"/api/brands/{brand_id}/analytics/funnel/checkout_dropout"
    ).json()
    assert [t["key"] for t in body["tables"]] == ["by_date", "by_week", "by_month"]
    labels = [c["label"] for c in body["tables"][0]["columns"]]
    assert labels == ["Date", "Item view users", "ATC%", "ATC->CAS", "ATC-> CAF",
                      "ATC -> GCI", "GCI -> ASI", "ASI -> API", "API->P", "CR%"]


def test_device_brand_uses_operating_system(auth_client, monkeypatch):
    """The source labels the page 'Device Brand' but breaks down by OS."""
    brand_id = _brand(auth_client)
    _connect_ga4(auth_client, brand_id)
    monkeypatch.setattr(services, "get_ga4_connector", lambda db, bid: StubGA4())

    body = auth_client.get(f"/api/brands/{brand_id}/analytics/funnel/device_brand").json()
    by_os = next(t for t in body["tables"] if t["key"] == "by_os")
    assert by_os["dimension"] == "operatingSystem"
    assert by_os["columns"][0]["label"] == "Operating system"


def test_browser_funnel_has_the_pdp_to_checkout_column(auth_client, monkeypatch):
    brand_id = _brand(auth_client)
    _connect_ga4(auth_client, brand_id)
    monkeypatch.setattr(services, "get_ga4_connector", lambda db, bid: StubGA4())

    body = auth_client.get(f"/api/brands/{brand_id}/analytics/funnel/browser_funnel").json()
    labels = [c["label"] for c in body["tables"][0]["columns"]]
    assert "PDP -> Checkout" in labels


def test_filters_are_applied_and_echoed_back(auth_client, monkeypatch):
    brand_id = _brand(auth_client)
    _connect_ga4(auth_client, brand_id)
    monkeypatch.setattr(services, "get_ga4_connector", lambda db, bid: StubGA4())

    body = auth_client.get(
        f"/api/brands/{brand_id}/analytics/funnel/overview"
        f"?page_title=QUE+GEHAN&browser=Safari"
    ).json()
    assert body["filters"] == {"page_title": ["QUE GEHAN"], "browser": ["Safari"]}

    r = auth_client.get(f"/api/brands/{brand_id}/analytics/filter-values/nonsense")
    assert r.status_code == 400
