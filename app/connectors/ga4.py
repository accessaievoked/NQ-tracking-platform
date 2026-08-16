"""Google Analytics 4 connector (Analytics Data API v1).

Pulls period totals for traffic + on-site ecommerce (sessions, users, purchases,
GA4-reported revenue, conversions). GA4's purchase revenue is the site's own
attribution — comparing it to Shopify's actually-collected cash is a future
report ("what GA4 claims vs what reached you").

Auth is a Google OAuth2 access token with the analytics.readonly scope. With no
credentials it returns deterministic sample data so the pipeline stays offline.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.connectors.base import Connector

GA4_API = "https://analyticsdata.googleapis.com/v1beta"
METRICS = [
    "sessions",
    "activeUsers",
    "newUsers",
    "engagedSessions",
    "ecommercePurchases",
    "purchaseRevenue",
    "conversions",
]


class GA4Connector(Connector):
    provider = "ga4"

    def fetch(self, period_start: datetime | None, period_end: datetime | None) -> dict[str, Any]:
        prop = self.config.get("property_id")
        token = self.credentials.get("access_token")
        if not (prop and token):
            return {"source": "sample", "report": _sample_report()}
        return self._fetch_live(prop, token, period_start, period_end)

    def verify_connection(self) -> dict[str, Any]:
        prop = self.config.get("property_id")
        token = self.credentials.get("access_token")
        if not (prop and token):
            raise ValueError("property_id (config) and access_token (credentials) are required")

        import httpx

        resp = httpx.get(
            f"{GA4_API}/properties/{prop}/metadata",
            headers={"Authorization": f"Bearer {token}"},
            timeout=20,
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"GA4 verification failed ({resp.status_code}): {resp.text}")
        return {"property_id": prop, "name": resp.json().get("name", "")}

    def _fetch_live(
        self,
        prop: str,
        token: str,
        period_start: datetime | None,
        period_end: datetime | None,
    ) -> dict[str, Any]:  # pragma: no cover - requires live GA4 property
        import httpx

        start = period_start.strftime("%Y-%m-%d") if period_start else "30daysAgo"
        end = period_end.strftime("%Y-%m-%d") if period_end else "today"
        body = {
            "dateRanges": [{"startDate": start, "endDate": end}],
            "metrics": [{"name": m} for m in METRICS],
        }
        resp = httpx.post(
            f"{GA4_API}/properties/{prop}:runReport",
            headers={"Authorization": f"Bearer {token}"},
            json=body,
            timeout=30,
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"GA4 runReport failed ({resp.status_code}): {resp.text}")
        return {"source": "live", "report": resp.json()}

    # --- Generic reporting -------------------------------------------------

    def run_report(
        self,
        *,
        dimensions: list[str],
        metrics: list[str],
        start: datetime | str,
        end: datetime | str,
        dimension_filter: dict[str, Any] | None = None,
        order_bys: list[dict[str, Any]] | None = None,
        limit: int = 100000,
    ) -> list[dict[str, Any]]:
        """Run an arbitrary GA4 report and return parsed rows.

        Each row is ``{"dimensions": [...], "metrics": {name: float}}``. This is
        the building block the funnel views compose: they all boil down to
        "count users per funnel event, broken down by some dimension".

        Raises if the property/token are missing — callers that need a
        connected-only guarantee (the Data Insights page) rely on that rather
        than silently receiving sample numbers.
        """
        prop = self.config.get("property_id")
        token = self.credentials.get("access_token")
        if not (prop and token):
            raise RuntimeError("GA4 is not connected (property_id + access_token required)")

        import httpx

        body: dict[str, Any] = {
            "dateRanges": [{"startDate": _date_str(start), "endDate": _date_str(end)}],
            "dimensions": [{"name": d} for d in dimensions],
            "metrics": [{"name": m} for m in metrics],
            "limit": limit,
        }
        if dimension_filter:
            body["dimensionFilter"] = dimension_filter
        if order_bys:
            body["orderBys"] = order_bys

        resp = httpx.post(
            f"{GA4_API}/properties/{prop}:runReport",
            headers={"Authorization": f"Bearer {token}"},
            json=body,
            timeout=60,
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"GA4 runReport failed ({resp.status_code}): {resp.text}")
        return parse_rows(resp.json())

    def summarize(self, payload: dict[str, Any]) -> dict[str, float]:
        report = payload.get("report", {})
        headers = [h.get("name") for h in report.get("metricHeaders", [])]
        rows = report.get("rows", [])
        values = rows[0].get("metricValues", []) if rows else []
        out: dict[str, float] = {}
        for i, name in enumerate(headers):
            out[name] = float(values[i].get("value", 0)) if i < len(values) else 0.0
        return out

    def normalize(self, payload: dict[str, Any]) -> Any:  # interface parity
        return self.summarize(payload)


def _date_str(value: datetime | str) -> str:
    """GA4 accepts YYYY-MM-DD or relative literals like '30daysAgo'/'today'."""
    return value.strftime("%Y-%m-%d") if isinstance(value, datetime) else str(value)


def parse_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten a runReport response into ``[{"dimensions": [...], "metrics": {...}}]``.

    Pure function so the funnel compute can be unit-tested against canned API
    payloads without touching the network.
    """
    dim_names = [h.get("name") for h in report.get("dimensionHeaders", [])]
    met_names = [h.get("name") for h in report.get("metricHeaders", [])]
    out: list[dict[str, Any]] = []
    for row in report.get("rows", []) or []:
        dims = [d.get("value", "") for d in row.get("dimensionValues", [])]
        vals = row.get("metricValues", [])
        mets: dict[str, float] = {}
        for i, name in enumerate(met_names):
            raw = vals[i].get("value", "0") if i < len(vals) else "0"
            try:
                mets[name] = float(raw)
            except (TypeError, ValueError):
                mets[name] = 0.0
        out.append({"dimensions": dims, "metrics": mets, "keys": dict(zip(dim_names, dims))})
    return out


def in_list_filter(field: str, values: list[str]) -> dict[str, Any]:
    """A GA4 ``dimensionFilter`` matching ``field`` against any of ``values``."""
    return {"filter": {"fieldName": field, "inListFilter": {"values": list(values)}}}


def and_filters(*filters: dict[str, Any] | None) -> dict[str, Any] | None:
    """Combine dimension filters with AND, ignoring ``None`` entries."""
    active = [f for f in filters if f]
    if not active:
        return None
    if len(active) == 1:
        return active[0]
    return {"andGroup": {"expressions": active}}


def _sample_report() -> dict[str, Any]:
    return {
        "metricHeaders": [{"name": m} for m in METRICS],
        "rows": [
            {"metricValues": [
                {"value": "12450"},   # sessions
                {"value": "8930"},    # activeUsers
                {"value": "6120"},    # newUsers
                {"value": "7340"},    # engagedSessions
                {"value": "512"},     # ecommercePurchases
                {"value": "1863500"}, # purchaseRevenue
                {"value": "640"},     # conversions
            ]}
        ],
    }
