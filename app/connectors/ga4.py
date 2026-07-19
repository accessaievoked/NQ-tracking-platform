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
