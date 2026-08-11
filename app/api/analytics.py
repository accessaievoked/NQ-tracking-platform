"""Data Insights routes — GA4 funnel views for the charts page.

Every endpoint is tenancy-scoped through ``get_owned_brand``. Nothing here falls
back to sample data: if GA4 isn't connected the API says so and the UI hides the
report rather than showing numbers nobody can trust.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.compute.funnel import CUSTOM_STEP_EVENTS, list_views
from app.db import get_db
from app.deps import get_owned_brand
from app.models import Brand
from app.services import (
    FILTER_FIELDS,
    analytics_connection_status,
    build_funnel_view,
    list_dimension_values,
    list_ga4_events,
    list_page_titles,
)

router = APIRouter(prefix="/api/brands/{brand_id}/analytics", tags=["analytics"])

MAX_RANGE_DAYS = 400


def _period(start: str | None, end: str | None, days: int) -> tuple[datetime, datetime]:
    """Resolve an explicit YYYY-MM-DD range, else the last ``days`` days."""
    if start and end:
        try:
            s = datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            e = datetime.strptime(end, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Dates must be YYYY-MM-DD")
        if e < s:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "end must be on or after start")
        if (e - s).days > MAX_RANGE_DAYS:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, f"Range is capped at {MAX_RANGE_DAYS} days"
            )
        return s, e
    end_dt = datetime.now(timezone.utc)
    return end_dt - timedelta(days=max(1, days)), end_dt


@router.get("/status")
def status_(brand: Brand = Depends(get_owned_brand), db: Session = Depends(get_db)):
    """Which sources are live, and whether the page can render a report at all."""
    return analytics_connection_status(db, brand.id)


@router.get("/views")
def views():
    """The option bar: every funnel view, with its default period length."""
    return list_views()


@router.get("/events")
def events(
    start: str | None = None,
    end: str | None = None,
    days: int = 30,
    brand: Brand = Depends(get_owned_brand),
    db: Session = Depends(get_db),
):
    """Event names this property actually sends, and how they map to funnel steps.

    Use this to pin down the checkout micro-funnel (CAS / CAF / GCI / ASI / API),
    which are custom events — then set the real names in
    ``app.compute.funnel.CUSTOM_STEP_EVENTS``.
    """
    s, e = _period(start, end, days)
    return {
        "current_mapping": CUSTOM_STEP_EVENTS,
        "events": list_ga4_events(db, brand.id, s, e),
    }


@router.get("/page-titles")
def page_titles(
    start: str | None = None,
    end: str | None = None,
    days: int = 30,
    brand: Brand = Depends(get_owned_brand),
    db: Session = Depends(get_db),
):
    """Values for the page-title filter, ordered by audience size."""
    s, e = _period(start, end, days)
    return list_page_titles(db, brand.id, s, e)


@router.get("/filter-values/{field}")
def filter_values(
    field: str,
    start: str | None = None,
    end: str | None = None,
    days: int = 30,
    brand: Brand = Depends(get_owned_brand),
    db: Session = Depends(get_db),
):
    """Values for any supported filter (page_title, source_medium, browser, ...)."""
    if field not in FILTER_FIELDS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Unknown filter '{field}'. Supported: {', '.join(FILTER_FIELDS)}",
        )
    s, e = _period(start, end, days)
    return list_dimension_values(db, brand.id, FILTER_FIELDS[field], s, e)


@router.get("/funnel/{view}")
def funnel(
    view: str,
    start: str | None = None,
    end: str | None = None,
    days: int = 30,
    page_title: list[str] = Query(default=[]),
    source_medium: list[str] = Query(default=[]),
    browser: list[str] = Query(default=[]),
    operating_system: list[str] = Query(default=[]),
    brand: Brand = Depends(get_owned_brand),
    db: Session = Depends(get_db),
):
    """Every table + chart spec for one funnel view."""
    conn = analytics_connection_status(db, brand.id)
    if not conn["can_render"]:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Google Analytics 4 is not connected for this brand.",
        )
    s, e = _period(start, end, days)
    filters = {
        "page_title": page_title,
        "source_medium": source_medium,
        "browser": browser,
        "operating_system": operating_system,
    }
    try:
        return build_funnel_view(db, brand.id, view, s, e, filters=filters)
    except KeyError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown view '{view}'")
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))
