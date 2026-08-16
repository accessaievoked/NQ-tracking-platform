"""GA4 funnel views — deterministic compute for the Data Insights page.

This is the Looker "Funnel Dashboard" rebuilt on the GA4 Data API. Every view is
the same shape underneath: count *users* per ecommerce event, broken down by one
or two dimensions (date, page title, hour, weekday, month, OS, browser), then
express each step as a percentage of the step before it.

Rate definitions (kept in one place so every table means the same thing):

    ATC %                = users(add_to_cart)    / users(view_item)
    Checkout %           = users(begin_checkout) / users(view_item)
    Purchase % / CR %    = users(purchase)       / users(view_item)
    ATC -> Checkout %    = users(begin_checkout) / users(add_to_cart)
    Checkout -> Purchase = users(purchase)       / users(begin_checkout)

so that ATC% x (ATC->Checkout%) x (Checkout->Purchase%) == Purchase%. That chain
holds on every page of the source report and is asserted in the tests.

"Add to baskets" is an *event* count (a user can add several items), which is why
it is larger than the user-based ATC% would suggest — same as the source report.

Totals are not row sums: user counts de-duplicate across days, so grand totals
come from their own un-broken-down GA4 query. The LLM never touches any of this;
all arithmetic is here and unit-tested.
"""
from __future__ import annotations

from typing import Any, Iterable

# --- Funnel steps ---------------------------------------------------------

# internal step name -> GA4 event name
STEP_EVENTS: dict[str, str] = {
    "session_start": "session_start",
    "first_visit": "first_visit",
    "page_view": "page_view",
    "scroll": "scroll",
    "item_list_view": "view_item_list",
    "item_view": "view_item",
    "add_to_cart": "add_to_cart",
    "view_cart": "view_cart",
    "begin_checkout": "begin_checkout",
    "add_shipping": "add_shipping_info",
    "add_payment": "add_payment_info",
    "purchase": "purchase",
}

# The source report's checkout micro-funnel uses five abbreviations — CAS, CAF,
# GCI, ASI, API — which are custom events in that GA4 property, not GA4
# standards. These are best-guess mappings onto the standard ecommerce events.
#
# To correct them: call GET /api/brands/{id}/analytics/events, which lists the
# event names the property actually sends with their user counts, then edit this
# dict. Nothing else needs to change — the columns, rates and totals all derive
# from it. A step mapped to an event the property never sends renders as "—".
CUSTOM_STEP_EVENTS: dict[str, str] = {
    "cas": "view_cart",           # CAS — cart step after add-to-cart
    "caf": "remove_from_cart",    # CAF — the failure/abandon branch
    "gci": "begin_checkout",      # GCI — checkout initiated
    "asi": "add_shipping_info",   # ASI — shipping info added
    "api": "add_payment_info",    # API — payment info added
}

ALL_STEP_EVENTS: dict[str, str] = {**STEP_EVENTS, **CUSTOM_STEP_EVENTS}

# One event can back several steps (GCI and begin_checkout may be the same
# event until the custom names are confirmed), so this maps event -> steps.
EVENT_STEPS: dict[str, list[str]] = {}
for _step, _event in ALL_STEP_EVENTS.items():
    EVENT_STEPS.setdefault(_event, []).append(_step)

FUNNEL_EVENT_NAMES: list[str] = sorted(EVENT_STEPS)


# --- Column definitions ---------------------------------------------------
# type: "text" | "int" | "float" | "pct" | "money"
# heat: True -> the UI paints a red->green scale across the column (like Looker)

def _c(key: str, label: str, type_: str = "int", heat: bool = False) -> dict[str, Any]:
    return {"key": key, "label": label, "type": type_, "heat": heat}


_DIM = _c("dim", "{dim}", "text")
_DIM2 = _c("dim2", "{dim2}", "text")
_VIEWS = _c("item_view_users", "Item view users", "float")
_ATC = _c("atc_pct", "ATC", "pct", True)
_ATC2CK = _c("atc_to_checkout_pct", "ATC -> Checkout", "pct", True)
_CK2P = _c("checkout_to_purchase_pct", "Checkout -> Purchase", "pct", True)
_CR = _c("purchase_pct", "CR%", "pct", True)

# The checkout micro-funnel columns shared by the dropout pages.
_MICRO = [
    _c("atc_pct", "ATC%", "pct", True),
    _c("atc_to_cas_pct", "ATC->CAS", "pct", True),
    _c("atc_to_caf_pct", "ATC-> CAF", "pct", True),
    _c("atc_to_gci_pct", "ATC -> GCI", "pct", True),
    _c("gci_to_asi_pct", "GCI -> ASI", "pct", True),
    _c("asi_to_api_pct", "ASI -> API", "pct", True),
    _c("api_to_purchase_pct", "API->P", "pct", True),
    _CR,
]

LAYOUTS: dict[str, list[dict[str, Any]]] = {
    # "Item View --> Purchase (By Date)" — the only table with Total users.
    "basic": [
        _DIM,
        _c("total_users", "Total users"),
        _VIEWS,
        _c("add_to_baskets", "Add to baskets"),
        _ATC,
        _c("checkout_pct", "Checkout", "pct", True),
        _c("purchase_pct", "Purchase", "pct", True),
    ],
    # Same, broken down by page title: no Total users column, and its grand
    # total is identical to the by-date table's.
    "basic_page": [
        _DIM, _VIEWS,
        _c("add_to_baskets", "Add to baskets"),
        _ATC,
        _c("checkout_pct", "Checkout", "pct", True),
        _c("purchase_pct", "Purchase", "pct", True),
    ],
    # Rates only — no Total users, no Add to baskets.
    "rates": [
        _DIM, _VIEWS, _ATC,
        _c("checkout_pct", "Checkout", "pct", True),
        _c("purchase_pct", "Purchase", "pct", True),
    ],
    "rates_cr": [
        _DIM, _VIEWS, _ATC,
        _c("checkout_pct", "Checkout", "pct", True),
        _c("purchase_pct", "Purchase", "pct", True),
        _CR,
    ],
    # Step-to-step conversion, ending on the overall rate.
    "steps": [
        _DIM, _VIEWS, _ATC, _ATC2CK, _CK2P,
        _c("purchase_pct", "Purchase", "pct", True),
    ],
    "steps_cr": [_DIM, _VIEWS, _ATC, _ATC2CK, _CK2P, _CR],
    # The source's by-page step table stops at Checkout -> Purchase.
    "steps_page": [_DIM, _VIEWS, _ATC, _ATC2CK, _CK2P],
    # Browser page adds PDP -> Checkout alongside the ATC-relative rate.
    "browser_date": [
        _DIM, _VIEWS, _ATC,
        _c("pdp_to_checkout_pct", "PDP -> Checkout", "pct", True),
        _ATC2CK, _CK2P, _CR,
    ],
    # Checkout micro-funnel (CAS / CAF / GCI / ASI / API).
    "micro": [_DIM, _VIEWS, *_MICRO],
    # Cohort-style table: two dimensions, plus ATC -> Purchase.
    "cohort": [
        _DIM, _DIM2, _VIEWS, _ATC, _ATC2CK, _CK2P,
        _c("atc_to_purchase_pct", "ATC -> Purchase", "pct", True),
        _CR,
    ],
    # Site-wide micro-funnel: every step as a share of all users.
    "website_wide": [
        _DIM,
        _c("page_view_rate_pct", "P.View", "pct", True),
        _c("item_view_rate_pct", "V.Item", "pct", True),
        _c("session_start_rate_pct", "S.Start", "pct", True),
        _c("engagement_rate_pct", "Engagement rate", "pct", True),
        _c("first_visit_rate_pct", "f.Visit", "pct", True),
        _c("scroll_rate_pct", "Scroll", "pct", True),
        _c("atc_rate_pct", "ATC%", "pct", True),
        _c("cas_rate_pct", "CAS", "pct", True),
        _c("caf_rate_pct", "CAF", "pct", True),
        _c("gci_rate_pct", "GCI", "pct", True),
        _c("asi_rate_pct", "ASI", "pct", True),
        _c("api_rate_pct", "API", "pct", True),
        _c("purchase_rate_pct", "Purch", "pct", True),
    ],
    # Item-scoped: counts items rather than users, and attributes purchases to
    # the product itself rather than the page the purchase event fired on.
    "items": [
        _DIM,
        _c("item_view_users", "Item views", "float"),
        _c("add_to_cart_users", "Added to cart", "float"),
        _c("begin_checkout_users", "Checked out", "float"),
        _c("purchase_users", "Purchased", "float"),
        _ATC, _CK2P,
        _c("purchase_pct", "View -> Purchase", "pct", True),
        _c("item_revenue", "Revenue", "money"),
    ],
}

# Item-scoped metrics -> the same funnel steps, so build_row() is reused as-is.
ITEM_METRICS = {
    "itemsViewed": "item_view",
    "itemsAddedToCart": "add_to_cart",
    "itemsCheckedOut": "begin_checkout",
    "itemsPurchased": "purchase",
}

# Percent columns whose "good" direction is inverted (low = green).
INVERSE_PCT = {
    "shipping_dropout_pct", "payment_dropout_pct", "purchase_dropout_pct",
    "checkout_dropout_pct", "atc_to_caf_pct", "caf_rate_pct",
}


# --- View definitions -----------------------------------------------------
# One entry per tab on the Data Insights page.

def _t(key: str, title: str, dimension: str | list[str], layout: str,
       sort: str = "dim_desc", limit: int = 5000, source: str = "events") -> dict[str, Any]:
    """source: 'events' = user counts per funnel event; 'items' = item-scoped."""
    dims = [dimension] if isinstance(dimension, str) else list(dimension)
    return {"key": key, "title": title, "dimension": dims[0], "dimensions": dims,
            "layout": layout, "sort": sort, "limit": limit, "source": source}


VIEWS: dict[str, dict[str, Any]] = {
    "overview": {
        "label": "Overview",
        "blurb": "The headline funnel for the selected period.",
        "tables": [
            _t("by_date", "Item View --> Purchase (By Date)", "date", "basic"),
            _t("by_product", "Top Products", "pageTitle", "steps_page", "item_views_desc", limit=50),
        ],
        "charts": [
            {"type": "funnel", "table": "by_date", "title": "Funnel for the period"},
            {"type": "line", "table": "by_date", "x": "dim", "series": ["purchase_pct"],
             "title": "Purchase rate by day"},
        ],
    },
    "product_funnel": {
        "label": "Product Funnel",
        "blurb": "Item view to purchase, by day and by product page.",
        "tables": [
            _t("by_date", "Item View --> Purchase (By Date)", "date", "basic"),
            _t("by_product", "Item View --> Purchase (By Products)", "pageTitle", "basic_page",
               "item_views_desc"),
            _t("by_date_steps", "Item View --> Purchase (By Date)", "date", "steps"),
            _t("by_product_steps", "Item View --> Purchase (By Products)", "pageTitle",
               "steps_page", "item_views_desc"),
        ],
        "charts": [
            {"type": "line", "table": "by_date", "x": "dim",
             "series": ["atc_pct", "checkout_pct", "purchase_pct"],
             "title": "Conversion rates by day"},
            {"type": "funnel", "table": "by_date", "title": "Overall funnel"},
            {"type": "bar", "table": "by_product", "x": "dim", "series": ["item_view_users"],
             "title": "Top products by item views", "limit": 12},
        ],
    },
    "funnel_long_view": {
        "label": "Funnel - Long View",
        "blurb": "The same daily funnel over a long horizon — set the range wide.",
        "default_days": 224,
        "tables": [
            _t("by_date", "Item View --> Purchase (By Date)", "date", "basic"),
            _t("by_date_steps", "Item View --> Purchase (By Date)", "date", "steps"),
        ],
        "charts": [
            {"type": "line", "table": "by_date", "x": "dim",
             "series": ["atc_pct", "checkout_pct", "purchase_pct"],
             "title": "Conversion rates over the full period"},
            {"type": "funnel", "table": "by_date", "title": "Full funnel", "long": True},
        ],
    },
    "hourly": {
        "label": "Hourly Dashboard",
        "blurb": "Which hours convert — and which just browse.",
        "default_days": 1,
        "tables": [
            _t("by_hour", "Item View --> Purchase (By Hour)", "hour", "rates", "dim_asc"),
            _t("by_hour_steps", "Item View --> Purchase (By Hour)", "hour", "steps_cr", "dim_asc"),
        ],
        "charts": [
            {"type": "bar", "table": "by_hour", "x": "dim", "series": ["item_view_users"],
             "title": "Item views by hour of day", "limit": 24},
            {"type": "line", "table": "by_hour", "x": "dim", "series": ["atc_pct", "purchase_pct"],
             "title": "ATC and purchase rate by hour", "chrono": False},
        ],
    },
    "weekly_trends": {
        "label": "Weekly Trends",
        "blurb": "Day-of-week performance, against the previous period.",
        "compare": True,
        "tables": [
            _t("by_weekday", "Item View --> Purchase (By Week)", "dayOfWeekName", "rates",
               "dim_weekday"),
            _t("by_weekday_steps", "Item View --> Purchase (By Week)", "dayOfWeekName",
               "steps_page", "dim_weekday"),
            _t("by_hour", "By Hour of Day", "hour", "steps_cr", "dim_asc"),
        ],
        "charts": [
            {"type": "line", "table": "by_hour", "x": "dim", "series": ["atc_to_checkout_pct"],
             "title": "ATC --> Checkout", "compare": True, "chrono": False},
            {"type": "line", "table": "by_hour", "x": "dim",
             "series": ["checkout_to_purchase_pct"],
             "title": "Checkout -->> Purchase", "compare": True, "chrono": False},
        ],
    },
    "website_funnel": {
        "label": "Website Funnel",
        "blurb": "Every step as a share of all site users, plus browser and page cuts.",
        "tables": [
            _t("by_browser", "Item View --> Purchase (By Browser)", "browser", "steps_cr",
               "item_views_desc"),
            _t("by_product", "Item View --> Purchase (By Products)", "pageTitle", "rates_cr",
               "item_views_desc"),
            _t("by_date_wide", "Website Funnel (By Date)", "date", "website_wide"),
        ],
        "charts": [
            {"type": "funnel", "table": "by_date_wide", "title": "Site-wide funnel", "site": True},
            {"type": "line", "table": "by_date_wide", "x": "dim",
             "series": ["atc_rate_pct", "gci_rate_pct", "purchase_rate_pct"],
             "title": "Share of all users reaching each step"},
        ],
    },
    "device_brand": {
        "label": "Device Brand",
        "blurb": "Funnel split by operating system, with the daily baseline.",
        "tables": [
            _t("by_date_steps", "Item View --> Purchase (By Date)", "date", "steps_page"),
            _t("by_os", "Item View --> Purchase (By Device Brand)", "operatingSystem", "rates",
               "item_views_desc"),
            _t("by_date", "Item View --> Purchase (By Date)", "date", "rates"),
            _t("by_os_steps", "Item View --> Purchase (By Device Brand)", "operatingSystem",
               "steps_page", "item_views_desc"),
            _t("by_product", "Item View --> Purchase (By Products)", "pageTitle", "rates",
               "item_views_desc"),
        ],
        "charts": [
            {"type": "bar", "table": "by_os", "x": "dim", "series": ["item_view_users"],
             "title": "Item views by operating system", "limit": 10},
            {"type": "bar", "table": "by_os", "x": "dim", "series": ["purchase_pct"],
             "title": "Purchase rate by operating system", "limit": 10},
        ],
    },
    "browser_funnel": {
        "label": "Browser Funnel",
        "blurb": "A browser converting far below the others usually means a bug.",
        "tables": [
            _t("by_date", "Item View --> Purchase (By Date)", "date", "browser_date"),
            _t("by_browser", "Item View --> Purchase (By Browser)", "browser", "steps_cr",
               "item_views_desc"),
            _t("by_product", "Item View --> Purchase (By Products)", "pageTitle", "rates_cr",
               "item_views_desc"),
        ],
        "charts": [
            {"type": "bar", "table": "by_browser", "x": "dim", "series": ["purchase_pct"],
             "title": "Purchase rate by browser", "limit": 10},
            {"type": "bar", "table": "by_browser", "x": "dim", "series": ["item_view_users"],
             "title": "Item views by browser", "limit": 10},
        ],
    },
    "cohort": {
        "label": "Cohort View",
        "blurb": "Product pages by month, with ATC -> Purchase.",
        "default_days": 224,
        "tables": [
            _t("by_product_month", "Item View --> Purchase (By Product / Month)",
               ["pageTitle", "yearMonth"], "cohort", "item_views_desc", limit=2000),
        ],
        "charts": [
            {"type": "bar", "table": "by_product_month", "x": "dim",
             "series": ["item_view_users"], "title": "Top product-months by item views",
             "limit": 12},
        ],
    },
    "checkout_dropout": {
        "label": "Checkout Dropout Funnel",
        "blurb": "Where people abandon between add-to-cart and payment.",
        "default_days": 224,
        "tables": [
            _t("by_date", "Checkout Dropout (By Date)", "date", "micro"),
            _t("by_week", "Checkout Dropout (By Week)", "yearWeek", "micro"),
            _t("by_month", "Checkout Dropout (By Month)", "yearMonth", "micro"),
        ],
        "charts": [
            {"type": "funnel", "table": "by_date", "title": "Checkout funnel", "checkout": True},
            {"type": "line", "table": "by_date", "x": "dim",
             "series": ["atc_to_gci_pct", "gci_to_asi_pct", "asi_to_api_pct",
                        "api_to_purchase_pct"],
             "title": "Step-to-step checkout conversion"},
        ],
    },
    "daily_checkout": {
        "label": "Daily Checkout Funnel",
        "blurb": "Monthly summary over the daily checkout micro-funnel.",
        "default_days": 224,
        "tables": [
            _t("by_month", "Item View --> Purchase (By Month)", "yearMonth", "steps"),
            _t("by_date", "Item View --> Purchase (By Date)", "date", "micro"),
        ],
        "charts": [
            {"type": "bar", "table": "by_month", "x": "dim", "series": ["item_view_users"],
             "title": "Item view users by month"},
            {"type": "line", "table": "by_date", "x": "dim",
             "series": ["atc_pct", "purchase_pct"], "title": "ATC and CR by day"},
        ],
    },
}

VIEW_ORDER = [
    "overview",
    "product_funnel",
    "funnel_long_view",
    "hourly",
    "weekly_trends",
    "website_funnel",
    "device_brand",
    "browser_funnel",
    "cohort",
    "checkout_dropout",
    "daily_checkout",
]

DIM_LABELS = {
    "date": "Date",
    "pageTitle": "Page title",
    "hour": "Hour",
    "dateHour": "Date + hour",
    "yearWeek": "Week",
    "yearMonth": "Month",
    "dayOfWeekName": "Day of week",
    "deviceCategory": "Device",
    "operatingSystem": "Operating system",
    "mobileDeviceBranding": "Device brand",
    "browser": "Browser",
    "sessionDefaultChannelGroup": "Channel",
    "sessionSourceMedium": "Source / medium",
    "itemName": "Product",
}


# --- Maths helpers --------------------------------------------------------

def _round(x: float, n: int = 2) -> float:
    return round(float(x or 0), n)


def _pct(part: float, whole: float) -> float | None:
    """Percentage, or None when the denominator is zero (renders as '—')."""
    if not whole:
        return None
    return _round(part / whole * 100.0)


def _sub_pct(part: float, whole: float) -> float | None:
    """Drop-off percentage: the share of ``whole`` that did NOT reach ``part``."""
    if not whole:
        return None
    return _round((whole - part) / whole * 100.0)


# --- Row building ---------------------------------------------------------

def _blank_steps() -> dict[str, float]:
    return {s: 0.0 for s in ALL_STEP_EVENTS}


def build_row(dim_value: str, users: dict[str, float], events: dict[str, float],
              total_users: float = 0.0, sessions: float = 0.0,
              revenue: float = 0.0, engagement_rate: float | None = None) -> dict[str, Any]:
    """Turn one dimension's per-step user counts into every derived column.

    ``users`` maps step name -> users who fired that event; ``events`` maps step
    name -> raw event count. Extra keys are ignored, missing keys count as zero.
    """
    u = {**_blank_steps(), **{k: float(v or 0) for k, v in (users or {}).items()}}
    e = {**_blank_steps(), **{k: float(v or 0) for k, v in (events or {}).items()}}

    item_views = u["item_view"]
    atc = u["add_to_cart"]
    checkout = u["begin_checkout"]
    shipping = u["add_shipping"]
    payment = u["add_payment"]
    purchase = u["purchase"]
    tu = float(total_users or 0)

    row: dict[str, Any] = {
        "dim": dim_value,
        "total_users": int(tu),
        "sessions": int(sessions or 0),
        "add_to_baskets": int(e["add_to_cart"]),
        "purchases_count": int(e["purchase"]),
        "item_revenue": _round(revenue),
        # Step user counts. GA4 returns modelled (fractional) user counts for
        # thresholded properties, so two decimals are kept rather than rounded away.
        "item_list_view_users": _round(u["item_list_view"]),
        "item_view_users": _round(item_views),
        "add_to_cart_users": _round(atc),
        "view_cart_users": _round(u["view_cart"]),
        "begin_checkout_users": _round(checkout),
        "add_shipping_users": _round(shipping),
        "add_payment_users": _round(payment),
        "purchase_users": _round(purchase),
        # Funnel rates, all relative to item views.
        "atc_pct": _pct(atc, item_views),
        "checkout_pct": _pct(checkout, item_views),
        "purchase_pct": _pct(purchase, item_views),
        "pdp_to_checkout_pct": _pct(u["gci"], item_views),
        # Step-to-step.
        "atc_to_checkout_pct": _pct(checkout, atc),
        "checkout_to_purchase_pct": _pct(purchase, checkout),
        "atc_to_purchase_pct": _pct(purchase, atc),
        # Checkout micro-funnel (CAS / CAF / GCI / ASI / API).
        "atc_to_cas_pct": _pct(u["cas"], atc),
        "atc_to_caf_pct": _pct(u["caf"], atc),
        "atc_to_gci_pct": _pct(u["gci"], atc),
        "gci_to_asi_pct": _pct(u["asi"], u["gci"]),
        "asi_to_api_pct": _pct(u["api"], u["asi"]),
        "api_to_purchase_pct": _pct(purchase, u["api"]),
        # Site-wide: every step as a share of all users.
        "item_view_rate_pct": _pct(item_views, tu),
        "page_view_rate_pct": _pct(u["page_view"], tu),
        "session_start_rate_pct": _pct(u["session_start"], tu),
        "first_visit_rate_pct": _pct(u["first_visit"], tu),
        "scroll_rate_pct": _pct(u["scroll"], tu),
        "atc_rate_pct": _pct(atc, tu),
        "cas_rate_pct": _pct(u["cas"], tu),
        "caf_rate_pct": _pct(u["caf"], tu),
        "gci_rate_pct": _pct(u["gci"], tu),
        "asi_rate_pct": _pct(u["asi"], tu),
        "api_rate_pct": _pct(u["api"], tu),
        "purchase_rate_pct": _pct(purchase, tu),
        "site_cvr_pct": _pct(purchase, tu),
        "engagement_rate_pct": (None if engagement_rate is None
                                else _round(float(engagement_rate) * 100.0)),
        # Checkout dropout.
        "shipping_dropout_pct": _sub_pct(shipping, checkout),
        "payment_dropout_pct": _sub_pct(payment, shipping),
        "purchase_dropout_pct": _sub_pct(purchase, payment),
        "checkout_dropout_pct": _sub_pct(purchase, checkout),
    }
    return row


WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _sort_rows(rows: list[dict[str, Any]], sort: str) -> list[dict[str, Any]]:
    # Date sorts use the raw GA4 value (20260811), never the pretty label —
    # "Aug 11" vs "Jul 31" would sort alphabetically and scramble the calendar.
    def dim(r):
        return _sort_key(r.get("dim_raw", r["dim"]))

    if sort == "dim_asc":
        return sorted(rows, key=dim)
    if sort == "dim_weekday":
        return sorted(rows, key=lambda r: (WEEKDAYS.index(r["dim"])
                                           if r["dim"] in WEEKDAYS else 99))
    # Metric sorts break ties on the label so equal rows keep a stable order
    # (rows are assembled from a set, whose iteration order is not stable).
    if sort == "item_views_desc":
        return sorted(rows, key=lambda r: (-(r.get("item_view_users") or 0), str(r["dim"])))
    if sort == "users_desc":
        return sorted(rows, key=lambda r: (-(r.get("total_users") or 0), str(r["dim"])))
    return sorted(rows, key=dim, reverse=True)  # dim_desc


def _sort_key(v: Any):
    s = str(v)
    return (0, int(s)) if s.isdigit() else (1, s)


# --- Dimension formatting -------------------------------------------------

_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
_MONTHS_FULL = ["January", "February", "March", "April", "May", "June", "July",
                "August", "September", "October", "November", "December"]


def format_dim(dimension: str, raw: str) -> str:
    """Human labels for GA4's compact dimension values (20260811 -> Aug 11, 2026)."""
    s = str(raw or "")
    try:
        if dimension == "date" and len(s) == 8:
            return f"{_MONTHS[int(s[4:6]) - 1]} {int(s[6:8])}, {s[:4]}"
        if dimension == "dateHour" and len(s) == 10:
            return f"{_MONTHS[int(s[4:6]) - 1]} {int(s[6:8])}, {_hour(s[8:10])}"
        if dimension == "hour":
            return _hour(s)
        if dimension == "yearWeek" and len(s) == 6:
            return s[4:].lstrip("0") or "0"
        if dimension == "yearMonth" and len(s) == 6:
            return _MONTHS_FULL[int(s[4:]) - 1]
    except (ValueError, IndexError):
        return s or "(not set)"
    return s or "(not set)"


def _hour(value: str) -> str:
    """GA4's 0-23 hour as the source report writes it: 12AM, 1AM, ... 11PM."""
    h = int(value)
    suffix = "AM" if h < 12 else "PM"
    hour12 = 12 if h % 12 == 0 else h % 12
    return f"{hour12}{suffix}"


# --- View assembly --------------------------------------------------------

def build_table(
    spec: dict[str, Any],
    event_rows: Iterable[dict[str, Any]],
    base_rows: Iterable[dict[str, Any]],
    total_event_rows: Iterable[dict[str, Any]],
    total_base: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Assemble one table from four GA4 result sets.

    ``event_rows``  dims = [*dimensions, eventName]  (or [*dimensions] for items)
    ``base_rows``   dims = [*dimensions]
    ``total_event_rows`` dims = [eventName]        (de-duplicated period totals)
    ``total_base``  metrics for the whole period, no breakdown
    """
    dims_spec: list[str] = spec.get("dimensions") or [spec["dimension"]]
    ndim = len(dims_spec)
    is_items = spec.get("source") == "items"

    users: dict[tuple, dict[str, float]] = {}
    events: dict[tuple, dict[str, float]] = {}
    revenue: dict[tuple, float] = {}
    for r in event_rows:
        dims = r.get("dimensions") or []
        if len(dims) < ndim:
            continue
        key = tuple(dims[:ndim])
        if is_items:
            steps = {step: r["metrics"].get(metric, 0.0) for metric, step in ITEM_METRICS.items()}
            users[key] = steps
            events[key] = {"add_to_cart": steps["add_to_cart"], "purchase": steps["purchase"]}
            revenue[key] = r["metrics"].get("itemRevenue", 0.0)
            continue
        if len(dims) < ndim + 1:
            continue
        for step in EVENT_STEPS.get(dims[ndim], []):
            users.setdefault(key, {})[step] = r["metrics"].get("totalUsers", 0.0)
            events.setdefault(key, {})[step] = r["metrics"].get("eventCount", 0.0)

    base: dict[tuple, dict[str, float]] = {}
    for r in base_rows:
        dims = r.get("dimensions") or []
        if len(dims) < ndim:
            continue
        base[tuple(dims[:ndim])] = r["metrics"]

    rows: list[dict[str, Any]] = []
    for key in set(users) | set(base):
        b = base.get(key, {})
        row = build_row(
            key[0],
            users.get(key, {}),
            events.get(key, {}),
            total_users=b.get("totalUsers", 0.0),
            sessions=b.get("sessions", 0.0),
            revenue=revenue.get(key, 0.0),
            engagement_rate=b.get("engagementRate"),
        )
        row["dim_raw"] = key[0]
        row["dim"] = format_dim(dims_spec[0], key[0])
        if ndim > 1:
            row["dim2_raw"] = key[1]
            row["dim2"] = format_dim(dims_spec[1], key[1])
        row["_key"] = "|".join(key)
        rows.append(row)

    rows = _sort_rows(rows, spec.get("sort", "dim_desc"))
    row_count = len(rows)
    rows = rows[: spec.get("limit") or 5000]

    # Grand total: de-duplicated period totals, never a sum of the rows (a user
    # who browsed on three days is one user, not three).
    t_users: dict[str, float] = {}
    t_events: dict[str, float] = {}
    t_revenue = 0.0
    for r in total_event_rows:
        if is_items:
            t_users = {step: r["metrics"].get(m, 0.0) for m, step in ITEM_METRICS.items()}
            t_events = {"add_to_cart": t_users["add_to_cart"], "purchase": t_users["purchase"]}
            t_revenue = r["metrics"].get("itemRevenue", 0.0)
            break
        dims = r.get("dimensions") or []
        if not dims:
            continue
        for step in EVENT_STEPS.get(dims[0], []):
            t_users[step] = r["metrics"].get("totalUsers", 0.0)
            t_events[step] = r["metrics"].get("eventCount", 0.0)
    tb = total_base or {}
    totals = build_row("Grand total", t_users, t_events,
                       total_users=tb.get("totalUsers", 0.0),
                       sessions=tb.get("sessions", 0.0),
                       revenue=t_revenue,
                       engagement_rate=tb.get("engagementRate"))

    labels = {"{dim}": DIM_LABELS.get(dims_spec[0], dims_spec[0])}
    if ndim > 1:
        labels["{dim2}"] = DIM_LABELS.get(dims_spec[1], dims_spec[1])
    columns = []
    for col in LAYOUTS[spec["layout"]]:
        label = col["label"]
        for token, value in labels.items():
            label = label.replace(token, value)
        # `inverse` tells the UI to flip the heat scale (a high dropout is bad).
        columns.append({**col, "label": label, "inverse": col["key"] in INVERSE_PCT})

    return {
        "key": spec["key"],
        "title": spec["title"],
        "dimension": dims_spec[0],
        "dimensions": dims_spec,
        "layout": spec["layout"],
        # Item-scoped tables count items, event-scoped ones count users, so their
        # rates aren't comparable. The UI badges this rather than letting two
        # different 'Grand total' rows sit side by side looking inconsistent.
        "scope": "items" if is_items else "users",
        "scope_label": "Item-scoped" if is_items else "User-scoped",
        "columns": columns,
        "rows": rows,
        "totals": totals,
        "row_count": row_count,
    }


def view_spec(view: str) -> dict[str, Any]:
    if view not in VIEWS:
        raise KeyError(f"Unknown view '{view}'")
    return VIEWS[view]


def list_views() -> list[dict[str, Any]]:
    """The option bar: every view, in display order."""
    return [
        {
            "key": k,
            "label": VIEWS[k]["label"],
            "blurb": VIEWS[k]["blurb"],
            "default_days": VIEWS[k].get("default_days", 30),
            "compare": bool(VIEWS[k].get("compare")),
        }
        for k in VIEW_ORDER
        if k in VIEWS
    ]
