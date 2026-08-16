"""Live Journey: turn raw storefront pixel events into a real-time visitor graph.

GA4's Realtime API can only return bucket *counts* — it exposes no user-level
identifier, so it can tell you 12 people are on the cart page but never that 8 of
them came from the collection page. Every event we collect carries Shopify's
``clientId``, so consecutive events for the same visitor become a directed edge
and the funnel becomes a graph.

Deterministic and dependency-free, exactly like ``money_flow`` and ``tracking``:
rows in, graph out, no DB and no I/O. The API layer does the fetching.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable

# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

# Acquisition channels. This order is also the legend order on the dashboard,
# and the colour slots are validated against it — don't reorder casually.
CHANNELS: list[str] = ["instagram", "facebook", "google", "direct", "other"]

# Funnel stages. ``col`` drives the left-to-right layout so the graph stays
# visually stable while traffic moves through it.
STAGES: list[dict[str, Any]] = [
    {"id": "home", "label": "Home", "col": 1},
    {"id": "collection", "label": "Collection", "col": 2},
    {"id": "search", "label": "Search", "col": 2},
    {"id": "product", "label": "Product", "col": 3},
    {"id": "other_page", "label": "Other page", "col": 3},
    {"id": "cart", "label": "Cart", "col": 4},
    {"id": "checkout", "label": "Checkout", "col": 5},
    {"id": "payment", "label": "Payment", "col": 6},
    {"id": "purchase", "label": "Purchase", "col": 7},
]

STAGE_BY_ID: dict[str, dict[str, Any]] = {s["id"]: s for s in STAGES}

# Shopify web-pixel standard event -> stage.
EVENT_TO_STAGE: dict[str, str] = {
    "collection_viewed": "collection",
    "search_submitted": "search",
    "product_viewed": "product",
    "cart_viewed": "cart",
    "product_added_to_cart": "cart",
    "checkout_started": "checkout",
    "checkout_contact_info_submitted": "checkout",
    "checkout_address_info_submitted": "checkout",
    "checkout_shipping_info_submitted": "checkout",
    "payment_info_submitted": "payment",
    "checkout_completed": "purchase",
}


def stage_of(event_name: str | None, path: str | None = "/") -> str:
    """Resolve an event to a funnel stage.

    ``page_viewed`` carries no intrinsic stage, so it falls back to the URL path.
    """
    direct = EVENT_TO_STAGE.get(event_name or "")
    if direct:
        return direct

    p = (path or "/").split("?", 1)[0].lower().rstrip("/") or "/"
    if p == "/":
        return "home"
    if p.startswith("/collections") and "/products/" in p:
        return "product"
    if p.startswith("/collections"):
        return "collection"
    if p.startswith("/products"):
        return "product"
    if p.startswith("/search"):
        return "search"
    if p.startswith("/cart"):
        return "cart"
    if p.startswith("/checkout") or p.startswith("/checkouts"):
        return "checkout"
    return "other_page"


def normalize_channel(raw: str | None) -> str:
    s = (raw or "").strip().lower()
    if "instagram" in s or s == "ig":
        return "instagram"
    if "facebook" in s or s in {"fb", "meta"} or "meta" in s:
        return "facebook"
    if "google" in s or "adwords" in s:
        return "google"
    if s in {"direct", "(direct)", ""}:
        return "direct"
    return s if s in CHANNELS else "other"


def channel_of(
    referrer: str | None = "",
    path: str | None = "",
    utm_source: str | None = "",
) -> str:
    """Derive the acquisition channel. utm wins over referrer because it's explicit."""
    if utm_source:
        return normalize_channel(utm_source)

    p = path or ""
    if "utm_source=" in p:
        tail = p.split("utm_source=", 1)[1]
        return normalize_channel(tail.split("&", 1)[0])

    ref = (referrer or "").lower()
    if not ref:
        return "direct"
    if "instagram" in ref:
        return "instagram"
    if "facebook" in ref or "fb." in ref or "meta." in ref:
        return "facebook"
    if "google" in ref:
        return "google"
    return "other"


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EventRow:
    """One pixel event, already normalized. Mirrors the ``live_events`` columns
    the API selects, so the compute layer never touches the ORM."""

    visitor_id: str
    session_id: str | None
    customer_id: str | None
    stage: str
    channel: str
    ts: datetime


def _titlecase(s: str) -> str:
    return s[:1].upper() + s[1:] if s else s


def _label_for(node_id: str) -> str:
    stage = STAGE_BY_ID.get(node_id)
    return stage["label"] if stage else _titlecase(node_id)


def _col_for(node_id: str) -> int:
    if node_id in CHANNELS:
        return 0
    stage = STAGE_BY_ID.get(node_id)
    return stage["col"] if stage else 3


def build_live_graph(
    rows: Iterable[EventRow],
    channel: str = "all",
) -> dict[str, Any]:
    """Aggregate a window of events into nodes, edges and headline numbers.

    ``rows`` may arrive in any order; they're grouped and sorted per visitor here.
    ``channel`` filters by the visitor's *entry* channel rather than per-event, so
    a filtered view still shows whole journeys instead of orphaned fragments.
    """
    # Group by visitor.
    timelines: dict[str, list[EventRow]] = {}
    for r in rows:
        timelines.setdefault(r.visitor_id, []).append(r)

    nodes: dict[str, dict[str, set[str]]] = {}
    links: dict[tuple[str, str], set[str]] = {}

    active: set[str] = set()
    sessions: set[str] = set()
    purchasers: set[str] = set()
    identified: set[str] = set()
    by_channel: dict[str, int] = {}

    def touch(node_id: str) -> dict[str, set[str]]:
        return nodes.setdefault(node_id, {"here": set(), "seen": set()})

    def add_link(src: str, dst: str, visitor: str) -> None:
        if not src or not dst or src == dst:
            return
        links.setdefault((src, dst), set()).add(visitor)

    for visitor_id, events in timelines.items():
        if not events:
            continue
        events.sort(key=lambda e: e.ts)

        entry_channel = events[0].channel or "direct"
        by_channel[entry_channel] = by_channel.get(entry_channel, 0) + 1

        if channel != "all" and entry_channel != channel:
            continue

        active.add(visitor_id)

        # Collapse consecutive repeats: a refresh is not a hop.
        path: list[str] = []
        for e in events:
            if e.session_id:
                sessions.add(e.session_id)
            if e.customer_id:
                identified.add(visitor_id)
            stage = e.stage or "other_page"
            if not path or path[-1] != stage:
                path.append(stage)
            if stage == "purchase":
                purchasers.add(visitor_id)

        # The acquisition channel is node zero.
        touch(entry_channel)["seen"].add(visitor_id)
        touch(entry_channel)["here"].add(visitor_id)
        add_link(entry_channel, path[0], visitor_id)

        for i, stage in enumerate(path):
            touch(stage)["seen"].add(visitor_id)
            if i:
                add_link(path[i - 1], stage, visitor_id)

        # Where this visitor is right now = the last stage they touched.
        touch(path[-1])["here"].add(visitor_id)

    node_list = [
        {
            "id": node_id,
            "label": _label_for(node_id),
            "kind": "channel" if node_id in CHANNELS else "stage",
            "col": _col_for(node_id),
            "here": len(v["here"]),
            "seen": len(v["seen"]),
        }
        for node_id, v in nodes.items()
    ]
    node_list.sort(key=lambda n: (n["col"], -n["seen"], n["id"]))

    link_list = [
        {"source": src, "target": dst, "value": len(visitors)}
        for (src, dst), visitors in links.items()
    ]
    link_list.sort(key=lambda link: -link["value"])

    total = len(active)
    return {
        "nodes": node_list,
        "links": link_list,
        # A sankey needs a DAG; the network view keeps the back-edges.
        "sankey_links": acyclic(link_list, node_list),
        "kpis": {
            "active_visitors": total,
            "sessions": len(sessions),
            "purchases": len(purchasers),
            "identified_visitors": len(identified),
            "conversion_rate_pct": round(len(purchasers) / total * 100, 2) if total else 0.0,
            "channels": {c: by_channel[c] for c in CHANNELS if by_channel.get(c)},
        },
    }


def acyclic(
    links: list[dict[str, Any]],
    nodes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Drop edges that move backwards or sideways in the funnel.

    Real journeys contain back-edges (product -> collection to compare) and a
    sankey cannot render a cycle. This is presentation-only: the numbers in
    ``links`` are untouched, and the network view renders them in full.
    """
    col = {n["id"]: n["col"] for n in nodes}
    return [link for link in links if col.get(link["source"], 0) < col.get(link["target"], 0)]


def empty_graph() -> dict[str, Any]:
    """The shape the UI expects when nothing has been collected yet."""
    return build_live_graph([])
