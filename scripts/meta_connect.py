"""Store a Meta Ads token on a brand (for testing real ROAS).

Usage:
    python -m scripts.meta_connect <brand_id> <ad_account_id> <access_token>

Validates the token against the ad account, then stores it (encrypted) as the
brand's meta_ads integration. After this, `python -m scripts.report <brand_id>`
will use real Meta spend and show real ROAS.
"""
from __future__ import annotations

import json
import sys

from app.connectors.meta_ads import MetaAdsConnector
from app.db import SessionLocal, init_db
from app.models import Brand, Integration, IntegrationProvider, IntegrationStatus
from app.security import encrypt


def main() -> None:
    if len(sys.argv) < 4:
        print("Usage: python -m scripts.meta_connect <brand_id> <ad_account_id> <access_token>")
        raise SystemExit(1)
    brand_id, account, token = sys.argv[1], sys.argv[2], sys.argv[3]

    init_db()
    with SessionLocal() as db:
        brand = db.get(Brand, brand_id)
        if not brand:
            print("Brand not found:", brand_id)
            raise SystemExit(1)

        conn = MetaAdsConnector(credentials={"access_token": token}, config={"ad_account_id": account})
        try:
            info = conn.verify_connection()
            print(f"Verified Meta account: {info.get('name')} ({info.get('currency')})")
        except Exception as exc:
            print("Meta verification failed:", exc)
            raise SystemExit(1)

        integ = (
            db.query(Integration)
            .filter(
                Integration.brand_id == brand.id,
                Integration.provider == IntegrationProvider.meta_ads,
            )
            .first()
        )
        if integ is None:
            integ = Integration(brand_id=brand.id, provider=IntegrationProvider.meta_ads)
            db.add(integ)
        integ.config = {"ad_account_id": account, "account_name": info.get("name"),
                        "currency": info.get("currency")}
        integ.encrypted_tokens = encrypt(json.dumps({"access_token": token}))
        integ.status = IntegrationStatus.connected
        integ.last_error = None
        db.commit()
    print(f"Meta Ads connected for brand {brand_id}. Now run: python -m scripts.report {brand_id}")


if __name__ == "__main__":
    main()
