# SOP — Connecting Shopify to the NQ Tracking Platform

**Scope:** How to connect a client's Shopify store so the platform can pull orders and generate reports.
**Method:** Shopify OAuth 2.0 authorization-code flow (offline token). The token is long-lived and self-served — the client approves once in their own Shopify admin.
**Audience:** Internal operator (you) + the client (store owner), who does one approval click.

---

## 1. How it works (one-paragraph overview)

The platform has a single Shopify app (**NQ-tracker**, registered in the Shopify Dev Dashboard). When a brand connects Shopify, the app sends the store owner to Shopify's own "Install / Approve" screen. On approval, Shopify redirects back to our `/callback` endpoint, which verifies the request (HMAC + a signed state), exchanges the one-time code for a permanent **offline access token**, and stores it (encrypted) against that brand. From then on, report generation uses that token to read the store's orders. No API keys are ever pasted by the client.

---

## 2. One-time platform setup (already done — reference only)

These are configured once and shared by every client store. You do **not** repeat these per client.

- **Shopify app:** `NQ-tracker` (Dev Dashboard), config in `nq-tracker/shopify.app.toml`.
- **Client ID:** `ddaf91f8cd04ddd4d13b630a82164f23` (this is `SHOPIFY_API_KEY`).
- **Redirect URL (must match exactly):** `https://nq-tracking-platform.fly.dev/api/integrations/shopify/callback`
- **Access scopes:** `read_orders` (required for reports), plus whatever else is set in `shopify.app.toml` / `SHOPIFY_SCOPES`.
- **Server secrets (Fly):** `SHOPIFY_API_KEY`, `SHOPIFY_API_SECRET`, `SHOPIFY_REDIRECT_URI`.
- If the app config ever changes, redeploy it with `shopify app deploy` (run in the `nq-tracker` folder).

> **Distribution note (important):** Shopify only lets a store install the app if that store is allowed by the app's distribution. With **custom distribution**, each independent client store must be added to the app's distribution (one store per custom app / one Plus org). If a store isn't permitted, connection fails with `shop_not_permitted`. Confirm the store is added **before** step 3.

---

## 3. Per-client connection procedure

Do this once for each new client store.

**Step 1 — Confirm the store is permitted.**
In the Shopify Dev/Partner Dashboard, make sure the client's store (e.g. `client-store.myshopify.com`) is included in the NQ-tracker app's distribution. (See the distribution note above.)

**Step 2 — Register the client's login** (if not already done).
Run: `python -m scripts.register_user client@email.com "Client Name"`. Send them the login link it prints.

**Step 3 — Open the client's brand in the platform.**
Log in (or have the client log in), select their brand, and go to **Brand Library**.

**Step 4 — Start the Shopify connection.**
On the **Shopify Store** tile, click **Connect** → **Continue to Shopify**. Enter the store domain in the form `client-store.myshopify.com` (no `https://`, no trailing slash).

**Step 5 — Approve on Shopify.**
The browser is redirected to Shopify's approval screen. The **store owner** (must be logged into that Shopify admin) reviews the requested access (`read_orders`) and clicks **Install / Approve**.

**Step 6 — Automatic return + storage.**
Shopify redirects back to the platform (`/?connected=shopify`). The backend verifies and stores the offline token automatically. The Shopify tile now shows **✓ Connected**.

**Step 7 — Verify (see section 4).**

---

## 4. Verification

- In **Brand Library**, the Shopify tile shows **✓ Connected** (not "Error" or "Not set up").
- Go to **Insights & Reports** → generate a **Money Flow Report** for that brand. If real order numbers appear (not the offline sample data), the live connection works.
- The stored token is a permanent **offline** token — it does not expire and needs no re-approval unless the client uninstalls the app or you change scopes.

---

## 5. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `shop_not_permitted` | Store isn't in the app's custom distribution | Add the store to NQ-tracker's distribution in the Dev Dashboard, then retry |
| `Invalid shop domain` | Domain typed wrong | Use exactly `store.myshopify.com` (no `https://`, no path) |
| `HMAC verification failed` | `SHOPIFY_API_SECRET` mismatch, or the request wasn't really from Shopify | Confirm the Fly secret matches the app's secret; re-run the flow |
| `Invalid or expired state` | Took >10 min between start and approval | Restart the connect flow (state is valid for 10 minutes) |
| Redirect/404 after approval | Redirect URL mismatch | Ensure the app's redirect URL is exactly the `/api/integrations/shopify/callback` URL above; redeploy with `shopify app deploy` if changed |
| Tile shows "Error" | Token exchange failed | Check server logs; usually a secret or scope mismatch |

---

## 6. What's stored (for reference)

Per brand, on success: an `Integration` row (provider `shopify`) with `config = {shop_domain, shop_name, currency}` and an **encrypted** `{access_token, scope}`. Reports read orders via this token using the Shopify Admin REST API (`/admin/api/<version>/orders.json`).
