"""Store GA4 credentials on a brand.

Usage:
    python -m scripts.ga4_connect <brand_id> <property_id> <token_or_keyfile>

The 3rd argument may be either:
  * a path to a service-account JSON key file (recommended — self-refreshing), or
  * a raw OAuth access token (e.g. from the OAuth Playground; expires in ~1h).
"""
from __future__ import annotations

import json
import os
import sys

from app.connectors.ga4 import GA4Connector
from app.connectors.google_auth import mint_access_token
from app.db import SessionLocal, init_db
from app.models import Brand, Integration, IntegrationProvider, IntegrationStatus
from app.security import encrypt


def main() -> None:
    if len(sys.argv) < 4:
        print("Usage: python -m scripts.ga4_connect <brand_id> <property_id> <token_or_keyfile>")
        raise SystemExit(1)
    brand_id, prop, arg = sys.argv[1], sys.argv[2], sys.argv[3]

    if os.path.isfile(arg):
        with open(arg, encoding="utf-8") as f:
            key_info = json.load(f)
        creds_to_store = {"service_account": key_info}
        token, _ = mint_access_token(key_info)  # verify the key works
        mode = f"service account ({key_info.get('client_email')})"
    else:
        token = arg
        creds_to_store = {"access_token": token}
        mode = "access token (expires ~1h)"

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
        integ.encrypted_tokens = encrypt(json.dumps(creds_to_store))
        integ.status = IntegrationStatus.connected
        integ.last_error = None
        db.commit()
    print(f"GA4 connected for brand {brand_id} (property {prop}) via {mode}.")


if __name__ == "__main__":
    main()
