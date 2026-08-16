"""Register (whitelist) an email so it can sign in.

Only registered emails can log in — this is the admin allow-list. Run this once
per person you want to grant access to; it creates their account and prints a
login link you can send them.

Usage:
    python -m scripts.register_user <email> [name]

Examples:
    python -m scripts.register_user client@brand.com
    python -m scripts.register_user client@brand.com "Client Name"
"""
from __future__ import annotations

import sys

from app.auth import issue_magic_link, register_user
from app.db import SessionLocal, init_db


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m scripts.register_user <email> [name]")
        raise SystemExit(1)
    email = sys.argv[1]
    name = sys.argv[2] if len(sys.argv) > 2 else None

    init_db()
    with SessionLocal() as db:
        register_user(db, email, name)
        link = issue_magic_link(db, email)

    label = name or email.split("@")[0]
    print(f"Registered {email} — account, user '{label}', and brand '{label}' created.")
    print(f"\nLogin link (send this to them):\n{link}")


if __name__ == "__main__":
    main()
