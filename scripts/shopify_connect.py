"""Print a ready-to-open Shopify install URL for a brand (OAuth auth-code flow).

Usage:
    python -m scripts.shopify_connect "Brand Name" your-store.myshopify.com

Creates the brand if needed, prints the signed install URL and the brand id.
Open the URL, click Install; Shopify redirects to your running backend's
callback (via the tunnel) which stores the offline token. Then run:
    python -m scripts.report <brand_id>
"""
from __future__ import annotations

import sys
import uuid

from app.connectors.shopify_oauth import STATE_SALT, build_install_url, is_valid_shop
from app.db import SessionLocal, init_db
from app.models import Brand, Client
from app.security import make_token


def main() -> None:
    name = sys.argv[1] if len(sys.argv) > 1 else "Test Brand"
    shop = sys.argv[2] if len(sys.argv) > 2 else ""
    if not is_valid_shop(shop):
        print('Usage: python -m scripts.shopify_connect "Brand Name" your-store.myshopify.com')
        raise SystemExit(1)

    init_db()
    with SessionLocal() as db:
        brand = db.query(Brand).filter(Brand.name == name).first()
        if not brand:
            client = db.query(Client).first() or Client(name="dev")
            if client.id is None:
                db.add(client)
                db.flush()
            brand = Brand(client_id=client.id, name=name)
            db.add(brand)
            db.commit()
            db.refresh(brand)
        state = make_token(
            {"brand_id": brand.id, "shop": shop, "nonce": uuid.uuid4().hex},
            salt=STATE_SALT,
        )
        url = build_install_url(shop, state)
        brand_id = brand.id

    print(f"Brand id: {brand_id}")
    print("\nOpen this URL in your browser and click Install:\n")
    print(url)
    print(f"\nAfter approving, run:  python -m scripts.report {brand_id}")


if __name__ == "__main__":
    main()
