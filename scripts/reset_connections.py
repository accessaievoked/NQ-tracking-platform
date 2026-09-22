"""Disconnect every integration for every brand, so they can be reconnected.

Clears exactly what the Disconnect button clears — stored credentials, config,
status and last error — for all brands at once. Brands, users, reports and
pulled data are untouched. It never decrypts anything, so it works whatever
TOKEN_ENCRYPTION_KEY is set to, including when the stored credentials can no
longer be read.

Usage:
    python -m scripts.reset_connections           # dry run: list what would be cleared
    python -m scripts.reset_connections --apply   # clear them
"""
from __future__ import annotations

import sys

from app.db import SessionLocal
from app.models import Brand, Integration, IntegrationStatus


def connected_rows(db):
    """Integrations holding credentials or not marked disconnected.

    `config` is deliberately not part of the test: it is a JSON column, so
    assigning None stores a JSON `null`, which SQL does not see as NULL — every
    disconnected row would look connected forever.
    """
    return (
        db.query(Integration, Brand.name)
        .join(Brand, Brand.id == Integration.brand_id)
        .filter(
            (Integration.encrypted_tokens.isnot(None))
            | (Integration.status != IntegrationStatus.not_connected)
        )
        .order_by(Brand.name, Integration.provider)
        .all()
    )


def main(argv: list[str]) -> int:
    apply = "--apply" in argv
    with SessionLocal() as db:
        rows = connected_rows(db)
        if not rows:
            print("No connections to clear — every integration is already disconnected.")
            return 0

        print("Connections" + (" being cleared:" if apply else " that would be cleared:"))
        for integ, brand_name in rows:
            print(f"  {brand_name} / {integ.provider.value}  ({integ.status.value})")

        if not apply:
            print(f"\nDry run — nothing changed. Re-run with --apply to clear {len(rows)}.")
            return 0

        for integ, _ in rows:
            integ.encrypted_tokens = None
            integ.config = None
            integ.status = IntegrationStatus.not_connected
            integ.last_error = None
        db.commit()

        left = connected_rows(db)
        if left:
            print(f"\n{len(left)} connection(s) were not cleared — check the database.")
            return 1
        print(f"\nCleared {len(rows)} connection(s). Reconnect them from each brand's page.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
