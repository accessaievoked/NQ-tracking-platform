"""Attach an existing brand to a user's account (dev convenience).

A fresh magic-link login creates a brand-new account, so a brand created earlier
under a different account (e.g. Three Sixty Leather, with Shopify connected)
won't show up. This reassigns that brand to the account of <email> — keeping the
brand's integrations intact — and prints a login link.

Usage:
    python -m scripts.dev_link_brand <email> [brand_id_or_name]

Example:
    python -m scripts.dev_link_brand you@example.com
    python -m scripts.dev_link_brand you@example.com "Three Sixty Leather"
"""
from __future__ import annotations

import sys

from app.auth import issue_magic_link, register_user
from app.db import SessionLocal
from app.models import Brand, User


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m scripts.dev_link_brand <email> [brand_id_or_name]")
        raise SystemExit(1)
    email = sys.argv[1]
    target = sys.argv[2] if len(sys.argv) > 2 else "Three Sixty Leather"

    with SessionLocal() as db:
        register_user(db, email)  # registers the user + client if new
        link = issue_magic_link(db, email)
        user = db.query(User).filter(User.email == email).first()

        brand = db.get(Brand, target) or db.query(Brand).filter(Brand.name == target).first()
        if brand is None:
            print(f"Brand not found by id or name: {target!r}")
            print("Existing brands:")
            for b in db.query(Brand).all():
                print(f"  {b.id}  {b.name}")
            raise SystemExit(1)

        brand.client_id = user.client_id
        db.commit()
        print(f"Attached '{brand.name}' ({brand.id}) to {email}.")
        print(f"\nLog in to the web app with {email} — this link also works:\n{link}")


if __name__ == "__main__":
    main()
