"""Delete a user's login access, or their entire account.

By default this only removes the User row (revokes that email's ability to
log in) and leaves their Client/Brand and any connected data untouched.

Pass --full to instead delete the whole account: the Client, every Brand
under it, and (via cascading foreign keys) their Integrations, RawPulls,
Metrics, and Reports. This is irreversible.

Usage:
    python -m scripts.delete_user <email>            # revoke login only
    python -m scripts.delete_user <email> --full      # wipe entire account
"""
from __future__ import annotations

import sys

from app.db import SessionLocal
from app.models import Client, User


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    full = "--full" in sys.argv[1:]

    if len(args) < 1:
        print("Usage: python -m scripts.delete_user <email> [--full]")
        raise SystemExit(1)

    email = args[0].strip().lower()

    with SessionLocal() as db:
        user = db.query(User).filter(User.email == email).first()
        if user is None:
            print(f"No user found with email {email!r}. Nothing to do.")
            return

        client = db.get(Client, user.client_id)
        client_name = client.name if client else "(unknown)"

        if full:
            other_users = (
                db.query(User)
                .filter(User.client_id == user.client_id, User.id != user.id)
                .count()
            )
            print(
                f"Deleting FULL account for {email!r}: client {client_name!r} "
                f"(id={user.client_id}), including all its brands, integrations, "
                f"and reports."
            )
            if other_users:
                print(
                    f"WARNING: {other_users} other user(s) share this client and "
                    "will also lose access."
                )
            if client is not None:
                db.delete(client)  # cascades to users, brands, integrations, reports
            else:
                db.delete(user)
            db.commit()
            print(f"Deleted account {client_name!r} and all associated data.")
        else:
            print(f"Revoking login for {email!r} (client {client_name!r} is kept as-is).")
            db.delete(user)
            db.commit()
            print(f"Deleted user {email!r}. Their brand/data is untouched.")


if __name__ == "__main__":
    main()
