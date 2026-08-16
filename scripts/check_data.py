"""One-off: dump brands and users to verify what's in the connected database.

Usage:
    python -m scripts.check_data
"""
from __future__ import annotations

from app.db import SessionLocal
from app.models import Brand, User


def main() -> None:
    with SessionLocal() as db:
        brands = db.query(Brand).all()
        users = db.query(User).all()
        print(f"BRANDS ({len(brands)}):")
        for b in brands:
            print(f"  id={b.id} name={b.name!r} client_id={b.client_id}")
        print(f"USERS ({len(users)}):")
        for u in users:
            print(f"  id={u.id} email={u.email!r} client_id={u.client_id}")


if __name__ == "__main__":
    main()
