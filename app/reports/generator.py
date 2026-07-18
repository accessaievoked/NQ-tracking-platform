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
    "values exactly as given. (2) Write in clear, confident prose with short "
    "sections. (3) Lead with the single most important insight (usually the gap "
    "between reported and real ROAS). (4) Explain what the numbers mean for the "
    "business and what to do next. Output Markdown."
)


def build_prompt(brand_name: str, period: str, metrics: dict[str, Any]) -> str:
    return (
        f"Brand: {brand_name}\n"
        f"Period: {period}\n\n"
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

    lines = [
        f"# {brand_name} — Money Flow Report",
        f"_{period}_",
        "",
        "## The headline",
        f"You spent **{cur} {mo['reported_ad_spend']:,.0f}** on ads "
        f"(**{cur} {mo['real_ad_cost']:,.0f}** after {mo['gst_rate']*100:.0f}% GST). "
        f"**{cur} {mi['net_sales']:,.0f}** in net sales actually reached the store.",
        "",
        f"Your ad dashboards claim a ROAS of **{eff['reported_roas']}x**, but the "
        f"real ROAS on money that reached you is **{eff['real_roas']}x** — "
        f"an overstatement of **{eff['roas_overstatement_pct']:.0f}%**.",
        "",
        "## Where the money went",
        f"| Category | Orders | Amount ({cur}) | % of gross |",
        "| --- | ---: | ---: | ---: |",
    ]
    for row in mi["breakdown"]:
        orders = "—" if row["orders"] is None else f"{row['orders']}"
        lines.append(
            f"| {row['category']} | {orders} | {row['amount']:,.0f} | {row['pct_of_gross']}% |"
        )
    lines += [
        f"| **Net Sales — reached you** | {mi['total_orders']} | "
        f"**{mi['net_sales']:,.0f}** | **{mi['net_sales_pct_of_gross']}%** |",
        "",
        "## Bottom line",
        f"After real ad cost, net contribution is **{cur} "
        f"{eff['net_profit_after_ads']:,.0f}**. Treat the platform ROAS as a "
        "vanity metric; budget decisions should use the real ROAS above.",
    ]
    return "\n".join(lines)
