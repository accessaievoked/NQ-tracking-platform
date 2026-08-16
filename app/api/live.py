"""Live Journey routes — storefront pixel ingest + the real-time graph.

Two very different security postures live in this module, hence the two routers:

``ingest_router``   Public. Called from the shopper's browser on a merchant
                    domain, authenticated only by a per-brand write-only key.
                    It can add events to one brand and read nothing.

``router``          Normal platform surface: session token + ``get_owned_brand``
                    tenancy, same as every other brand route.
"""
from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.compute.live_journey import (
    CHANNELS,
    STAGES,
    EventRow,
    build_live_graph,
    channel_of,
    stage_of,
)
from app.config import settings
from app.db import get_db
from app.deps import get_owned_brand
from app.models import Brand, LiveEvent
from app.pixel import render_pixel

ingest_router = APIRouter(prefix="/api/live", tags=["live"])
router = APIRouter(prefix="/api/brands/{brand_id}/live", tags=["live"])

# The pixel runs on the merchant's own domain, so ingest is inherently
# cross-origin. `*` is safe on this one endpoint specifically: it is write-only,
# keyed, and returns no body — there is nothing for a hostile origin to read.
_CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "content-type",
    "Access-Control-Max-Age": "86400",
}

MAX_BODY_BYTES = 256 * 1024

# Pruning is opportunistic rather than a scheduled job: no worker process exists
# yet, and the ingest path is the only thing guaranteed to run often. Guarded so
# it fires at most once a minute per process.
_last_prune: datetime | None = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(dt: datetime) -> datetime:
    """SQLite hands back naive datetimes; treat those as the UTC we wrote."""
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def new_ingest_key() -> str:
    return "nqk_" + secrets.token_urlsafe(24)


def ensure_ingest_key(db: Session, brand: Brand) -> str:
    """Lazily mint a brand's ingest key so existing brands don't need backfilling."""
    if not brand.live_ingest_key:
        brand.live_ingest_key = new_ingest_key()
        db.commit()
        db.refresh(brand)
    return brand.live_ingest_key


# ---------------------------------------------------------------------------
# Ingest (public, keyed)
# ---------------------------------------------------------------------------


@ingest_router.options("/{ingest_key}/events")
def ingest_preflight(ingest_key: str) -> Response:
    """Present for correctness, but the pixel is built to never trigger it:
    it posts text/plain, which is a CORS-simple content type."""
    return Response(status_code=204, headers=_CORS)


@ingest_router.post("/{ingest_key}/events")
async def ingest(
    ingest_key: str,
    request: Request,
    db: Session = Depends(get_db),
) -> Response:
    """Accept one event or a batch from the storefront pixel.

    Returns 204 in every non-fatal case, including an unknown key. A pixel in a
    shopper's browser can do nothing useful with an error, and echoing "no such
    brand" would turn this into a key-probing oracle.
    """
    raw = await request.body()
    if len(raw) > MAX_BODY_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Payload too large")

    try:
        payload = json.loads(raw or b"{}")
    except ValueError:
        return Response(status_code=204, headers=_CORS)

    batch = payload if isinstance(payload, list) else [payload]
    batch = [e for e in batch if isinstance(e, dict)][: settings.live_max_batch]
    if not batch:
        return Response(status_code=204, headers=_CORS)

    await run_in_threadpool(_persist, db, ingest_key, batch)
    return Response(status_code=204, headers=_CORS)


def _persist(db: Session, ingest_key: str, batch: list[dict]) -> None:
    brand_id = db.scalar(select(Brand.id).where(Brand.live_ingest_key == ingest_key))
    if not brand_id:
        return

    now = _now()
    rows = [_to_row(brand_id, raw, now) for raw in batch]
    db.add_all([r for r in rows if r is not None])
    db.commit()
    _maybe_prune(db, now)


def _to_row(brand_id: str, raw: dict, now: datetime) -> LiveEvent | None:
    visitor_id = str(raw.get("client_id") or raw.get("clientId") or "").strip()
    if not visitor_id:
        return None  # without the thread there is no journey to draw

    path = str(raw.get("path") or "/")[:512]
    name = str(raw.get("name") or "page_viewed")[:64]

    # A client clock that is wrong (or lying) must not park events in the future
    # where they'd sit in the window forever.
    ts = now
    epoch_ms = raw.get("ts")
    if isinstance(epoch_ms, (int, float)) and epoch_ms > 0:
        try:
            parsed = datetime.fromtimestamp(float(epoch_ms) / 1000.0, tz=timezone.utc)
            ts = min(parsed, now)
        except (OverflowError, OSError, ValueError):
            ts = now

    return LiveEvent(
        brand_id=brand_id,
        visitor_id=visitor_id[:64],
        session_id=(str(raw.get("session_id") or "") or None),
        customer_id=(str(raw.get("customer_id") or "") or None),
        event_name=name,
        # Derived here, never taken from the client.
        stage=stage_of(name, path),
        channel=channel_of(referrer=raw.get("referrer"), path=path),
        path=path,
        ts=ts,
    )


def _maybe_prune(db: Session, now: datetime) -> None:
    global _last_prune
    if _last_prune and (now - _last_prune) < timedelta(minutes=1):
        return
    _last_prune = now
    cutoff = now - timedelta(minutes=settings.live_retention_minutes)
    db.execute(delete(LiveEvent).where(LiveEvent.ts < cutoff))
    db.commit()


# ---------------------------------------------------------------------------
# Dashboard (session auth + tenancy)
# ---------------------------------------------------------------------------


@router.get("/graph")
def graph(
    window: int = 30,
    channel: str = "all",
    brand: Brand = Depends(get_owned_brand),
    db: Session = Depends(get_db),
):
    """Nodes, edges and headline numbers for the last ``window`` minutes."""
    if channel != "all" and channel not in CHANNELS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown channel '{channel}'")
    window = max(1, min(int(window), settings.live_window_minutes))

    cutoff = _now() - timedelta(minutes=window)
    rows = db.execute(
        select(
            LiveEvent.visitor_id,
            LiveEvent.session_id,
            LiveEvent.customer_id,
            LiveEvent.stage,
            LiveEvent.channel,
            LiveEvent.ts,
        )
        .where(LiveEvent.brand_id == brand.id, LiveEvent.ts >= cutoff)
        .order_by(LiveEvent.visitor_id, LiveEvent.ts)
    ).all()

    graph_data = build_live_graph(
        (
            EventRow(
                visitor_id=r.visitor_id,
                session_id=r.session_id,
                customer_id=r.customer_id,
                stage=r.stage,
                channel=r.channel,
                ts=_as_utc(r.ts),
            )
            for r in rows
        ),
        channel=channel,
    )
    return {
        **graph_data,
        "window_minutes": window,
        "channel": channel,
        "event_count": len(rows),
        "generated_at": _now().isoformat(),
    }


@router.get("/status")
def live_status(
    brand: Brand = Depends(get_owned_brand),
    db: Session = Depends(get_db),
):
    """Whether the pixel has ever reported in — drives the setup empty state."""
    last_ts = db.scalar(
        select(LiveEvent.ts)
        .where(LiveEvent.brand_id == brand.id)
        .order_by(LiveEvent.ts.desc())
        .limit(1)
    )
    last = _as_utc(last_ts) if last_ts else None
    return {
        "pixel_installed": last is not None,
        "last_event_at": last.isoformat() if last else None,
        "receiving": bool(last and (_now() - last) < timedelta(minutes=5)),
        "window_minutes": settings.live_window_minutes,
        "channels": CHANNELS,
        "stages": STAGES,
    }


@router.get("/pixel")
def pixel(
    brand: Brand = Depends(get_owned_brand),
    db: Session = Depends(get_db),
):
    """The copy-paste pixel, pre-filled with this brand's ingest URL."""
    key = ensure_ingest_key(db, brand)
    ingest_url = f"{settings.app_base_url.rstrip('/')}/api/live/{key}/events"
    return {
        "ingest_url": ingest_url,
        "code": render_pixel(
            brand_name=brand.name,
            brand_id=brand.id,
            ingest_url=ingest_url,
            generated_at=_now().strftime("%Y-%m-%d"),
        ),
    }


@router.post("/pixel/rotate")
def rotate_pixel(
    brand: Brand = Depends(get_owned_brand),
    db: Session = Depends(get_db),
):
    """Issue a new ingest key. The old one stops working immediately, so the
    pixel in the storefront must be replaced with the newly generated code."""
    brand.live_ingest_key = new_ingest_key()
    db.commit()
    db.refresh(brand)
    return pixel(brand=brand, db=db)
