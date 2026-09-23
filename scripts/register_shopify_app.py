"""Register a Shopify app and link it to a brand.

Custom-distribution Shopify apps install on one store only, so each client
store needs its own app from the Dev Dashboard. This records that app's client
ID and secret (encrypted) and points the brand at it; the brand's "Connect"
button on the Shopify tile then uses it. Brands with no app use the default
app from SHOPIFY_API_KEY / SHOPIFY_API_SECRET.

The client secret is never taken on the command line (it would sit in your
shell history). Choose whichever of these suits you:

  * default          — a hidden prompt (nothing appears as you paste)
  * --show-secret    — a visible prompt, so you can see what you pasted
  * --secret-file F  — read it from a file you paste it into, then delete F
  * SHOPIFY_APP_SECRET in the environment

Whatever you use, the script checks the secret looks like a Shopify one (32
hex characters) and refuses the client ID by mistake.

Usage:
    python -m scripts.register_shopify_app --list
    python -m scripts.register_shopify_app --brand "Indethnic" --name NQ-tracker-Indethnic --client-id <id>
    python -m scripts.register_shopify_app --brand "Indethnic" --name NQ-tracker-Indethnic   # link an app already registered
    python -m scripts.register_shopify_app --brand "Indethnic" --use-default                  # back to the default app

Run it from the repo on your machine: your .env points at the production
database and must hold the same TOKEN_ENCRYPTION_KEY as production.
"""
from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

from app.db import SessionLocal
from app.models import Brand, Integration, IntegrationProvider, IntegrationStatus, ShopifyApp
from app.security import encrypt


SECRET_LENGTH = 32


def read_secret(args) -> str | None:
    """The client secret, from --secret-file, the environment, or a prompt."""
    if args.secret_file:
        try:
            secret = Path(args.secret_file).read_text(encoding="utf-8")
        except OSError as exc:
            print(f"Could not read {args.secret_file}: {exc}")
            return None
    elif os.environ.get("SHOPIFY_APP_SECRET"):
        secret = os.environ["SHOPIFY_APP_SECRET"]
    elif args.show_secret:
        secret = input("Client secret (visible): ")
    else:
        secret = getpass.getpass("Client secret (hidden — paste and press Enter): ")

    # Quotes and stray whitespace survive a paste surprisingly often.
    secret = secret.strip().strip('"').strip("'").strip()
    if not secret:
        print("No client secret given — nothing saved.")
        return None
    return secret


def secret_problem(secret: str, client_id: str) -> str | None:
    """Catch the mistakes that only surface later as 'HMAC verification failed'."""
    if secret == client_id:
        return ("That is the client ID, not the client secret. The secret is the "
                "separate value on the same page, usually behind a Reveal button.")
    if any(c.isspace() for c in secret):
        return "That secret contains a space — it looks like something else was copied."
    looks_right = len(secret) == SECRET_LENGTH and all(
        c in "0123456789abcdefABCDEF" for c in secret
    )
    if not looks_right:
        return (f"That does not look like a Shopify client secret: expected "
                f"{SECRET_LENGTH} characters of 0-9 and a-f, got {len(secret)}. "
                "Copy it again from the Dev Dashboard (app -> Settings), or use "
                "--secret-file to paste it into a file first.")
    return None


def find_brand(db, ref: str) -> Brand | None:
    """A brand by id, or by case-insensitive exact name. Ambiguous names exit."""
    brand = db.get(Brand, ref)
    if brand:
        return brand
    matches = [b for b in db.query(Brand).all() if b.name.strip().lower() == ref.strip().lower()]
    if len(matches) > 1:
        print(f'More than one brand is called "{ref}". Pass the id instead:')
        for b in matches:
            print(f"  {b.id}  {b.name}")
        raise SystemExit(2)
    return matches[0] if matches else None


def list_all(db) -> None:
    apps = db.query(ShopifyApp).order_by(ShopifyApp.name).all()
    print("Shopify apps:")
    if not apps:
        print("  (none registered — every brand uses the default app)")
    for a in apps:
        print(f"  {a.name}  client_id={a.client_id}")

    print("\nBrands:")
    for b in db.query(Brand).order_by(Brand.name).all():
        app = b.shopify_app.name if b.shopify_app else "default app"
        print(f"  {b.name}  ->  {app}  ({b.id})")


def _connected_shopify(db, brand: Brand) -> Integration | None:
    return (
        db.query(Integration)
        .filter(
            Integration.brand_id == brand.id,
            Integration.provider == IntegrationProvider.shopify,
            Integration.status == IntegrationStatus.connected,
        )
        .first()
    )


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m scripts.register_shopify_app")
    parser.add_argument("--list", action="store_true", help="show apps and which brand uses which")
    parser.add_argument("--brand", help="brand name or id")
    parser.add_argument("--name", help="a label for the app, e.g. NQ-tracker-Indethnic")
    parser.add_argument("--client-id", help="the app's Client ID from the Dev Dashboard")
    parser.add_argument("--use-default", action="store_true", help="point the brand back at the default app")
    parser.add_argument("--show-secret", action="store_true",
                        help="type/paste the secret visibly instead of hidden")
    parser.add_argument("--secret-file", help="read the secret from this file instead of prompting")
    args = parser.parse_args(argv)

    with SessionLocal() as db:
        if args.list:
            list_all(db)
            return 0

        if not args.brand:
            parser.error("--brand is required (or use --list)")
        brand = find_brand(db, args.brand)
        if not brand:
            print(f'No brand matches "{args.brand}". Existing brands:')
            for b in db.query(Brand).order_by(Brand.name).all():
                print(f"  {b.name}  ({b.id})")
            return 2

        if args.use_default:
            brand.shopify_app_id = None
            db.commit()
            print(f"{brand.name} now uses the default Shopify app.")
            return 0

        if not args.name:
            parser.error("--name is required")

        app = db.query(ShopifyApp).filter(ShopifyApp.name == args.name).first()
        if args.client_id:
            clash = db.query(ShopifyApp).filter(ShopifyApp.client_id == args.client_id).first()
            if clash and (app is None or clash.id != app.id):
                print(f'That client ID is already registered as "{clash.name}". '
                      f"Link it with: --brand \"{brand.name}\" --name \"{clash.name}\"")
                return 2

            secret = read_secret(args)
            if secret is None:
                return 2
            problem = secret_problem(secret, args.client_id.strip())
            if problem:
                print(problem)
                return 2

            if app is None:
                app = ShopifyApp(name=args.name, client_id=args.client_id.strip(),
                                 encrypted_client_secret=encrypt(secret))
                db.add(app)
                action = "Registered"
            else:
                app.client_id = args.client_id.strip()
                app.encrypted_client_secret = encrypt(secret)
                action = "Updated"
            db.flush()
        elif app is None:
            print(f'No app called "{args.name}" is registered yet. Add --client-id to register it.')
            return 2
        else:
            action = "Linked existing"

        previous = brand.shopify_app_id
        brand.shopify_app_id = app.id
        db.commit()

        print(f'{action} app "{app.name}" (client_id={app.client_id}) for brand {brand.name}.')
        if args.client_id:
            print(f"Saved a {SECRET_LENGTH}-character client secret. If the connection still "
                  "fails, run scripts.check_shopify_callback on the failing URL.")
        if previous != app.id and _connected_shopify(db, brand):
            print("Note: this brand's store was connected through a different app. "
                  "Disconnect and reconnect Shopify on its Brand Library page.")
        print("Next: open the brand in NQ, click Connect on the Shopify tile, and "
              "enter the store's .myshopify.com domain.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
