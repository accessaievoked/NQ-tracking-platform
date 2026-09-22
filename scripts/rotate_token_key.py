"""Re-encrypt every stored credential under the primary TOKEN_ENCRYPTION_KEY.

Integration credentials are Fernet-encrypted. The app decrypts with a ring of
keys (primary, TOKEN_ENCRYPTION_KEY_PREVIOUS, then the legacy key derived from
APP_SECRET_KEY) but always encrypts with the primary. So after changing the
primary key, old rows keep working — this script moves them onto the new key so
the old ones can eventually be dropped.

Nothing secret is ever printed: rows are identified by brand and provider, and
keys only by label.

Usage:
    python -m scripts.rotate_token_key --generate-key   # print a fresh Fernet key
    python -m scripts.rotate_token_key                  # dry run: report only
    python -m scripts.rotate_token_key --apply          # re-encrypt, then verify

Run it wherever the app's environment lives, e.g. in production:
    fly ssh console -a nq-tracking-platform -C "python -m scripts.rotate_token_key"
"""
from __future__ import annotations

import sys
from collections import Counter

from cryptography.fernet import Fernet

from app.config import settings
from app.db import SessionLocal
from app.models import Brand, Integration
from app.security import key_ring, reencrypt, which_key

PRIMARY = "primary"


def _check_primary_key() -> str | None:
    """Return a problem with the configured primary key, or None if usable."""
    key = settings.token_encryption_key
    if not key:
        return (
            "TOKEN_ENCRYPTION_KEY is empty, so the primary key is still the legacy "
            "one derived from APP_SECRET_KEY. Set a real key first "
            "(--generate-key makes one)."
        )
    try:
        Fernet(key.encode())
    except (ValueError, TypeError):
        return "TOKEN_ENCRYPTION_KEY is not a valid Fernet key (44 url-safe base64 chars)."
    return None


def _rows(db):
    return (
        db.query(Integration, Brand.name)
        .join(Brand, Brand.id == Integration.brand_id)
        .filter(Integration.encrypted_tokens.isnot(None))
        .order_by(Brand.name, Integration.provider)
        .all()
    )


def report(db) -> tuple[Counter, list]:
    """Print which key each stored credential is under. Returns (counts, rows)."""
    rows = _rows(db)
    counts: Counter = Counter()
    print(f"Keys in the ring: {', '.join(label for label, _ in key_ring())}\n")
    if not rows:
        print("No stored credentials — nothing to rotate.")
        return counts, rows

    width = max(len(f"{name} / {integ.provider.value}") for integ, name in rows)
    for integ, name in rows:
        label = which_key(integ.encrypted_tokens) or "UNREADABLE — no key matches"
        counts[label] += 1
        print(f"  {f'{name} / {integ.provider.value}':<{width}}  ->  {label}")

    print("\nSummary:")
    for label, n in counts.most_common():
        print(f"  {n:>3}  {label}")
    return counts, rows


def apply(db, rows) -> int:
    """Re-encrypt every row not already on the primary key. Returns exit code."""
    moved = skipped = 0
    for integ, name in rows:
        label = which_key(integ.encrypted_tokens)
        if label is None:
            skipped += 1
            continue
        if label == PRIMARY:
            continue
        integ.encrypted_tokens = reencrypt(integ.encrypted_tokens)
        moved += 1
    db.commit()

    # Verify against the primary key alone — not the ring — so a row that only
    # decrypts through a fallback counts as a failure.
    primary = Fernet(key_ring()[0][1])
    failed = []
    for integ, name in _rows(db):
        try:
            primary.decrypt(integ.encrypted_tokens.encode())
        except Exception:
            failed.append(f"{name} / {integ.provider.value}")

    print(f"\nRe-encrypted {moved} credential(s) under the primary key.")
    if skipped:
        print(
            f"Skipped {skipped} unreadable credential(s) — no configured key opens "
            "them. Add the key they were written with to "
            "TOKEN_ENCRYPTION_KEY_PREVIOUS and run again, or reconnect them."
        )
    if failed:
        print("NOT on the primary key after rotation:")
        for f in failed:
            print(f"  {f}")
        return 1
    if not skipped:
        print("Verified: every stored credential opens with the primary key alone.")
    return 1 if skipped else 0


def main(argv: list[str]) -> int:
    if "--generate-key" in argv:
        print(Fernet.generate_key().decode())
        return 0

    problem = _check_primary_key()
    if problem and "--apply" in argv:
        print(f"Refusing to rotate: {problem}")
        return 2

    with SessionLocal() as db:
        counts, rows = report(db)
        if problem:
            print(f"\nNote: {problem}")
        if "--apply" not in argv:
            pending = sum(
                n for label, n in counts.items()
                if label != PRIMARY and not label.startswith("UNREADABLE")
            )
            print(
                f"\nDry run — nothing changed. {pending} credential(s) would move to "
                "the primary key. Re-run with --apply to do it."
            )
            return 0
        return apply(db, rows)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
