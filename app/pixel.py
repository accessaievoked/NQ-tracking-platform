"""The storefront pixel, served pre-filled per brand.

Kept as a template string rather than a static asset so the Live Journey page can
hand the merchant a copy-paste-ready snippet with their own ingest URL and key
already substituted — no manual editing, so no chance of pasting a placeholder.
"""
from __future__ import annotations

# NOTE ON TRANSPORT: the body is sent as `text/plain` on purpose. A JSON
# content-type makes the request "non-simple", so the browser fires a CORS
# preflight OPTIONS before every single event — doubling requests and dropping
# beacons during page unload. text/plain is a CORS-simple type, so the POST goes
# straight out. The server parses the body as JSON regardless of content-type.
PIXEL_TEMPLATE = """\
/**
 * NQ Live Journey — storefront pixel for {brand_name}
 * ---------------------------------------------------------------------------
 * Shopify admin -> Settings -> Customer events -> Add custom pixel.
 * Paste this whole file, Save, then Connect. Nothing to edit.
 *
 * Generated {generated_at} for brand {brand_id}.
 * The key below is a public, write-only ingest key: it can only add events to
 * this brand, never read them. Rotate it any time from the Live Journey page.
 */

var NQ_ENDPOINT = "{ingest_url}";

var SESSION_COOKIE = "nq_live_sid";
var SESSION_TTL_MIN = 30;

// --- session id -------------------------------------------------------------
// browser.cookie.get/set are async in the pixel sandbox, so resolve once and
// hold the value in memory for the life of the page.
var sessionPromise = null;

function getSessionId() {{
  if (sessionPromise) return sessionPromise;
  sessionPromise = (async function () {{
    var sid;
    try {{
      sid = await browser.cookie.get(SESSION_COOKIE);
    }} catch (e) {{
      sid = null;
    }}
    if (!sid) {{
      sid = "s_" + Date.now().toString(36) + "_" + Math.random().toString(36).slice(2, 10);
    }}
    // Re-set on every page so the 30-minute expiry slides forward with activity.
    try {{
      await browser.cookie.set(
        SESSION_COOKIE + "=" + sid + "; path=/; max-age=" + SESSION_TTL_MIN * 60 + "; SameSite=Lax"
      );
    }} catch (e) {{
      /* non-fatal: the in-memory id still holds for this page */
    }}
    return sid;
  }})();
  return sessionPromise;
}}

// --- consent ----------------------------------------------------------------
function analyticsAllowed() {{
  try {{
    var p = init.customerPrivacy;
    // No consent banner configured -> no restriction to honour yet. When a
    // banner is present this tightens automatically.
    if (!p) return true;
    return p.analyticsProcessingAllowed !== false;
  }} catch (e) {{
    return false;
  }}
}}

// --- transport --------------------------------------------------------------
function send(payload) {{
  var body = JSON.stringify(payload);
  try {{
    if (typeof fetch === "function") {{
      // keepalive lets the request outlive the page unloading mid-navigation,
      // which is exactly when the most interesting hops happen.
      fetch(NQ_ENDPOINT, {{
        method: "POST",
        body: body,
        keepalive: true,
        mode: "cors",
        headers: {{ "Content-Type": "text/plain;charset=UTF-8" }},
      }}).catch(function () {{}});
      return;
    }}
  }} catch (e) {{
    /* fall through to sendBeacon */
  }}
  try {{
    navigator.sendBeacon(NQ_ENDPOINT, body);
  }} catch (e) {{
    /* give up silently — analytics must never break the storefront */
  }}
}}

// --- subscribe --------------------------------------------------------------
// One subscription covers page_viewed, collection_viewed, product_viewed,
// search_submitted, cart_viewed, checkout_started, payment_info_submitted and
// checkout_completed.
analytics.subscribe("all_standard_events", async function (event) {{
  if (!analyticsAllowed()) return;

  var sessionId = "";
  try {{
    sessionId = await getSessionId();
  }} catch (e) {{
    /* proceed without it; clientId alone still yields a usable journey */
  }}

  var doc = (event.context && event.context.document) || {{}};
  var loc = doc.location || {{}};

  send({{
    // clientId is Shopify's documented replacement for the _shopify_y cookie
    // (retired 1 Jan 2026). Stable across storefront, checkout, customer
    // accounts and order status — this is the thread through the journey.
    client_id: event.clientId,
    session_id: sessionId,
    customer_id: (init.data && init.data.customer && init.data.customer.id) || null,
    name: event.name,
    path: (loc.pathname || "/") + (loc.search || ""),
    referrer: doc.referrer || "",
    ts: Date.parse(event.timestamp) || Date.now(),
  }});
}});
"""


def render_pixel(*, brand_name: str, brand_id: str, ingest_url: str, generated_at: str) -> str:
    return PIXEL_TEMPLATE.format(
        brand_name=brand_name,
        brand_id=brand_id,
        ingest_url=ingest_url,
        generated_at=generated_at,
    )
