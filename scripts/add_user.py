"""Add a new login (User) to an EXISTING brand's client, without creating a
new client/brand pair. Use this instead of register_user.py when you want a
fresh login for a brand that already exists (keeps its integrations/reports).

Identify the brand by its client_id (no spaces/quoting headaches over SSH)
or, if you'd rather, by its name.

Usage:
    python -m scripts.add_user <email> <client_id_or_brand_name> [display_name]

Example:
    python -m scripts.add_user newlogin@brand.com 9464ef60-b8ba-4d64-b838-f83b6d21327a Covera
"""
from __future__ import annotations

import sys

from app.auth import issue_magic_link
from app.db import SessionLocal
from app.models import Brand, User


def main() -> None:
    args = sys.argv[1:]
    if len(args) < 2:
        print("Usage: python -m scripts.add_user <email> <client_id_or_brand_name> [display_name]")
        raise SystemExit(1)

    email = args[0].strip().lower()
    identifier = args[1]
    display_name = args[2] if len(args) > 2 else email.split("@")[0]

    with SessionLocal() as db:
        brand = (
            db.query(Brand)
            .filter((Brand.client_id == identifier) | (Brand.name.ilike(identifier)))
            .first()
        )
        if brand is None:
            print(f"No brand found matching {identifier!r} (tried client_id and name).")
            raise SystemExit(1)

        existing = db.query(User).filter(User.email == email).first()
        if existing is not None:
            print(f"A user with email {email!r} already exists (client_id={existing.client_id}).")
            raise SystemExit(1)

        user = User(client_id=brand.client_id, email=email, name=display_name)
        db.add(user)
        db.commit()
        db.refresh(user)
        link = issue_magic_link(db, email)

    print(f"Added {email!r} as a new login for brand {brand.name!r} (client_id={brand.client_id}).")
    print(f"\nLogin link (send this to them):\n{link}")


if __name__ == "__main__":
    main()
