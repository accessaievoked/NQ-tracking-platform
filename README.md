# NQ Tracking Platform — Backend

Backend for an in-house analytics tool: brand workspaces that connect a client's
ad + store data, and AI-generated reports built on top of it. This repo is the
**API + report engine**. The flagship report is **Money Flow**, which reconciles
ad spend against real Shopify order outcomes (cancellations, returns, discounts,
GST) to expose the gap between platform-reported ROAS and real ROAS.

## Design principle

**The LLM never does arithmetic.** Every number is computed deterministically in
`app/compute/`, unit-tested, and only then handed to the narrative generator,
which is told not to alter any figure. This keeps reports accurate, cheap, and
reproducible.

## Stack

- FastAPI + SQLAlchemy 2.0 + Alembic
- Postgres (Neon in staging/prod; local Postgres or SQLite for dev/tests)
- Magic-link auth (per-client sessions, tenancy-isolated)
- Anthropic Claude for narratives (optional locally — falls back to a template)

## Layout

```
app/
  main.py            FastAPI app + routers
  config.py          settings from .env
  db.py              engine/session/Base + init_db()
  models.py          ORM: clients, users, brands, integrations, raw_pulls, metrics, reports
  schemas.py         Pydantic request/response
  security.py        token encryption + signed magic-link/session tokens
  auth.py            magic-link issue/verify
  deps.py            auth + brand-ownership (tenancy) dependencies
  api/               auth, brands, integrations, reports routers
  connectors/        base + shopify (sample data offline; live Admin API sketched)
  compute/           money_flow.py — deterministic metrics
  reports/           generator.py — metrics -> narrative (Claude or fallback)
  services.py        pull -> compute -> narrate -> persist pipeline
migrations/          Alembic (autogenerate-ready)
scripts/dev_init.py  create tables + print a login link
tests/               money-flow unit tests + API smoke/tenancy tests
```

## Quick start (local)

```bash
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                  # defaults work out of the box

# 1) Start Postgres (or point DATABASE_URL at a Neon dev branch)
docker compose up -d

# 2) Create tables and get a login link
python -m scripts.dev_init you@example.com

# 3) Run the API
uvicorn app.main:app --reload
# open http://localhost:8000/docs
```

No `ANTHROPIC_API_KEY` is needed to develop: report narratives fall back to a
deterministic template. Set the key in `.env` to switch on Claude-written prose.

## Try the flow (Swagger or curl)

1. `POST /api/auth/magic-link` `{ "email": "you@example.com" }` → returns a
   `dev_login_url`.
2. Open that URL (`GET /api/auth/verify`) → returns a session `token`.
3. Send `Authorization: Bearer <token>` on the calls below.
4. `POST /api/brands` `{ "name": "Covera" }`.
5. `POST /api/brands/{id}/reports` `{ "type": "money_flow",
   "period_start": "2026-07-01T00:00:00Z", "period_end": "2026-07-06T00:00:00Z" }`.
6. `GET /api/brands/{id}/reports/{report_id}` → computed metrics + narrative.

With no Shopify credentials connected, step 5 runs on built-in sample data so the
whole pipeline works end-to-end offline.

## Tests

```bash
pytest
```

Tests use in-memory SQLite (no Postgres needed). They pin the exact Money Flow
figures and cover auth + tenancy isolation.

> Note: running `pytest` directly inside a OneDrive-synced folder can trip a temp
> cleanup bug. If you hit it, run from a normal local checkout.

## Migrations (when you change models)

```bash
alembic revision --autogenerate -m "message"
alembic upgrade head
```

## What's stubbed / next

- **Connectors:** Shopify has the real Admin API call sketched (`_fetch_live`);
  Meta Ads, Google Ads, GA4, Search Console still to add. Ad spend in the Money
  Flow pipeline currently uses a placeholder (`services._sample_ad_spend`).
- **Report types:** only `money_flow` is implemented; audit / P&L / performance
  follow the same compute→narrate pattern.
- **OAuth:** `integrations/connect` stores credentials directly for dev; real
  OAuth start/callback per provider goes here.
- **Auth hardening:** magic-link auto-provisions users; add an allow-list before
  go-live. Wire an email sender to actually deliver links.
- **Deploy:** Fly.io app + worker (scheduled reports) — not in this repo yet.
```

## Connecting a real merchant store (Shopify OAuth)

Client stores aren't in your Dev Dashboard org, so the client-credentials grant
is rejected (`shop_not_permitted`). Use the standard OAuth authorization-code
flow instead. It needs a public HTTPS callback, so local testing uses a tunnel.

1. Put the app's credentials in `.env`:
   ```
   SHOPIFY_API_KEY=<client_id>
   SHOPIFY_API_SECRET=<client_secret>
   SHOPIFY_SCOPES=read_orders
   ```
2. Start a tunnel to your local server (no signup needed):
   ```
   cloudflared tunnel --url http://localhost:8000
   ```
   Copy the `https://<random>.trycloudflare.com` URL it prints.
3. Set the callback in `.env` and restart uvicorn:
   ```
   APP_BASE_URL=https://<random>.trycloudflare.com
   SHOPIFY_REDIRECT_URI=https://<random>.trycloudflare.com/api/integrations/shopify/callback
   ```
4. Register that redirect URL on the app. For a config-as-code app, in
   `shopify.app.toml`:
   ```toml
   application_url = "https://<random>.trycloudflare.com"
   [auth]
   redirect_urls = [ "https://<random>.trycloudflare.com/api/integrations/shopify/callback" ]
   ```
   then `shopify app deploy`.
5. Create a brand and get a session token (see Quick start), then fetch the
   install redirect (the endpoint is authenticated, so pass the bearer token and
   read the `Location` header):
   ```
   curl -i "https://<tunnel>/api/integrations/shopify/install?brand_id=<BRAND_ID>&shop=<shop>.myshopify.com" \
        -H "Authorization: Bearer <SESSION_TOKEN>"
   ```
   Open the `Location` URL in a browser, approve, and Shopify redirects to the
   callback, which stores the offline token on the brand. Generating a report
   then pulls that store's live orders.
