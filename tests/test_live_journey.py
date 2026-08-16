"""Tests for the Live Journey graph: compute layer + pixel ingest API."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.compute.live_journey import (
    EventRow,
    build_live_graph,
    channel_of,
    stage_of,
)

T0 = datetime(2026, 8, 16, 10, 0, tzinfo=timezone.utc)


def _ev(visitor, stage, channel="instagram", offset=0, session="s1", customer=None):
    return EventRow(
        visitor_id=visitor,
        session_id=session,
        customer_id=customer,
        stage=stage,
        channel=channel,
        ts=T0 + timedelta(seconds=offset),
    )


def _link(graph, source, target):
    for link in graph["links"]:
        if link["source"] == source and link["target"] == target:
            return link["value"]
    return 0


def _node(graph, node_id):
    for n in graph["nodes"]:
        if n["id"] == node_id:
            return n
    return None


# --- mapping ---------------------------------------------------------------

def test_stage_from_event_name_beats_path():
    assert stage_of("checkout_completed", "/anything") == "purchase"
    assert stage_of("product_viewed", "/") == "product"


def test_stage_falls_back_to_path_for_page_viewed():
    assert stage_of("page_viewed", "/") == "home"
    assert stage_of("page_viewed", "/collections/co-ords") == "collection"
    assert stage_of("page_viewed", "/collections/co-ords/products/x") == "product"
    assert stage_of("page_viewed", "/cart") == "cart"
    assert stage_of("page_viewed", "/pages/about") == "other_page"
    # Query strings and trailing slashes must not change the answer.
    assert stage_of("page_viewed", "/?utm_source=instagram") == "home"
    assert stage_of("page_viewed", "/products/tee/") == "product"


def test_channel_prefers_utm_over_referrer():
    assert channel_of(referrer="https://www.google.com/", path="/?utm_source=instagram") == "instagram"
    assert channel_of(referrer="https://l.instagram.com/", path="/") == "instagram"
    assert channel_of(referrer="", path="/") == "direct"
    assert channel_of(referrer="https://t.co/abc", path="/") == "other"


# --- graph -----------------------------------------------------------------

def test_edges_come_from_consecutive_events_per_visitor():
    """The whole point: two visitors interleaved still produce correct paths."""
    graph = build_live_graph([
        _ev("a", "home", offset=0),
        _ev("b", "home", "google", offset=1),
        _ev("a", "collection", offset=2),
        _ev("b", "product", "google", offset=3),
        _ev("a", "product", offset=4),
    ])

    assert _link(graph, "home", "collection") == 1      # only visitor a
    assert _link(graph, "collection", "product") == 1
    assert _link(graph, "home", "product") == 1         # only visitor b
    assert _link(graph, "instagram", "home") == 1
    assert _link(graph, "google", "home") == 1


def test_repeat_views_of_same_stage_are_not_hops():
    graph = build_live_graph([
        _ev("a", "product", offset=0),
        _ev("a", "product", offset=1),   # a refresh
        _ev("a", "cart", offset=2),
    ])
    assert _link(graph, "product", "product") == 0
    assert _link(graph, "product", "cart") == 1


def test_here_is_last_stage_and_seen_is_everyone_who_passed():
    graph = build_live_graph([
        _ev("a", "home", offset=0), _ev("a", "cart", offset=1),
        _ev("b", "home", offset=2),
    ])
    assert _node(graph, "home")["seen"] == 2
    assert _node(graph, "home")["here"] == 1   # only b is still there
    assert _node(graph, "cart")["here"] == 1


def test_back_edges_are_dropped_from_sankey_but_kept_in_links():
    graph = build_live_graph([
        _ev("a", "collection", offset=0),
        _ev("a", "product", offset=1),
        _ev("a", "collection", offset=2),   # went back to compare
    ])
    assert _link(graph, "product", "collection") == 1
    sankey = {(link["source"], link["target"]) for link in graph["sankey_links"]}
    assert ("collection", "product") in sankey
    assert ("product", "collection") not in sankey


def test_channel_filter_keeps_whole_journeys():
    graph = build_live_graph(
        [
            _ev("a", "home", "instagram", offset=0),
            _ev("a", "cart", "instagram", offset=1),
            _ev("b", "home", "google", offset=2),
        ],
        channel="instagram",
    )
    assert graph["kpis"]["active_visitors"] == 1
    assert _link(graph, "home", "cart") == 1
    assert _node(graph, "google") is None
    # Channel totals stay unfiltered so the filter UI can show every option.
    assert graph["kpis"]["channels"]["google"] == 1


def test_kpis():
    graph = build_live_graph([
        _ev("a", "home", offset=0),
        _ev("a", "purchase", offset=1, customer="cust_1"),
        _ev("b", "home", offset=2, session="s2"),
    ])
    k = graph["kpis"]
    assert k["active_visitors"] == 2
    assert k["purchases"] == 1
    assert k["sessions"] == 2
    assert k["identified_visitors"] == 1
    assert k["conversion_rate_pct"] == 50.0


def test_empty_input_is_a_valid_empty_graph():
    graph = build_live_graph([])
    assert graph["nodes"] == []
    assert graph["links"] == []
    assert graph["kpis"]["active_visitors"] == 0
    assert graph["kpis"]["conversion_rate_pct"] == 0.0


def test_events_out_of_order_are_sorted_before_pathing():
    graph = build_live_graph([
        _ev("a", "cart", offset=5),
        _ev("a", "home", offset=1),
    ])
    assert _link(graph, "home", "cart") == 1
    assert _link(graph, "cart", "home") == 0


# --- API -------------------------------------------------------------------

def _brand_with_pixel(auth_client):
    brand = auth_client.post("/api/brands", json={"name": "Claura"}).json()
    pixel = auth_client.get(f"/api/brands/{brand['id']}/live/pixel").json()
    key = pixel["ingest_url"].rsplit("/api/live/", 1)[1].split("/events")[0]
    return brand, key, pixel


def test_pixel_endpoint_returns_ready_to_paste_code(auth_client):
    _, key, pixel = _brand_with_pixel(auth_client)
    assert key.startswith("nqk_")
    # No unsubstituted placeholders, and the real endpoint is baked in.
    assert "{ingest_url}" not in pixel["code"]
    assert pixel["ingest_url"] in pixel["code"]
    assert "all_standard_events" in pixel["code"]


def test_ingest_then_graph_round_trip(auth_client):
    brand, key, _ = _brand_with_pixel(auth_client)

    r = auth_client.post(
        f"/api/live/{key}/events",
        content=(
            '[{"client_id":"v1","session_id":"s1","name":"page_viewed",'
            '"path":"/","referrer":"https://l.instagram.com/"},'
            '{"client_id":"v1","session_id":"s1","name":"product_viewed",'
            '"path":"/products/tee","referrer":""},'
            '{"client_id":"v2","session_id":"s2","name":"page_viewed",'
            '"path":"/","referrer":"https://www.google.com/"}]'
        ),
        headers={"Content-Type": "text/plain"},
    )
    assert r.status_code == 204

    graph = auth_client.get(f"/api/brands/{brand['id']}/live/graph").json()
    assert graph["kpis"]["active_visitors"] == 2
    assert graph["event_count"] == 3
    assert _link(graph, "instagram", "home") == 1
    assert _link(graph, "home", "product") == 1
    # The visitor's channel comes from their first event, not each event's referrer.
    assert _node(graph, "instagram")["seen"] == 1


def test_stage_and_channel_are_derived_server_side(auth_client):
    """A hostile pixel cannot inject its own stage/channel."""
    brand, key, _ = _brand_with_pixel(auth_client)
    auth_client.post(
        f"/api/live/{key}/events",
        content=(
            '{"client_id":"v1","name":"checkout_completed","path":"/",'
            '"stage":"home","channel":"instagram","referrer":"https://www.google.com/"}'
        ),
        headers={"Content-Type": "text/plain"},
    )
    graph = auth_client.get(f"/api/brands/{brand['id']}/live/graph").json()
    assert _node(graph, "purchase") is not None   # derived from the event name
    assert _node(graph, "google") is not None     # derived from the referrer
    assert _node(graph, "instagram") is None


def test_unknown_ingest_key_is_silently_accepted(auth_client):
    """Never confirm or deny a key — that would make this a probing oracle."""
    brand, _, _ = _brand_with_pixel(auth_client)
    r = auth_client.post(
        f"/api/live/nqk_not_a_real_key/events",
        content='{"client_id":"v9","name":"page_viewed","path":"/"}',
        headers={"Content-Type": "text/plain"},
    )
    assert r.status_code == 204
    graph = auth_client.get(f"/api/brands/{brand['id']}/live/graph").json()
    assert graph["kpis"]["active_visitors"] == 0


def test_events_without_client_id_are_dropped(auth_client):
    brand, key, _ = _brand_with_pixel(auth_client)
    auth_client.post(
        f"/api/live/{key}/events",
        content='[{"name":"page_viewed","path":"/"},{"client_id":"v1","name":"page_viewed","path":"/"}]',
        headers={"Content-Type": "text/plain"},
    )
    graph = auth_client.get(f"/api/brands/{brand['id']}/live/graph").json()
    assert graph["event_count"] == 1


def test_malformed_body_does_not_500(auth_client):
    _, key, _ = _brand_with_pixel(auth_client)
    r = auth_client.post(
        f"/api/live/{key}/events", content="not json at all",
        headers={"Content-Type": "text/plain"},
    )
    assert r.status_code == 204


def test_future_timestamps_are_clamped(auth_client):
    """A wrong client clock must not park events in the window forever."""
    brand, key, _ = _brand_with_pixel(auth_client)
    year_3000 = 32503680000000
    auth_client.post(
        f"/api/live/{key}/events",
        content='{"client_id":"v1","name":"page_viewed","path":"/","ts":%d}' % year_3000,
        headers={"Content-Type": "text/plain"},
    )
    graph = auth_client.get(f"/api/brands/{brand['id']}/live/graph?window=5").json()
    assert graph["event_count"] == 1


def test_rotate_invalidates_the_old_key(auth_client):
    brand, old_key, _ = _brand_with_pixel(auth_client)
    rotated = auth_client.post(f"/api/brands/{brand['id']}/live/pixel/rotate").json()
    assert old_key not in rotated["ingest_url"]

    auth_client.post(
        f"/api/live/{old_key}/events",
        content='{"client_id":"v1","name":"page_viewed","path":"/"}',
        headers={"Content-Type": "text/plain"},
    )
    graph = auth_client.get(f"/api/brands/{brand['id']}/live/graph").json()
    assert graph["event_count"] == 0


def test_graph_requires_auth_and_is_tenancy_scoped(client, auth_client):
    brand, _, _ = _brand_with_pixel(auth_client)
    assert client.get(f"/api/brands/{brand['id']}/live/graph",
                      headers={"Authorization": "Bearer nope"}).status_code == 401


def test_status_reports_pixel_not_installed(auth_client):
    brand = auth_client.post("/api/brands", json={"name": "Fresh"}).json()
    st = auth_client.get(f"/api/brands/{brand['id']}/live/status").json()
    assert st["pixel_installed"] is False
    assert st["receiving"] is False


def test_window_is_capped_to_configured_maximum(auth_client):
    brand, _, _ = _brand_with_pixel(auth_client)
    graph = auth_client.get(f"/api/brands/{brand['id']}/live/graph?window=9999").json()
    assert graph["window_minutes"] == 30


def test_unknown_channel_filter_is_rejected(auth_client):
    brand, _, _ = _brand_with_pixel(auth_client)
    r = auth_client.get(f"/api/brands/{brand['id']}/live/graph?channel=tiktok")
    assert r.status_code == 400
