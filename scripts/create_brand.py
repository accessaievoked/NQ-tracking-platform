"""Create an additional brand inside an existing account (client tenant).

Every account is provisioned with one brand at registration and there is no
create-brand UI, so this is the admin path for onboarding a second (or third)
brand into the same tenant.

Identify the owning tenant by any user's email, or by client_id directly.

Usage:
    python -m scripts.create_brand <email_or_client_id> <brand_name> [website] [industry]

Examples:
    python -m scripts.create_brand you@agency.com "House of Vaulte"
    python -m scripts.create_brand you@agency.com "House of Vaulte" houseofvaulte.com Fashion
"""
from __future__ import annotations

import sys

from app.db import SessionLocal
from app.models import Brand, User


def main() -> None:
    args = sys.argv[1:]
    if len(args) < 2:
        print("Usage: python -m scripts.create_brand <email_or_client_id> <brand_name> "
              "[website] [industry]")
        raise SystemExit(1)

    identifier = args[0].strip()
    name = args[1].strip()
    website = args[2] if len(args) > 2 else None
    industry = args[3] if len(args) > 3 else None

    with SessionLocal() as db:
        user = db.query(User).filter(User.email == identifier.lower()).first()
        client_id = user.client_id if user else identifier

        owner_brands = db.query(Brand).filter(Brand.client_id == client_id).all()
        if not owner_brands and not user:
            print(f"No user or tenant found matching {identifier!r}.")
            print("Known users:")
            for u in db.query(User).all():
                print(f"  {u.email}  client_id={u.client_id}")
            raise SystemExit(1)

        # Names are how add_user and the brand switcher find a brand, so a
        # duplicate inside one tenant would be genuinely ambiguous.
        clash = next((b for b in owner_brands if b.name.lower() == name.lower()), None)
        if clash:
            print(f"Brand {name!r} already exists in this tenant (id={clash.id}). Nothing to do.")
            raise SystemExit(0)

        brand = Brand(client_id=client_id, name=name, website=website, industry=industry)
        db.add(brand)
        db.commit()
        db.refresh(brand)

    print(f"Created brand {brand.name!r}")
    print(f"  id        = {brand.id}")
    print(f"  client_id = {brand.client_id}")
    print(f"\nEveryone in this tenant can now see it. To give it its own login:")
    print(f'  python -m scripts.add_user <email> "{brand.name}" "{brand.name}"')


if __name__ == "__main__":
    main()
