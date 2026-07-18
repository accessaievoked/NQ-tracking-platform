"""Meta (Facebook/Instagram) Ads connector — Marketing API insights.

Pulls account-level spend and purchase conversion value for a period, and maps
them into the AdSpend shape the Money Flow compute expects.

  reported_spend   = insights.spend
  reported_revenue = sum of action_values for purchase actions
                     (used for the platform's claimed ROAS)

With no credentials it returns empty sample data so the pipeline stays offline-
safe. Live auth uses a Meta access token + ad account id; full OAuth / App Review
is the productionization step (a token can be stored directly for testing).
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from app.compute.money_flow import AdSpend
from app.connectors.base import Connector

GRAPH_VERSION = "v21.0"
_PURCHASE_ACTIONS = {
    "omni_purchase",
    "purchase",
    "offsite_conversion.fb_pixel_purchase",
}


class MetaAdsConnector(Connector):
    provider = "meta_ads"

    def fetch(self, period_start: datetime | None, period_end: datetime | None) -> dict[str, Any]:
        account = self.config.get("ad_account_id")
        token = self.credentials.get("access_token")
        if not (account and token):
            return {"source": "sample", "data": []}
        return self._fetch_live(account, token, period_start, period_end)

    def verify_connection(self) -> dict[str, Any]:
        account = _normalize_account(self.config.get("ad_account_id", ""))
        token = self.credentials.get("access_token")
        if not (account and token):
            raise ValueError("ad_account_id (config) and access_token (credentials) are required")

        import httpx

        resp = httpx.get(
            f"https://graph.facebook.com/{GRAPH_VERSION}/{account}",
            params={"fields": "name,currency,account_status", "access_token": token},
            timeout=20,
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"Meta verification failed ({resp.status_code}): {resp.text}")
        return resp.json()

    def _fetch_live(
        self,
        account: str,
        token: str,
        period_start: datetime | None,
        period_end: datetime | None,
    ) -> dict[str, Any]:  # pragma: no cover - requires live Meta account
        import httpx

        account = _normalize_account(account)
        params: dict[str, Any] = {
            "fields": "spend,action_values,purchase_roas",
            "level": "account",
            "access_token": token,
        }
        if period_start and period_end:
            params["time_range"] = json.dumps(
                {"since": period_start.strftime("%Y-%m-%d"), "until": period_end.strftime("%Y-%m-%d")}
            )
        resp = httpx.get(
            f"https://graph.facebook.com/{GRAPH_VERSION}/{account}/insights",
            params=params,
            timeout=30,
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"Meta insights failed ({resp.status_code}): {resp.text}")
        return {"source": "live", "data": resp.json().get("data", [])}

    def to_ad_spend(self, payload: dict[str, Any]) -> AdSpend:
        spend = 0.0
        revenue = 0.0
        for row in payload.get("data", []):
            spend += float(row.get("spend", 0) or 0)
            for av in row.get("action_values", []) or []:
                if av.get("action_type") in _PURCHASE_ACTIONS:
                    revenue += float(av.get("value", 0) or 0)
        return AdSpend(
            reported_spend=round(spend, 2),
            reported_revenue=round(revenue, 2),
            by_platform={"meta_ads": round(spend, 2)},
            connected=True,
        )

    def normalize(self, payload: dict[str, Any]) -> Any:  # not used; kept for interface
        return payload.get("data", [])


def _normalize_account(account: str) -> str:
    account = str(account or "")
    return account if account.startswith("act_") else f"act_{account}"
