"""Connect a brand's Microsoft Clarity project (stores an encrypted API token).

Get the token in Clarity -> Settings -> Data Export -> Generate new API token.

Usage:
    python -m scripts.clarity_connect <brand_id> <api_token>
"""
from __future__ import annotations

import json
import sys

from app.connectors.clarity import ClarityConnector
from app.db import SessionLocal
from app.models import Brand, Integration, IntegrationProvider, IntegrationStatus
from app.security import encrypt


def main() -> None:
    if len(sys.argv) < 3:
        print("Usage: python -m scripts.clarity_connect <brand_id> <api_token>")
        raise SystemExit(1)
    brand_id, token = sys.argv[1], sys.argv[2]

    # Validate the token against the live API before storing it.
    ClarityConnector(credentials={"token": token}).verify_connection()

    with SessionLocal() as db:
        brand = db.get(Brand, brand_id)
        if not brand:
            print("Brand not found:", brand_id)
            raise SystemExit(1)
        integ = (
            db.query(Integration)
            .filter(Integration.brand_id == brand_id,
                    Integration.provider == IntegrationProvider.clarity)
            .first()
        )
        if not integ:
            integ = Integration(brand_id=brand_id, provider=IntegrationProvider.clarity)
            db.add(integ)
        integ.encrypted_tokens = encrypt(json.dumps({"token": token}))
        integ.status = IntegrationStatus.connected
        db.commit()
    print(f"Clarity connected for brand {brand_id}.")


if __name__ == "__main__":
    main()
