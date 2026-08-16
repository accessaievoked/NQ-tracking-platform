"""Post simulated storefront traffic at the Live Journey ingest endpoint.

Lets you demo (and load-check) the live graph without touching a real store.

    python -m scripts.mock_live_traffic --brand <BRAND_ID> --token <SESSION_TOKEN>
    python -m scripts.mock_live_traffic --url http://localhost:8000/api/live/nqk_xxx/events

The first form looks the ingest URL up through the API, so it works against a
deployed instance too:

    python -m scripts.mock_live_traffic --brand <ID> --token <TOKEN> \
        --base https://nq-tracking-platform.fly.dev
"""
from __future__ import annotations

import argparse
import random
import sys
import threading
import time

import httpx

# Channel mix roughly mirrors a paid-social-led DTC store.
CHANNELS = [
    ("instagram", 0.34, "https://l.instagram.com/"),
    ("facebook", 0.22, "https://l.facebook.com/"),
    ("google", 0.20, "https://www.google.com/"),
    ("direct", 0.18, ""),
    ("other", 0.06, "https://t.co/"),
]

# (event name, path, probability of continuing past this step)
FUNNEL = [
    ("page_viewed", "/", 0.72),
    ("collection_viewed", "/collections/co-ords", 0.68),
    ("product_viewed", "/products/{p}", 0.42),
    ("product_added_to_cart", "/cart", 0.55),
    ("checkout_started", "/checkouts/c/abc", 0.62),
    ("payment_info_submitted", "/checkouts/c/abc/payment", 0.78),
    ("checkout_completed", "/checkouts/c/abc/thank-you", 0.0),
]

PRODUCTS = [
    "floral-rayon-co-ord",
    "navy-bohemian-bird-set",
    "black-chanderi-silk-co-ord",
    "elegant-pink-embroidered-v-neck",
    "black-rayon-embroidered-dress",
]

_sent = 0
_visitors = 0
_lock = threading.Lock()


def _pick_channel():
    r = random.random()
    for name, weight, referrer in CHANNELS:
        r -= weight
        if r <= 0:
            return name, referrer
    return CHANNELS[-1][0], CHANNELS[-1][2]


def _post(client: httpx.Client, url: str, payload: dict) -> None:
    global _sent
    try:
        # text/plain matches the real pixel: a CORS-simple content type, so the
        # browser never fires a preflight.
        client.post(url, content=payload_json(payload), headers={"Content-Type": "text/plain"})
        with _lock:
            _sent += 1
    except httpx.HTTPError as exc:
        print(f"\n[mock] collector unreachable: {exc}", file=sys.stderr)


def payload_json(payload: dict) -> str:
    import json

    return json.dumps(payload)


def simulate_visitor(url: str) -> None:
    global _visitors
    with _lock:
        _visitors += 1

    channel, referrer = _pick_channel()
    client_id = f"c_{random.getrandbits(40):010x}"
    session_id = f"s_{random.getrandbits(40):010x}"
    product = random.choice(PRODUCTS)
    # ~1 in 9 shoppers is a returning, logged-in customer.
    customer_id = f"cust_{random.randint(1, 4000)}" if random.random() < 0.11 else None

    with httpx.Client(timeout=5.0) as client:
        for name, path, keep in FUNNEL:
            resolved = path.format(p=product)
            _post(client, url, {
                "client_id": client_id,
                "session_id": session_id,
                "customer_id": customer_id,
                "name": name,
                "path": resolved,
                "referrer": referrer,
                "ts": int(time.time() * 1000),
            })
            referrer = "https://claura.example.com" + resolved

            # Some shoppers bounce back to the collection to compare first.
            if name == "product_viewed" and random.random() < 0.3:
                time.sleep(random.uniform(1.2, 4.0))
                _post(client, url, {
                    "client_id": client_id, "session_id": session_id,
                    "customer_id": customer_id, "name": "collection_viewed",
                    "path": "/collections/co-ords", "referrer": referrer,
                    "ts": int(time.time() * 1000),
                })
                time.sleep(random.uniform(1.5, 4.0))
                _post(client, url, {
                    "client_id": client_id, "session_id": session_id,
                    "customer_id": customer_id, "name": "product_viewed",
                    "path": "/products/" + random.choice(PRODUCTS), "referrer": referrer,
                    "ts": int(time.time() * 1000),
                })

            if random.random() > keep:
                break
            time.sleep(random.uniform(2.0, 11.0))  # dwell time on the page


def resolve_url(base: str, brand_id: str, token: str) -> str:
    r = httpx.get(
        f"{base.rstrip('/')}/api/brands/{brand_id}/live/pixel",
        headers={"Authorization": f"Bearer {token}"},
        timeout=15.0,
    )
    r.raise_for_status()
    return r.json()["ingest_url"]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--url", help="Full ingest URL (skips the API lookup)")
    ap.add_argument("--brand", help="Brand id, used with --token to look the URL up")
    ap.add_argument("--token", help="Session bearer token")
    ap.add_argument("--base", default="http://localhost:8000", help="API base URL")
    ap.add_argument("--rate", type=int, default=40, help="Visitors per minute")
    args = ap.parse_args()

    url = args.url
    if not url:
        if not (args.brand and args.token):
            ap.error("pass --url, or both --brand and --token")
        url = resolve_url(args.base, args.brand, args.token)

    print(f"[mock] posting to {url} at ~{args.rate} visitors/min — ctrl-C to stop")
    interval = 60.0 / max(1, args.rate)

    try:
        while True:
            threading.Thread(target=simulate_visitor, args=(url,), daemon=True).start()
            time.sleep(interval)
            with _lock:
                print(f"\r[mock] visitors: {_visitors}  events sent: {_sent}   ", end="")
    except KeyboardInterrupt:
        print("\n[mock] stopped")


if __name__ == "__main__":
    main()
