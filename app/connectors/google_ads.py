"""Google Ads connector — Ads API (REST) spend + conversion value.

Pulls account-level cost and conversion value for a period and maps them into
the AdSpend shape the Money Flow compute expects, alongside Meta:

  reported_spend   = metrics.cost_micros / 1e6
  reported_revenue = metrics.conversions_value  (the platform's claimed revenue)

Auth is an OAuth2 access token with the `adwords` scope, minted from the
client's own refresh token by app.connectors.google_auth.refresh_access_token —
the same durable, keyless path GA4 uses. Two extra things the Ads API needs and
GA4 does not:

  * developer-token   — issued to the manager (MCC) account, sent on every call
  * login-customer-id — the MCC account id, set when querying a client account
                        the manager operates on behalf of

With no credentials it returns empty sample data so the pipeline stays
offline-safe, matching the other connectors.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.compute.money_flow import AdSpend
from app.connectors.base import Connector

# The Ads API deprecates versions roughly yearly; bump here (or set
# config["api_version"]) when Google retires this one.
API_VERSION = "v21"
API_ROOT = "https://googleads.googleapis.com"

_SPEND_QUERY = """
    SELECT metrics.cost_micros, metrics.conversions_value, metrics.conversions
    FROM customer
    WHERE segments.date BETWEEN '{since}' AND '{until}'
""".strip()

_VERIFY_QUERY = """
    SELECT customer.id, customer.descriptive_name, customer.currency_code
    FROM customer
    LIMIT 1
""".strip()


class GoogleAdsConnector(Connector):
    provider = "google_ads"

    def fetch(self, period_start: datetime | None, period_end: datetime | None) -> dict[str, Any]:
        if not self._ready():
            return {"source": "sample", "data": []}
        return self._fetch_live(period_start, period_end)

    def verify_connection(self) -> dict[str, Any]:
        if not self._ready():
            raise ValueError(
                "customer_id (config) plus access_token and developer_token "
                "(credentials) are required"
            )
        rows = self._search(_VERIFY_QUERY)
        if not rows:
            raise RuntimeError(
                "Google Ads returned no customer row — check the customer ID and "
                "that the manager account has access to it."
            )
        customer = rows[0].get("customer", {})
        return {
            "customer_id": _digits(self.config.get("customer_id")),
            "name": customer.get("descriptiveName", ""),
            "currency": customer.get("currencyCode", ""),
        }

    # --- internals --------------------------------------------------------

    def _ready(self) -> bool:
        return bool(
            self.config.get("customer_id")
            and self.credentials.get("access_token")
            and self.credentials.get("developer_token")
        )

    def _headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.credentials['access_token']}",
            "developer-token": self.credentials["developer_token"],
            "Content-Type": "application/json",
        }
        # Only needed when the queried account sits under a manager account.
        login_customer_id = _digits(self.config.get("login_customer_id"))
        if login_customer_id:
            headers["login-customer-id"] = login_customer_id
        return headers

    def _search(self, query: str) -> list[dict[str, Any]]:
        import httpx

        version = self.config.get("api_version") or API_VERSION
        customer_id = _digits(self.config.get("customer_id"))
        resp = httpx.post(
            f"{API_ROOT}/{version}/customers/{customer_id}/googleAds:searchStream",
            headers=self._headers(),
            json={"query": query},
            timeout=30,
        )
        if resp.status_code >= 400:
            raise RuntimeError(
                f"Google Ads request failed ({resp.status_code}): {resp.text}"
            )
        # searchStream answers with a list of chunks, each holding its own rows.
        payload = resp.json()
        chunks = payload if isinstance(payload, list) else [payload]
        rows: list[dict[str, Any]] = []
        for chunk in chunks:
            rows.extend(chunk.get("results", []) or [])
        return rows

    def _fetch_live(
        self, period_start: datetime | None, period_end: datetime | None
    ) -> dict[str, Any]:  # pragma: no cover - requires a live Ads account
        if not (period_start and period_end):
            return {"source": "sample", "data": []}
        query = _SPEND_QUERY.format(
            since=period_start.strftime("%Y-%m-%d"),
            until=period_end.strftime("%Y-%m-%d"),
        )
        return {"source": "live", "data": self._search(query)}

    # --- mapping ----------------------------------------------------------

    def to_ad_spend(self, payload: dict[str, Any]) -> AdSpend:
        spend = 0.0
        revenue = 0.0
        for row in payload.get("data", []):
            metrics = row.get("metrics", {}) or {}
            spend += float(metrics.get("costMicros", 0) or 0) / 1_000_000
            revenue += float(metrics.get("conversionsValue", 0) or 0)
        return AdSpend(
            reported_spend=round(spend, 2),
            reported_revenue=round(revenue, 2),
            by_platform={"google_ads": round(spend, 2)},
            connected=True,
        )

    def normalize(self, payload: dict[str, Any]) -> Any:  # not used; interface parity
        return payload.get("data", [])


def _digits(value: Any) -> str:
    """Ads API wants bare digits: 123-456-7890 -> 1234567890."""
    return "".join(ch for ch in str(value or "") if ch.isdigit())
