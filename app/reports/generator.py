"""Report generation: computed metrics -> narrative.

Design rule: the LLM receives only already-computed metrics and writes prose.
It is explicitly told not to alter any number. If ANTHROPIC_API_KEY is unset
(local dev), a deterministic template narrative is produced so the pipeline is
fully testable offline.
"""
from __future__ import annotations

import json
from typing import Any

from app.config import settings

SYSTEM_PROMPT = (
    "You are a performance-marketing analyst writing a Money Flow report for a "
    "Direct-to-Consumer brand. You are given a JSON object of PRE-COMPUTED "
    "metrics. Rules: (1) Never invent, recompute, or alter any number - use the "
    "values exactly as given. (2) 'Net sales' means cash actually COLLECTED "
    "(paid orders minus refunds), not orders merely placed. (3) If "
    "efficiency.ad_spend_connected is false, do NOT state or imply any ROAS - "
    "say ad spend isn't connected yet. (4) Lead with the most important insight. "
    "Output Markdown."
)


def build_prompt(brand_name: str, period: str, metrics: dict[str, Any]) -> str:
    return (
        f"Brand: {brand_name}\nPeriod: {period}\n\n"
        f"PRE-COMPUTED METRICS (do not change any number):\n"
        f"```json\n{json.dumps(metrics, indent=2)}\n```\n\n"
        "Write the Money Flow report now."
    )


def generate_narrative(brand_name: str, period: str, metrics: dict[str, Any]) -> str:
    if not settings.anthropic_api_key:
        return _fallback_narrative(brand_name, period, metrics)
    try:
        return _claude_narrative(brand_name, period, metrics)
    except Exception as exc:  # pragma: no cover - network dependent
        return (
            _fallback_narrative(brand_name, period, metrics)
            + f"\n\n_(LLM narrative unavailable: {exc}; showing computed summary.)_"
        )


def _claude_narrative(brand_name: str, period: str, metrics: dict[str, Any]) -> str:  # pragma: no cover
    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    msg = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": build_prompt(brand_name, period, metrics)}],
    )
    return "".join(block.text for block in msg.content if block.type == "text")


def _fallback_narrative(brand_name: str, period: str, metrics: dict[str, Any]) -> str:
    mi = metrics["money_in"]
    mo = metrics["money_out"]
    eff = metrics["efficiency"]
    cur = metrics.get("currency", "INR")
    connected = bool(eff.get("ad_spend_connected"))

    lines = [f"# {brand_name} — Money Flow Report", f"_{period}_", "", "## The headline"]
    if connected and eff.get("real_roas") is not None:
        lines += [
            f"You spent **{cur} {mo['reported_ad_spend']:,.0f}** on ads "
            f"(**{cur} {mo['real_ad_cost']:,.0f}** after {mo['gst_rate']*100:.0f}% GST). "
            f"**{cur} {mi['net_sales']:,.0f}** in cash actually reached the store.",
            "",
            f"Your ad dashboards claim a ROAS of **{eff['reported_roas']}x**, but the real "
            f"ROAS on collected cash is **{eff['real_roas']}x** — an overstatement of "
            f"**{eff['roas_overstatement_pct']:.0f}%**.",
        ]
    else:
        lines += [
            f"Of **{cur} {mi['gross_sales']:,.0f}** in orders placed, only "
            f"**{cur} {mi['net_sales']:,.0f}** ({mi['net_sales_pct_of_gross']}%) has actually "
            "been collected. _Ad spend isn't connected yet, so ROAS is not shown._",
        ]

    lines += ["", "## Where the money went",
              f"| Category | Orders | Amount ({cur}) | % of gross |",
              "| --- | ---: | ---: | ---: |"]
    for row in mi["breakdown"]:
        orders = "—" if row["orders"] is None else f"{row['orders']}"
        lines.append(f"| {row['category']} | {orders} | {row['amount']:,.0f} | {row['pct_of_gross']}% |")
    lines.append(
        f"| **Net collected — reached you** | — | **{mi['net_sales']:,.0f}** | "
        f"**{mi['net_sales_pct_of_gross']}%** |"
    )

    lines += ["", "## Bottom line"]
    if connected and eff.get("net_profit_after_ads") is not None:
        lines.append(
            f"After real ad cost, net contribution is **{cur} {eff['net_profit_after_ads']:,.0f}**. "
            "Use the real ROAS above for budget decisions, not the platform figure."
        )
    else:
        pending = next((r for r in mi["breakdown"] if r["category"].startswith("Pending")), None)
        pend_txt = (
            f" **{cur} {pending['amount']:,.0f}** ({pending['pct_of_gross']}%) is still pending "
            "collection (e.g. COD not yet delivered)."
            if pending else ""
        )
        lines.append(
            f"Only **{mi['net_sales_pct_of_gross']}%** of placed revenue has actually been "
            f"collected.{pend_txt} Connect Meta/Google ad spend to unlock real ROAS."
        )
    return "\n".join(lines)


def generate_tracking_narrative(brand_name: str, period: str, m: dict) -> str:
    """Template narrative for the GA4-vs-Shopify tracking-reality report."""
    cur = m.get("currency", "INR")
    sh = m["shopify"]
    ga = m["ga4"]
    gap = m["gap"]
    conv = m["conversion"]

    lines = [
        f"# {brand_name} — Tracking Reality (GA4 vs Shopify)",
        f"_{period}_",
        "",
        "## The headline",
        f"GA4 tracked **{ga['purchases']}** purchases, but Shopify actually recorded "
        f"**{sh['orders']}** orders — GA4 is **{gap['verdict']}**, capturing only "
        f"**{gap['order_capture_rate_pct']}%** of real orders "
        f"(**{gap['untracked_orders']}** orders, {gap['untracked_orders_pct']}%, went untracked).",
        "",
        "## GA4 vs reality",
        f"| Metric | GA4 (dashboard) | Shopify (reality) |",
        "| --- | ---: | ---: |",
        f"| Purchases / orders | {ga['purchases']} | {sh['orders']} |",
        f"| Revenue ({cur}) | {ga['purchase_revenue']:,.0f} | {sh['gross_sales']:,.0f} (gross) / "
        f"{sh['collected']:,.0f} (collected) |",
        f"| Conversion rate | {conv['ga4_reported_cvr_pct']}% | {conv['true_cvr_pct']}% (true) |",
        "",
        "## What this means",
        f"The client's GA4 dashboard **understates sales**: it only sees "
        f"{gap['order_capture_rate_pct']}% of orders and {gap['revenue_capture_rate_pct']}% of "
        f"gross revenue. Optimising ad campaigns to GA4 conversions therefore undercounts true "
        f"performance — real conversion rate is **{conv['true_cvr_pct']}%** vs GA4's reported "
        f"**{conv['ga4_reported_cvr_pct']}%** across {m['sessions']:,} sessions. Use Shopify order "
        "data as the source of truth for revenue, and treat GA4 as directional traffic insight.",
    ]
    return "\n".join(lines)


# ==========================================================================
# Generic report narrator (adverti-style report types)
#
# Any report registered in app.reports.specs is driven through here. The model
# gets the report's system prompt + a PRE-COMPUTED facts JSON and writes prose.
# With no ANTHROPIC_API_KEY, a deterministic template renders the facts under
# each spec section so the pipeline is fully testable offline.
# ==========================================================================

def build_report_prompt(brand_name: str, period: str, facts: dict[str, Any]) -> str:
    return (
        f"Brand: {brand_name}\nPeriod: {period}\n\n"
        f"PRE-COMPUTED FACTS (do not change any number):\n"
        f"```json\n{json.dumps(facts, indent=2, default=str)}\n```\n\n"
        "Write the report now, using the exact sections defined in your instructions."
    )


def generate_report_narrative(
    report_type, brand_name: str, period: str, facts: dict[str, Any]
) -> str:
    """Render any spec-backed report. Routes to Claude when a key is set,
    else falls back to a deterministic template built from the same spec."""
    from app.reports.specs import get_spec  # local import avoids a cycle

    spec = get_spec(report_type)
    if not settings.anthropic_api_key:
        return _fallback_report(spec, brand_name, period, facts)
    try:
        return _claude_report(spec, brand_name, period, facts)
    except Exception as exc:  # pragma: no cover - network dependent
        return (
            _fallback_report(spec, brand_name, period, facts)
            + f"\n\n_(LLM narrative unavailable: {exc}; showing computed summary.)_"
        )


def _claude_report(spec, brand_name: str, period: str, facts: dict[str, Any]) -> str:  # pragma: no cover
    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    msg = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=2500,
        system=spec.system_prompt(),
        messages=[{"role": "user", "content": build_report_prompt(brand_name, period, facts)}],
    )
    return "".join(block.text for block in msg.content if block.type == "text")


def _fallback_report(spec, brand_name: str, period: str, facts: dict[str, Any]) -> str:
    """Deterministic, offline rendering: one H2 per spec section, filled from
    ``facts`` when a matching key exists. Facts keys are matched to sections by
    a slugified section name (e.g. 'METRICS BLOCK' -> 'metrics_block').

    This is intentionally simple — it exists so the whole pipeline runs and is
    testable without an API key; Claude produces the real prose when enabled.
    """
    lines = [
        f"# {brand_name} — {spec.title}",
        f"_{period}_",
        "",
        "> _Template preview (no ANTHROPIC_API_KEY set). Set the key to switch "
        "on Claude-written prose. All figures below come straight from the "
        "computed facts and are never altered._",
    ]
    for name, instruction in spec.sections:
        lines += ["", f"## {name}"]
        value = facts.get(_slug(name))
        if value is None:
            lines.append(f"_{instruction}_ — _(no `{_slug(name)}` in facts)_")
        else:
            lines.append(_render_fact(value))
    return "\n".join(lines)


def _slug(name: str) -> str:
    out = []
    for ch in name.lower():
        out.append(ch if ch.isalnum() else "_")
    slug = "".join(out)
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug.strip("_")


def _render_fact(value: Any) -> str:
    """Render a facts value as readable Markdown: strings as-is, list-of-dicts
    as a table, other lists as bullets, scalars inline."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return "\n".join(f"- **{k}:** {v}" for k, v in value.items())
    if isinstance(value, list):
        if value and all(isinstance(row, dict) for row in value):
            cols = list(dict.fromkeys(k for row in value for k in row))  # first-seen order
            head = "| " + " | ".join(cols) + " |"
            sep = "| " + " | ".join("---" for _ in cols) + " |"
            body = [
                "| " + " | ".join(str(row.get(c, "")) for c in cols) + " |"
                for row in value
            ]
            return "\n".join([head, sep, *body])
        return "\n".join(f"- {item}" for item in value)
    return str(value)
