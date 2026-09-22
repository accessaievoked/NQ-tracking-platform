"""Work out why a Shopify callback failed HMAC verification.

Paste the full address from the browser tab that showed
{"detail":"HMAC verification failed"}. The script reads which brand the
request was for, which Shopify app that brand uses, and checks Shopify's
signature against every app secret it knows — the brand's registered app, the
default app from SHOPIFY_API_KEY/SECRET, and every other registered app — to
say which one (if any) actually signed it. No secret is printed.

Usage:
    python -m scripts.check_shopify_callback "https://nq-tracking-platform.fly.dev/api/integrations/shopify/callback?code=...&hmac=...&shop=...&state=..."

The authorization code in that address was never exchanged, but it expires in
minutes and is single-use; you will reconnect afterwards anyway.
"""
from __future__ import annotations

import sys
from urllib.parse import parse_qsl, urlparse

from itsdangerous import URLSafeTimedSerializer

from app.config import settings
from app.connectors.shopify_oauth import STATE_SALT, ShopifyAppCreds, default_app, verify_hmac
from app.db import SessionLocal
from app.models import Brand, ShopifyApp
from app.security import decrypt


def _brand_id_from_state(state: str) -> tuple[str | None, bool]:
    """(brand_id, signature_ok). Reads the payload even if our signature fails."""
    s = URLSafeTimedSerializer(settings.app_secret_key, salt=STATE_SALT)
    ok, payload = s.loads_unsafe(state)
    return (payload or {}).get("brand_id") if isinstance(payload, dict) else None, bool(ok)


def diagnose(url: str) -> int:
    params = dict(parse_qsl(urlparse(url).query, keep_blank_values=True))
    missing = [k for k in ("hmac", "shop", "state") if k not in params]
    if missing:
        print(f"That address is missing {', '.join(missing)} — copy the whole URL "
              "from the browser bar of the error page.")
        return 2

    print(f"Store:  {params['shop']}")
    brand_id, state_ok = _brand_id_from_state(params["state"])

    with SessionLocal() as db:
        brand = db.get(Brand, brand_id) if brand_id else None
        if not brand:
            print("Brand:  could not tell which brand this was for.")
        else:
            uses = brand.shopify_app.name if brand.shopify_app else "the default app"
            print(f"Brand:  {brand.name}  (uses {uses})")
        if not state_ok:
            print("        Note: this machine's APP_SECRET_KEY differs from production's, "
                  "so the state check above was skipped. That is not the cause.")

        candidates: list[tuple[str, ShopifyAppCreds]] = []
        d = default_app()
        if d.client_id and d.client_secret:
            candidates.append((f"default app (SHOPIFY_API_KEY {d.client_id[:8]}…)", d))
        for a in db.query(ShopifyApp).order_by(ShopifyApp.name).all():
            try:
                secret = decrypt(a.encrypted_client_secret)
            except ValueError:
                print(f"        Cannot decrypt the secret stored for {a.name} — "
                      "TOKEN_ENCRYPTION_KEY here differs from the one it was saved with.")
                continue
            candidates.append((f"{a.name} ({a.client_id[:8]}…)", ShopifyAppCreds(a.client_id, secret)))

    expected = None
    if brand is not None:
        expected = (f"{brand.shopify_app.name} ({brand.shopify_app.client_id[:8]}…)"
                    if brand.shopify_app else next((n for n, _ in candidates if n.startswith("default")), None))

    print("\nWhich secret signed this request:")
    matched = None
    for name, app in candidates:
        ok = verify_hmac(params, app)
        print(f"  {'MATCH' if ok else '  -  '}  {name}")
        if ok:
            matched = name

    print()
    if matched and matched == expected:
        print("The signature matches the brand's app, so it would pass now. If production "
              "still fails, production is on older code or a different secret: run fly deploy.")
    elif matched:
        print(f"Shopify signed with {matched}, but the brand expects {expected}.\n"
              "The store was sent to the wrong app, or the brand is linked to the wrong app. "
              "Check with: python -m scripts.register_shopify_app --list")
    else:
        print("No known secret matches. The client secret saved for this brand's app is not "
              "the one Shopify is using. Common causes: the client ID was pasted instead of "
              "the secret, the secret was rotated in the Dev Dashboard, or it came from a "
              "different app. Re-register it (you will be asked for the secret again):\n"
              "  python -m scripts.register_shopify_app --brand \"<brand>\" --name <app name> "
              "--client-id <client id>\n"
              "If the brand uses the default app, update SHOPIFY_API_SECRET instead: "
              "fly secrets set SHOPIFY_API_SECRET=... -a nq-tracking-platform")
    return 0 if matched == expected and matched else 1


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(diagnose(sys.argv[1]))
