"""Report-type prompt registry (adverti-style reports).

Each report type maps to a :class:`ReportSpec` that encodes its title, cadence,
the shared analyst guardrails (the LLM never does math), and the exact numbered
sections the report must contain. The registry is the single source of truth for
both the Claude prompt and the deterministic template fallback in
``app/reports/generator.py``. Adding or tweaking a report is a data change here.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.models import ReportType

SHARED_RULES = (
    "You are a senior performance-marketing analyst writing a report for an "
    "Indian Direct-to-Consumer (D2C) brand. You are given a JSON object of "
    "PRE-COMPUTED facts.\n"
    "Rules:\n"
    "(1) NEVER invent, recompute, or alter any number — use the values exactly "
    "as given in the facts JSON.\n"
    "(2) If a fact needed for a section is missing or null, say so plainly "
    "instead of guessing (e.g. 'ad spend not connected', 'COGS unavailable').\n"
    "(3) All money is Indian Rupees; write amounts as 'Rs. 12,34,567' "
    "(Indian digit grouping) unless the facts specify another currency.\n"
    "(4) 'Net' / 'retained' / 'collected' revenue means cash actually "
    "collected (paid orders minus refunds/returns), not orders merely placed.\n"
    "(5) Lead with the single most important, data-supported insight.\n"
    "(6) Every recommended action must be ranked by rupee (Rs.) impact and be "
    "concrete (what to do, on which entity, expected Rs. effect).\n"
    "(7) Output GitHub-flavoured Markdown using the exact numbered sections "
    "below, in order, as H2 headings.\n"
)


@dataclass(frozen=True)
class ReportSpec:
    key: ReportType
    title: str
    cadence: str
    summary: str
    sections: list[tuple[str, str]] = field(default_factory=list)

    @property
    def section_names(self) -> list[str]:
        return [name for name, _ in self.sections]

    def system_prompt(self) -> str:
        lines = [
            SHARED_RULES,
            f"\nREPORT: {self.title} ({self.cadence}).",
            f"PURPOSE: {self.summary}",
            "\nProduce exactly these sections, in this order:",
        ]
        for i, (name, instruction) in enumerate(self.sections, start=1):
            lines.append(f"{i}. {name}: {instruction}")
        return "\n".join(lines)


SPECS: dict[ReportType, ReportSpec] = {}


def _spec(key, title, cadence, summary, sections) -> ReportSpec:
    return ReportSpec(key=key, title=title, cadence=cadence, summary=summary, sections=sections)


def _register(spec: ReportSpec) -> None:
    SPECS[spec.key] = spec


# ===================== Batch 1: alert / weekly / monthly specs =====================

_register(_spec(ReportType.cpa_spike_alert, "CPA Spike Alert", "alert",
    "Flag a campaign/ad set whose CPA spiked above its rolling baseline.", [
    ("HEADLINE", "one sentence stating which campaign/ad set triggered the spike and by how much."),
    ("METRICS BLOCK", "CPA, Spend, Conversions, CTR — each with baseline (7/30-day avg), current, and % deviation."),
    ("TRIGGER CONDITION", "the exact threshold crossed (e.g. CPA >X% above rolling average)."),
    ("LIKELY CAUSE", "audience fatigue, bid/budget change, landing-page issue, or seasonality — pick the most data-supported cause."),
    ("AFFECTED ENTITIES", "list campaigns/ad sets/ads driving the spike, ranked by Rs. wasted."),
    ("RECOMMENDED ACTION", "pause, adjust bid, or monitor — with expected Rs. impact if acted on within 24h."),
]))

_register(_spec(ReportType.creative_fatigue_alert, "Creative Fatigue Alert", "alert",
    "Flag creatives losing performance from over-exposure.", [
    ("HEADLINE", "one sentence naming the creative(s) losing performance and the trend duration."),
    ("METRICS BLOCK", "CTR, Frequency, CPM, CPA — this week vs last week vs 4-week average, with direction arrows."),
    ("FATIGUE SIGNAL", "frequency threshold crossed and CTR decay rate."),
    ("CREATIVE STATUS", "tag each active ad as Healthy / Warning / Critical based on fatigue signals."),
    ("TOP 3 FATIGUED CREATIVES", "ranked by Rs. impact of continued spend."),
    ("RECOMMENDED ACTION", "refresh, rotate, or pause — ranked by urgency and Rs. impact."),
]))

_register(_spec(ReportType.daily_spend_alert, "Daily Spend Alert", "daily",
    "Compare today's spend against expected daily budget pace.", [
    ("HEADLINE", "one sentence on today's spend vs the expected daily budget pace."),
    ("METRICS BLOCK", "Spend, Conversions, CPA, ROAS — today vs yesterday vs 7-day average."),
    ("PACING STATUS", "over-pacing / under-pacing / on-track, with Rs. and % variance."),
    ("DRIVERS", "which campaigns/ad sets are responsible for the variance."),
    ("RISK FLAG", "any budget caps at risk of being hit or missed today."),
    ("RECOMMENDED ACTION", "budget reallocation or bid adjustment, ranked by Rs. impact."),
]))

_register(_spec(ReportType.wasted_spend_alert, "Wasted Spend Alert", "alert",
    "Surface spend with zero / near-zero return this period.", [
    ("HEADLINE", "one sentence on total Rs. spent with zero or near-zero return this period."),
    ("METRICS BLOCK", "Spend, Conversions, CPA, ROAS for the flagged entities — this period vs prior period."),
    ("WASTE BREAKDOWN", "campaigns/ad sets/ads with spend but no conversions, or CPA far above breakeven."),
    ("ROOT CAUSE", "targeting mismatch, broken creative/link, audience saturation, or tracking issue."),
    ("TOP 3 WASTE SOURCES", "ranked by Rs. wasted."),
    ("RECOMMENDED ACTION", "pause/reallocate, ranked by Rs. recoverable."),
]))

_register(_spec(ReportType.cod_rto_weekly, "COD & RTO Weekly", "weekly",
    "Weekly cash-on-delivery confirmation and return-to-origin health.", [
    ("HEADLINE", "one sentence on this week's COD confirmation rate and RTO trend."),
    ("METRICS BLOCK", "COD Orders, Confirmation Rate, RTO Rate, RTO Cost (Rs.), Net Delivered Revenue — this week vs last week."),
    ("WHAT WORKED", "regions/products/campaigns with low RTO, with data."),
    ("WHAT UNDERPERFORMED", "regions/products/campaigns with high RTO, with root cause."),
    ("RISK FLAG", "any campaign driving orders with abnormally high RTO risk."),
    ("TOP 3 ACTIONS", "ranked by Rs. impact (e.g. geo-exclusion, COD verification steps)."),
]))

_register(_spec(ReportType.creative_health_weekly, "Creative Health Weekly", "weekly",
    "Weekly portfolio-wide creative health check.", [
    ("HEADLINE", "one sentence on overall creative portfolio health this week."),
    ("METRICS BLOCK", "CTR, Frequency, CPM, Thumb-stop rate (if available) — this week vs last week, per top creative."),
    ("CREATIVE STATUS", "tag every active ad as Healthy / Warning / Critical."),
    ("WHAT WORKED", "top 2-3 creatives still performing, with data."),
    ("WHAT UNDERPERFORMED", "top 2-3 creatives fatiguing or underperforming, with root cause."),
    ("TOP 3 ACTIONS", "ranked by Rs. impact (refresh, rotate, kill)."),
]))

_register(_spec(ReportType.money_flow_weekly, "Money Flow Weekly", "weekly",
    "Weekly reconciliation of ad spend against cash that actually reached the store.", [
    ("HEADLINE", "one sentence, Rs. spent vs Rs. actually reaching the store net this week."),
    ("METRICS BLOCK", "Net Revenue, Total Ad Spend, Total Ad Cost, Gross Sales, Dashboard-Claimed ROAS, True Retained ROAS — this week vs last week."),
    ("THE GAP", "Rs. and % gap between claimed and retained ROAS this week, with cause."),
    ("WHAT WORKED", "2-3 wins with data."),
    ("WHAT UNDERPERFORMED", "2-3 issues with root cause."),
    ("TOP 3 ACTIONS", "ranked by Rs. impact."),
]))

_register(_spec(ReportType.platform_compare_weekly, "Platform Compare Weekly", "weekly",
    "Compare platforms on true ROAS and suggest budget shifts.", [
    ("HEADLINE", "one sentence on which platform delivered the best true ROAS this week."),
    ("METRICS BLOCK", "per platform: Spend, Conversions, CPA, ROAS, CTR, CPM — this week vs last week."),
    ("WHAT WORKED", "platform/channel combination with the strongest efficiency gain, with data."),
    ("WHAT UNDERPERFORMED", "platform/channel with declining efficiency, with root cause."),
    ("BUDGET SHIFT SIGNAL", "how much budget could shift between platforms and expected Rs. impact."),
    ("TOP 3 ACTIONS", "ranked by Rs. impact."),
]))

_register(_spec(ReportType.weekly_action_plan, "Weekly Action Plan", "weekly",
    "The prioritised action list for next week, ranked by rupee impact.", [
    ("HEADLINE", "one sentence on the single highest-priority action for next week."),
    ("CONTEXT METRICS", "Spend, Conversions, CPA, ROAS — this week vs last week, direction only (brief)."),
    ("TOP 5 ACTIONS", "ranked by Rs. impact, each with what to do, why (data-backed), and expected outcome."),
    ("CREATIVE STATUS", "any ACTIVE ads critical or warning that need action this week."),
    ("RISK WATCH", "anything likely to become a problem next week if untouched."),
    ("OWNER/DEADLINE", "suggested action owner and timing for each of the top 3 actions."),
]))

_register(_spec(ReportType.monthly_customer_quality, "Monthly Customer Quality", "monthly",
    "Month-over-month shift in the quality of acquired customers.", [
    ("HEADLINE", "one sentence on the biggest shift in customer quality this month."),
    ("METRICS BLOCK", "AOV, Repeat Purchase Rate, New vs Returning split, Customer LTV estimate, Return/Refund Rate — this month vs last month, with direction."),
    ("WHAT WORKED", "2-3 channels/campaigns bringing in higher-quality customers, with data."),
    ("WHAT UNDERPERFORMED", "2-3 sources bringing low-quality or high-return customers, with root cause."),
    ("COHORT NOTE", "any notable shift in acquisition channel mix affecting quality."),
    ("TOP 3 ACTIONS", "ranked by Rs. impact on customer lifetime value."),
]))

_register(_spec(ReportType.monthly_money_flow, "Monthly Money Flow Report", "monthly",
    "Monthly platform-reported ROAS vs actual retained ROAS.", [
    ("HEADLINE", "one sentence contrasting platform-reported ROAS vs actual retained ROAS."),
    ("METRICS BLOCK", "Gross Sales, Net Revenue (after discounts/returns), Total Ad Spend, Total Ad Cost (incl. tax), Platform-Claimed ROAS, True Retained ROAS — this month vs last month."),
    ("THE GAP", "Rs. and % difference between dashboard-claimed and real retained ROAS, explained (returns, COD failures, discounts, attribution overlap)."),
    ("WHAT WORKED", "2-3 campaigns with the smallest claim-vs-real gap."),
    ("WHAT UNDERPERFORMED", "2-3 campaigns with the largest gap, with root cause."),
    ("TOP 3 ACTIONS", "ranked by Rs. impact on closing the gap."),
]))

_register(_spec(ReportType.monthly_performance, "Monthly Performance Report", "monthly",
    "Monthly account performance summary.", [
    ("HEADLINE", "one sentence, the biggest change this month."),
    ("METRICS BLOCK", "Spend, Conversions, CPA, ROAS, CTR, CPM — this month vs last month, with direction."),
    ("WHAT WORKED", "top 2-3 wins with data."),
    ("WHAT UNDERPERFORMED", "top 2-3 issues with root cause."),
    ("CREATIVE STATUS", "any active ads flagged critical or warning."),
    ("TOP 3 ACTIONS", "ranked by Rs. impact. If commerce connected, add one line on the month's retained ROAS vs reported."),
]))

_register(_spec(ReportType.monthly_product_pl, "Monthly Product P&L", "monthly",
    "Per-product profit and loss for the month.", [
    ("HEADLINE", "one sentence on the most and least profitable product this month."),
    ("METRICS BLOCK", "per top product/SKU: Revenue, Ad Spend Allocated, COGS (if available), Returns/RTO Cost, Net Margin — this month vs last month."),
    ("WHAT WORKED", "2-3 products with improving margin, with data."),
    ("WHAT UNDERPERFORMED", "2-3 products with shrinking or negative margin, with root cause."),
    ("INVENTORY/PRICING FLAG", "any product where ad spend is outpacing margin."),
    ("TOP 3 ACTIONS", "ranked by Rs. impact on overall profit."),
]))

# ===================== Batch 2: exact prompts from the screenshots =====================

_register(_spec(ReportType.true_roas_money_flow, "True ROAS / Money Flow Report", "monthly",
    "Flagship money-flow report: ad spend vs cash actually reaching the store, with the dashboard-vs-real ROAS gap.", [
    ("HEADLINE", "one sentence — 'You spent Rs.[X] on ads. Rs.[Y] net revenue reached your store (net).'"),
    ("UTM COVERAGE CHECK", "state what % of orders have valid UTM tags; if below 60%, flag that campaign-level ROAS is directional only."),
    ("THE ROAS REALITY", "three numbers — Dashboard-Claimed ROAS, GST-Corrected ROAS, True Store ROAS — each labeled with what it means."),
    ("THE MONEY STORY", "Net Revenue (Shopify, after discounts/returns), Total Ad Spend (platform, excl. GST), Total Ad Cost (incl. GST), Gross Sales."),
    ("GAP CALLOUT", "Rs. and % gap between dashboard-claimed ROAS and true retained ROAS, one sentence on the cause (returns, GST, unattributed orders)."),
    ("MONEY IN — ORDER REALITY TABLE", "Total Orders, Successfully Fulfilled, Partially Fulfilled/Pending, with amount and % of gross for each."),
]))

_register(_spec(ReportType.campaign_attribution, "Full Campaign x Order Attribution Report", "weekly",
    "How reliably campaign-level spend maps to real orders via UTM; flags tracking breaks and cancellation risk.", [
    ("HEADLINE", "title with account(s) covered, period, and total orders scanned."),
    ("UTM COVERAGE WARNING", "% coverage and whether it's below the reliability threshold."),
    ("UTM/TRACKING BREAK ALERT", "flag any detected tracking break (e.g. dynamic parameters not resolved, broken URL template) that could hide attribution."),
    ("CORE METRICS", "Total Platform Spend, Orders Cancelled (count and % of scanned), Cancelled Revenue at Risk (Rs.), COD Cancel Rate, UTM Coverage %."),
    ("CAMPAIGN/ADSET/AD BREAKDOWN", "performance and order attribution at each level, flagged by data confidence."),
    ("RECOMMENDED FIX", "top action to repair attribution or reduce cancellation risk, ranked by Rs. impact."),
]))

_register(_spec(ReportType.product_pl, "Product P&L Report", "monthly",
    "Per-product profit and loss with attribution-method disclosure and dual ROAS view.", [
    ("HEADLINE", "period, order count, and accounts/platforms included."),
    ("ATTRIBUTION METHOD DISCLOSURE", "state whether attribution is blended/account-level vs UTM-matched, and the % UTM coverage; flag if product-level costs are proportional estimates rather than true matches."),
    ("MONEY-IN BLOCK", "Gross Revenue, Net Revenue (post-returns), Net Revenue Ex-GST, Total Ad Spend (incl. GST)."),
    ("ROAS DUAL VIEW", "Reported ROAS (platform-claimed avg) vs True ROAS (net revenue ex-GST / spend), plus Rs. lost to reversals this period and as % of gross."),
    ("PER-PRODUCT TABLE", "Revenue, Ad Cost Allocated, Net Margin per top SKU/product."),
    ("PRIORITY ACTION", "the single most urgent tracking or margin fix, ranked by Rs. impact."),
]))

_register(_spec(ReportType.account_audit, "Full Account Audit Report", "monthly",
    "Whole-account health score with sub-scores and the critical issues dragging it down.", [
    ("HEADLINE", "Overall Health Score out of 100, with a one-word status (Healthy/Amber/At Risk/Critical) and one sentence on the primary driver."),
    ("SUBSCORES", "each out of 25 — Spend Efficiency, Creative Health, Performance Trend, Account Structure — one line of justification per subscore."),
    ("ACCOUNT SUMMARY METRICS", "Total Spend, Total Purchases, Best ROAS campaign, Worst ROAS campaign, Active Campaigns count, Avg Account ROAS."),
    ("CRITICAL ALERTS", "list any campaign/ad set/creative in a catastrophic or exhausted state, each with the specific data point (ROAS, frequency, wasted Rs.) that triggered the alert."),
    ("STRUCTURAL ISSUES", "anything wrong with account/campaign structure (budget split, audience overlap, naming/tracking gaps)."),
    ("TOP 3 ACTIONS", "ranked by Rs. impact to restore health score."),
]))

_register(_spec(ReportType.meta_ads_kill_strategy, "Meta Ads Kill Rule Strategy", "weekly",
    "Rule-based kill/scale/monitor decisions across campaigns, ad sets and ads.", [
    ("HEADLINE", "accounts covered, ads analyzed, estimated monthly waste identified."),
    ("ACTION KEY", "legend — define Kill Now / Pause / Monitor / Scale / Hold with the exact rule/threshold for each."),
    ("BUCKET COUNTS", "number of ads to Kill/Pause immediately, number to Scale, number to Monitor, number with no ROAS data (traffic/awareness)."),
    ("MASTER KILL RULES — CAMPAIGN LEVEL", "explicit pause conditions (e.g. 'Pause entire campaign when: blended ROAS < X for 7+ consecutive days AND no ad set above Y ROAS')."),
    ("AD SET / AD LEVEL RULES", "the same explicit thresholds one level down."),
    ("ESTIMATED IMPACT", "Rs./month recovered if all Kill/Pause recommendations are executed by [date]."),
]))

_register(_spec(ReportType.ad_strategy, "Meta Ads Strategy Review & Recommendations", "monthly",
    "Forward-looking budget and campaign playbook: review, allocation, and corrections.", [
    ("HEADLINE", "proposed budget for the upcoming period, split by account/objective, and a one-sentence strategy verdict (Sound / Mostly Sound / Needs Correction)."),
    ("REVIEW PERIOD & TARGETS", "date range reviewed, net sales target, required net ROAS to hit target."),
    ("BUDGET ALLOCATION", "Rs. and % split across platforms/campaign types with the rationale for the split."),
    ("WHAT'S WORKING", "hero campaign/ad set found, with its ROAS/CPA and why it should scale."),
    ("WHAT'S WRONG", "the biggest strategic mistake identified (e.g. budget misallocation, missing high performer from scaling plan), with data."),
    ("CORRECTIONS", "ranked list of specific changes with expected ROAS/Rs. improvement if adopted."),
]))

_register(_spec(ReportType.campaign_revamp, "Campaign Revamp / Blueprint Strategy", "adhoc",
    "Blueprint to rebuild an underperforming campaign: diagnostics, new structure, creative plan, projection.", [
    ("HEADLINE", "what's being revamped, current CPA vs target CPA, current ROAS vs target ROAS."),
    ("OLD CAMPAIGN DIAGNOSTICS", "Total Spend, Cost Per Purchase, Reported ROAS, Purchases, Ad Creatives Tested — for the campaign being replaced."),
    ("WHY IT FAILED", "one-sentence root cause (e.g. 'CPA is X% above target, ROAS Y% below target')."),
    ("NEW STRUCTURE", "proposed campaign/ad set/creative structure with target CPA and ROAS."),
    ("CREATIVE PLAN", "how many new creatives, formats, and refresh cadence."),
    ("EXPECTED OUTCOME", "projected Rs./ROAS improvement vs the old structure."),
]))

_register(_spec(ReportType.meta_ads_performance, "Meta Ads Performance Report", "dashboard",
    "Dashboard-style Meta Ads performance snapshot with fatigue/strength flags.", [
    ("HEADLINE", "account(s) covered and period selector (Today / Yesterday / Last 7 Days / Last 14 Days / This Month)."),
    ("METRICS BLOCK", "Total Ad Spend, Purchase Revenue, ROAS, Purchases, Frequency, CPM, Outbound CTR, Landing Page Views — each with account-level breakdown if multiple ad accounts."),
    ("FATIGUE FLAG", "call out if Frequency is in a 'High Fatigue' band."),
    ("STRENGTH FLAG", "call out any metric performing 'Strong' vs benchmark."),
    ("WHAT WORKED / WHAT UNDERPERFORMED", "2-3 items each with data."),
    ("TOP ACTIONS", "ranked by Rs. impact."),
]))


def get_spec(report_type: ReportType) -> ReportSpec:
    """Return the spec for a report type, or raise if it has no AI spec."""
    try:
        return SPECS[report_type]
    except KeyError as exc:  # pragma: no cover
        raise KeyError(
            f"No report spec registered for '{report_type.value}'. "
            f"Registered: {sorted(k.value for k in SPECS)}"
        ) from exc


def has_spec(report_type: ReportType) -> bool:
    return report_type in SPECS
