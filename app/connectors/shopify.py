"""Shopify connector (Admin REST API) + Dev Dashboard auth.

Two credential styles are supported:

  * Legacy custom app:   {"access_token": "shpat_..."}   (permanent token)
  * Dev Dashboard app:   {"client_id": "...", "client_secret": "..."}
        -> exchanged via the client-credentials grant for a token that
           expires in ~24h. Token caching/refresh lives in the service layer
           (see app.services.get_valid_shopify_token) because it needs DB access.

The connector itself only ever receives a ready access token; with no token it
returns deterministic sample data so the pipeline runs offline.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.connectors.base import Connector

SHOPIFY_API_VERSION = "2024-10"
MAX_RETRIES = 5


@dataclass
class TokenBundle:
    access_token: str
    scope: str
    expires_in: int  # seconds until expiry (Dev Dashboard tokens: ~86399)

    def expires_at(self, now: float | None = None) -> float:
        return (now if now is not None else time.time()) + self.expires_in


def exchange_client_credentials(
    shop_domain: str, client_id: str, client_secret: str
) -> TokenBundle:
    """Exchange Dev Dashboard credentials for a short-lived Admin API token.

    POST https://{shop}/admin/oauth/access_token
        {client_id, client_secret, grant_type: "client_credentials"}
    -> {access_token, scope, expires_in}
    """
    import httpx

    resp = httpx.post(
        f"https://{shop_domain}/admin/oauth/access_token",
        json={
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "client_credentials",
        },
        headers={"Accept": "application/json"},
        timeout=20,
    )
    if resp.status_code >= 400:
        raise RuntimeError(
            f"Shopify token exchange failed ({resp.status_code}): {resp.text}"
        )
    data = resp.json()
    return TokenBundle(
        access_token=data["access_token"],
        scope=data.get("scope", ""),
        expires_in=int(data.get("expires_in", 86399)),
    )


class ShopifyConnector(Connector):
    provider = "shopify"

    def fetch(self, period_start: datetime | None, period_end: datetime | None) -> dict[str, Any]:
        shop = self.config.get("shop_domain")
        token = self.credentials.get("access_token")
        if not (shop and token):
            return {"source": "sample", "orders": _sample_orders()}
        return self._fetch_live(shop, token, period_start, period_end)

    def verify_connection(self) -> dict[str, Any]:
        """Validate an access token against shop.json. Raises on failure."""
        shop = self.config.get("shop_domain")
        token = self.credentials.get("access_token")
        if not (shop and token):
            raise ValueError("shop_domain (config) and access_token (credentials) are required")

        import httpx

        resp = httpx.get(
            f"https://{shop}/admin/api/{SHOPIFY_API_VERSION}/shop.json",
            headers={"X-Shopify-Access-Token": token},
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json().get("shop", {})

    def normalize(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for o in payload.get("orders", []):
            out.append(
                {
                    "order_id": str(o.get("id")),
                    "total_price": float(o.get("total_price", 0) or 0),
                    "total_discounts": float(o.get("total_discounts", 0) or 0),
                    "total_refunded": _refunded_amount(o),
                    "is_cancelled": bool(o.get("cancelled_at")),
                    "fulfillment": _norm_fulfillment(o.get("fulfillment_status")),
                }
            )
        return out

    def _fetch_live(
        self,
        shop: str,
        token: str,
        period_start: datetime | None,
        period_end: datetime | None,
    ) -> dict[str, Any]:  # pragma: no cover - requires a live store
        import httpx

        url = f"https://{shop}/admin/api/{SHOPIFY_API_VERSION}/orders.json"
        params: dict[str, Any] | None = {"status": "any", "limit": 250}
        if period_start:
            params["created_at_min"] = period_start.isoformat()
        if period_end:
            params["created_at_max"] = period_end.isoformat()
        headers = {"X-Shopify-Access-Token": token}

        orders: list[dict[str, Any]] = []
        with httpx.Client(timeout=60, headers=headers) as client:
            while url:
                resp = _get_with_retry(client, url, params)
                orders.extend(resp.json().get("orders", []))
                url = _next_link(resp.headers.get("link"))
                params = None

        return {"source": "live", "shop": shop, "orders": orders}


def _get_with_retry(client, url: str, params: dict | None):  # pragma: no cover
    import httpx

    for _ in range(MAX_RETRIES):
        resp = client.get(url, params=params)
        if resp.status_code == 429:
            time.sleep(float(resp.headers.get("Retry-After", "2")))
            continue
        resp.raise_for_status()
        return resp
    raise httpx.HTTPError(f"Shopify rate limit not cleared after {MAX_RETRIES} retries")


def _refunded_amount(order: dict[str, Any]) -> float:
    refunds = order.get("refunds")
    if isinstance(refunds, list) and refunds:
        return round(
            sum(
                float(t.get("amount", 0) or 0)
                for r in refunds
                for t in r.get("transactions", [])
            ),
            2,
        )
    return float(order.get("total_refunded", 0) or 0)


def _norm_fulfillment(status: str | None) -> str:
    if status == "fulfilled":
        return "fulfilled"
    if status == "partial":
        return "partial"
    return "unfulfilled"


def _next_link(link_header: str | None) -> str | None:  # pragma: no cover
    if not link_header or 'rel="next"' not in link_header:
        return None
    for part in link_header.split(","):
        if 'rel="next"' in part:
            return part[part.find("<") + 1 : part.find(">")]
    return None


def _sample_orders() -> list[dict[str, Any]]:
    """Deterministic sample resembling a small Shopify export."""
    return [
        {"id": 1, "total_price": "2499.00", "total_discounts": "100.00",
         "total_refunded": "0", "cancelled_at": None, "fulfillment_status": "fulfilled"},
        {"id": 2, "total_price": "3999.00", "total_discounts": "0",
         "total_refunded": "0", "cancelled_at": None, "fulfillment_status": "fulfilled"},
        {"id": 3, "total_price": "1799.00", "total_discounts": "200.00",
         "total_refunded": "1799.00", "cancelled_at": None, "fulfillment_status": "fulfilled"},
        {"id": 4, "total_price": "2999.00", "total_discounts": "0",
         "total_refunded": "0", "cancelled_at": None, "fulfillment_status": "partial"},
        {"id": 5, "total_price": "4599.00", "total_discounts": "0",
         "total_refunded": "0", "cancelled_at": "2026-07-03T10:00:00Z",
         "fulfillment_status": None},
        {"id": 6, "total_price": "1299.00", "total_discounts": "50.00",
         "total_refunded": "0", "cancelled_at": None, "fulfillment_status": None},
    ]
