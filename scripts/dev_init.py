"""Quick local bootstrap: create tables and print a ready-to-use login link.

Usage (with DATABASE_URL pointing at local Postgres or Neon):
    python -m scripts.dev_init you@example.com
"""
from __future__ import annotations

import sys

from app.auth import issue_magic_link
from app.db import SessionLocal, init_db


def main() -> None:
    email = sys.argv[1] if len(sys.argv) > 1 else "dev@example.com"
    init_db()
    with SessionLocal() as db:
        url = issue_magic_link(db, email)
    print("Tables created.")
    print(f"Login link for {email}:\n{url}")


if __name__ == "__main__":
    main()
