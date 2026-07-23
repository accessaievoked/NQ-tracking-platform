"""Microsoft Clarity connector — behavioral analytics (Data Export API).

Clarity is a behavior tool: sessions, engagement, scroll depth, and friction
signals (dead clicks, rage clicks, quickbacks, script errors). It carries NO
sales or ad-spend data, so it does not feed the Money Flow / True ROAS reports.
It's scaffolded here so a future UX / conversion-friction report can consume it.

With no credentials it returns sample data so the pipeline stays offline-safe.
Live auth: a Bearer API token generated in Clarity -> Settings -> Data Export.
The Live Insights endpoint returns aggregate metrics for the last 1-3 days
(small daily quota), so it's a spot-diagnostic source, not a historical one.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.connectors.base import Connector

API_URL = "https://www.clarity.ms/export-data/api/v1/project-live-insights"


@dataclass
class ClaritySummary:
    connected: bool = False
    num_days: int = 0
    sessions: int = 0
    bot_sessions: int = 0
    distinct_users: int = 0
    pages_per_session: float = 0.0
    avg_scroll_depth_pct: float = 0.0
    dead_click_sessions: int = 0
    rage_click_sessions: int = 0
    quickback_sessions: int = 0
    excessive_scroll_sessions: int = 0
    script_error_sessions: int = 0
    by_metric: dict = field(default_factory=dict)


# Sample Live-Insights payload (shape mirrors Clarity's API) for offline use.
_SAMPLE = [
    {"metricName": "Traffic", "information": [{
        "totalSessionCount": "6420", "totalBotSessionCount": "310",
        "distinctUserCount": "5180", "pagesPerSessionPercentage": 2.7}]},
    {"metricName": "ScrollDepth", "information": [{"averageScrollDepth": 58.4}]},
    {"metricName": "DeadClickCount", "information": [{"sessionsCount": "512"}]},
    {"metricName": "RageClickCount", "information": [{"sessionsCount": "188"}]},
    {"metricName": "QuickbackClick", "information": [{"sessionsCount": "241"}]},
    {"metricName": "ExcessiveScroll", "information": [{"sessionsCount": "97"}]},
    {"metricName": "ScriptErrorCount", "information": [{"sessionsCount": "63"}]},
]


def _num(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


class ClarityConnector(Connector):
    provider = "clarity"

    def fetch(self, period_start: datetime | None = None, period_end: datetime | None = None) -> dict[str, Any]:
        token = self.credentials.get("token")
        num_days = int(self.config.get("num_days", 3))
        if not token:
            return {"source": "sample", "num_days": num_days, "data": list(_SAMPLE)}
        return self._fetch_live(token, num_days)

    def verify_connection(self) -> dict[str, Any]:
        token = self.credentials.get("token")
        if not token:
            raise ValueError("a Clarity Data Export API token is required")
        payload = self._fetch_live(token, num_days=1)
        return {"ok": True, "metrics": [m.get("metricName") for m in payload.get("data", [])]}

    def _fetch_live(self, token: str, num_days: int) -> dict[str, Any]:  # pragma: no cover - live
        import httpx

        num_days = max(1, min(int(num_days), 3))  # API allows 1-3 days
        resp = httpx.get(
            API_URL,
            headers={"Authorization": f"Bearer {token}"},
            params={"numOfDays": num_days},
            timeout=30,
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"Clarity export failed ({resp.status_code}): {resp.text}")
        return {"source": "live", "num_days": num_days, "data": resp.json()}

    def normalize(self, payload: dict[str, Any]) -> dict[str, Any]:
        """metricName -> its first information row."""
        out: dict[str, Any] = {}
        for metric in payload.get("data", []):
            info = metric.get("information") or [{}]
            out[metric.get("metricName", "")] = info[0] if info else {}
        return out

    def summarize(self, payload: dict[str, Any]) -> ClaritySummary:
        m = self.normalize(payload)
        traffic = m.get("Traffic", {})
        s = ClaritySummary(
            connected=True,
            num_days=int(payload.get("num_days", 0) or 0),
            sessions=int(_num(traffic.get("totalSessionCount"))),
            bot_sessions=int(_num(traffic.get("totalBotSessionCount"))),
            distinct_users=int(_num(traffic.get("distinctUserCount"))),
            pages_per_session=round(_num(traffic.get("pagesPerSessionPercentage")), 2),
            avg_scroll_depth_pct=round(_num(m.get("ScrollDepth", {}).get("averageScrollDepth")), 2),
            dead_click_sessions=int(_num(m.get("DeadClickCount", {}).get("sessionsCount"))),
            rage_click_sessions=int(_num(m.get("RageClickCount", {}).get("sessionsCount"))),
            quickback_sessions=int(_num(m.get("QuickbackClick", {}).get("sessionsCount"))),
            excessive_scroll_sessions=int(_num(m.get("ExcessiveScroll", {}).get("sessionsCount"))),
            script_error_sessions=int(_num(m.get("ScriptErrorCount", {}).get("sessionsCount"))),
            by_metric=m,
        )
        return s
