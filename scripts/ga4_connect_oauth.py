"""Store keyless GA4 OAuth credentials (refresh token) on a brand.

Usage:
    python -m scripts.ga4_connect_oauth <brand_id> <property_id> \
        <client_id> <client_secret> <refresh_token>

The backend then refreshes access tokens forever with no downloadable key.
"""
from __future__ import annotations

import json
import sys

from app.connectors.ga4 import GA4Connector
from app.connectors.google_auth import refresh_access_token
from app.db import SessionLocal, init_db
from app.models import Brand, Integration, IntegrationProvider, IntegrationStatus
from app.security import encrypt


def main() -> None:
    if len(sys.argv) < 6:
        print("Usage: python -m scripts.ga4_connect_oauth <brand_id> <property_id> "
              "<client_id> <client_secret> <refresh_token>")
        raise SystemExit(1)
    brand_id, prop, client_id, client_secret, refresh_token = sys.argv[1:6]

    # Verify: refresh once, then confirm property access.
    token, _ = refresh_access_token(client_id, client_secret, refresh_token)

    init_db()
    with SessionLocal() as db:
        brand = db.get(Brand, brand_id)
        if not brand:
            print("Brand not found:", brand_id)
            raise SystemExit(1)
        try:
            GA4Connector(
                credentials={"access_token": token}, config={"property_id": prop}
            ).verify_connection()
        except Exception as exc:
            print("GA4 verification failed:", exc)
            raise SystemExit(1)

        integ = (
            db.query(Integration)
            .filter(Integration.brand_id == brand.id, Integration.provider == IntegrationProvider.ga4)
            .first()
        )
        if integ is None:
            integ = Integration(brand_id=brand.id, provider=IntegrationProvider.ga4)
            db.add(integ)
        integ.config = {"property_id": prop}
        integ.encrypted_tokens = encrypt(json.dumps({
            "oauth": {
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
            }
        }))
        integ.status = IntegrationStatus.connected
        integ.last_error = None
        db.commit()
    print(f"GA4 connected for brand {brand_id} (property {prop}) via keyless OAuth refresh token.")


if __name__ == "__main__":
    main()
