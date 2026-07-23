"""Report-type prompt registry.

Each report type maps to a :class:`ReportSpec` encoding its title, cadence, the
shared analyst guardrails (the LLM never does math), and the numbered sections
the report must contain. Single source of truth for the Claude prompt and the
deterministic template fallback in ``app/reports/generator.py``.
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
    "instead of guessing (e.g. 'ad platform not connected', 'UTM tracking not "
    "connected', 'COGS unavailable').\n"
    "(3) All money is Indian Rupees; write amounts as 'Rs. 12,34,567' (Indian "
    "digit grouping) unless the facts specify another currency.\n"
    "(4) 'Retained' / 'net' / 'kept' revenue means cash actually retained after "
    "GST, cancellations, returns and RTO — not orders merely placed.\n"
    "(5) Only ever analyse ACTIVE ads/campaigns when the report says ACTIVE.\n"
    "(6) Lead with the most important, data-supported insight; every "
    "recommended action must be ranked by rupee (Rs.) impact and be concrete.\n"
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
        from app.reports.prompt_text import PROMPTS  # local import avoids a cycle

        headings = [name for name, _ in self.sections]
        lines = [SHARED_RULES, f"\nREPORT: {self.title} ({self.cadence})."]

        verbatim = PROMPTS.get(self.key)
        if verbatim:
            lines.append("\nFollow these EXACT instructions:\n\"\"\"\n" + verbatim + "\n\"\"\"")
        else:
            lines.append(f"PURPOSE: {self.summary}")

        # Guarantee every heading appears, even when data is missing.
        lines.append(
            "\nOUTPUT: GitHub-flavoured Markdown. You MUST include EVERY one of these H2 (##) "
            "headings, in this exact order, and NEVER omit a heading. Fill each from the facts; "
            "if a heading's data is not in the facts, keep the heading and write one short line "
            "under it such as 'Not available — [required source, e.g. Meta Ads / Google Ads / "
            "UTM tracking] not connected.' Headings, in order:"
        )
        for i, name in enumerate(headings, start=1):
            lines.append(f"## {name}")
        return "\n".join(lines)


SPECS: dict[ReportType, ReportSpec] = {}


def _spec(key, title, cadence, summary, sections) -> ReportSpec:
    return ReportSpec(key=key, title=title, cadence=cadence, summary=summary, sections=sections)


def _register(spec: ReportSpec) -> None:
    SPECS[spec.key] = spec


# ===================== Account & performance =====================

_register(_spec(ReportType.account_audit, "Full Account Audit", "monthly",
    "Structured ad-account audit with a health score (4x25 without commerce, 5x20 with commerce).", [
    ("DATA VOLUME & SCORE", "state the data tier (30+ days/5+ campaigns/10+ ads = FULL AUDIT; 7-30 days = LIMITED; <7 days = TOO EARLY), then the overall health score out of 100 and a one-line verdict."),
    ("SPEND OVERVIEW", "total spend, campaign count, ad count, and objective type from business_category."),
    ("WASTED SPEND", "wasted % = (0-conversion ACTIVE ad spend over 14d) / total spend, with the Rs. amount."),
    ("CREATIVE HEALTH", "count of fatigued ads (frequency >3.0 AND CTR declining >10%) and the score band."),
    ("TOP 3 & BOTTOM 3", "the three best and three worst performers with data."),
    ("RETAINED REVENUE GAP", "commerce only — gap between reported and retained ROAS after GST, cancellations, returns, RTO; withhold if commerce not connected."),
    ("PRIORITY ACTIONS", "ranked by Rs. impact."),
]))

_register(_spec(ReportType.weekly_performance, "Weekly Performance Report", "weekly",
    "This-week performance snapshot with wins, issues and ranked actions.", [
    ("HEADLINE", "one sentence, the biggest change this week."),
    ("METRICS BLOCK", "Spend, Conversions, CPA, ROAS, CTR, CPM — each with this week, last week, and direction."),
    ("WHAT WORKED", "top 2-3 wins with data."),
    ("WHAT UNDERPERFORMED", "top 2-3 issues with root cause."),
    ("CREATIVE STATUS", "any ACTIVE ads critical or warning."),
    ("TOP 3 ACTIONS", "ranked by Rs. impact. If commerce connected, add one line on the week's retained ROAS vs reported."),
]))

_register(_spec(ReportType.cpa_diagnosis, "CPA Increase Diagnosis", "adhoc",
    "Diagnose why CPA rose, last 7d vs previous 7d, with evidence-weighted hypotheses.", [
    ("HEADLINE", "one sentence on how much CPA rose and over what window."),
    ("HYPOTHESES", "for each of campaign-level CPA change, creative fatigue, audience saturation, CPM inflation, conversion-rate change, and budget change: give evidence for, evidence against, and a probability."),
    ("MOST LIKELY CAUSE", "the single best-supported cause."),
    ("IMMEDIATE FIX", "what to do now."),
    ("STRUCTURAL FIX", "the durable fix."),
    ("WHAT TO MONITOR", "the metrics to watch."),
]))

_register(_spec(ReportType.day_of_week, "Day-of-Week Performance", "monthly",
    "Performance by day of week over the last 30 days.", [
    ("DAY TABLE", "day, spend, conversions, CPA, ROAS, CTR, and a best/worst flag."),
    ("BEST & WORST DAYS", "identify the best and worst days."),
    ("HIGH-CPA DAYS", "any day with CPA more than 25% above average."),
    ("WEEKEND VS WEEKDAY", "compare weekend to weekday, and peak hours if hourly data exists."),
    ("RECOMMENDATIONS", "scheduling, pacing, and bid adjustments."),
]))

# ===================== Spend & budget =====================

_register(_spec(ReportType.wasted_spend, "Wasted Spend Analysis", "weekly",
    "Identify Tier-1 (zero/near-zero return) and Tier-2 (converting but not retaining) wasted spend.", [
    ("HEADLINE", "'Rs.[total] wasted across [N] ACTIVE ads (X% of spend).' If Tier 2 present, add 'Rs.[X] more looks profitable but is not retaining.'"),
    ("TIER 1 WASTE", "ACTIVE ads with spend >Rs.500 in 14d and zero conversions, or spend >3x avg CPA with only 1 conversion. Traffic/awareness objective only if CTR <0.5% AND spend >Rs.1,000."),
    ("TIER 2 WASTE", "commerce + UTM >=60% only — ACTIVE ads where retained revenue (after GST, cancellations, returns, RTO) is below ad cost despite platform conversions; show reported vs retained ROAS side by side."),
    ("WASTE LIST", "each ad with platform, 14d spend, conversions, days active, and retained ROAS where available."),
    ("MONTHLY PROJECTION & WHY", "monthly Rs. projection and root-cause analysis; if no waste, flag borderline."),
    ("REALLOCATION", "move freed budget to the best retained-ROAS campaign."),
]))

_register(_spec(ReportType.budget_reallocation, "Budget Reallocation Plan", "weekly",
    "Reallocate ACTIVE campaign budgets, classifying each Scale/Maintain/Reduce/Pause.", [
    ("CLASSIFICATION TABLE", "campaign, platform, current budget, reported ROAS, retained ROAS, classification (SCALE/MAINTAIN/REDUCE/PAUSE), new budget. Classify on retained ROAS when commerce connected and UTM >=60%."),
    ("BUDGET FLOW", "the flow of Rs. amounts from reduced to scaled campaigns."),
    ("EXPECTED IMPROVEMENT", "expected blended retained-ROAS improvement."),
    ("IMPLEMENTATION", "a gradual rollout over 5 days."),
    ("WARNING SIGNALS", "signals to watch during the change."),
    ("PLATFORM SPLIT", "should the Meta-to-Google split change?"),
]))

_register(_spec(ReportType.scaling_opportunities, "Scaling Opportunities", "weekly",
    "Find budget-limited winners and overspending underperformers; scale and pull-back tables.", [
    ("BUDGET-LIMITED WINNERS", "above-average results that are hitting budget caps."),
    ("OVERSPENDING UNDERPERFORMERS", "high budget, poor results."),
    ("LEARNING PHASE", "campaigns stuck in learning (need ~50 conversions/week)."),
    ("SCALING HEADROOM", "room to grow without saturation."),
    ("SCALE & PULL-BACK TABLES", "a scale table and a pull-back table with Rs. amounts."),
    ("REALLOCATION & GUARDRAILS", "reallocation plan and scaling guardrails; if commerce connected, note any winner whose retained ROAS does not justify scaling."),
]))

_register(_spec(ReportType.diminishing_returns, "Diminishing Returns Analysis", "monthly",
    "Detect diminishing returns on ACTIVE campaigns spending over Rs.500/day.", [
    ("HEADLINE", "one sentence on which campaigns are past their efficient ceiling."),
    ("ROAS VS SPEND TREND", "is ROAS trending worse as spend increased over 30 days?"),
    ("SATURATION SIGNALS", "frequency over 3.0 or impression share stagnating."),
    ("INCREMENTAL COST", "is the incremental conversion cost increasing?"),
    ("CLASSIFICATION TABLE", "campaign, platform, spend, ROAS trend, frequency or IS, status (ROOM TO GROW / APPROACHING CEILING / PAST CEILING)."),
    ("RECOMMENDATIONS", "past ceiling -> optimal budget; room to grow -> capacity estimate."),
]))

# ===================== Creative =====================

_register(_spec(ReportType.creative_fatigue, "Creative Fatigue Analysis", "weekly",
    "Flag ACTIVE ads by fatigue: Critical / Warning / Healthy.", [
    ("SUMMARY", "'[X] of [total] ACTIVE ads need attention.'"),
    ("STATUS TABLE", "ad, platform, frequency, CTR 7d, CPM 7d, days running, status, and retained ROAS where commerce connected. Critical: freq >4.5 OR (freq >3.0 AND CTR dropped >20%). Warning: freq 3.0-4.5 AND CTR dropped 10-20%. Healthy: freq <2.5 AND CTR stable/improving. Google: use CTR trend and ad age (no frequency)."),
    ("ANGLE COVERAGE", "distinct angles present, and missing angles."),
    ("REPLACE-FIRST", "mark fatiguing ads with strong retained ROAS as replace-first."),
    ("COST OF INACTION", "the Rs. cost of leaving fatigued ads running."),
]))

_register(_spec(ReportType.ad_ranking, "Ad Ranking (Top & Bottom)", "weekly",
    "Rank all ACTIVE ads by primary KPI (retained ROAS where possible).", [
    ("RANKING TABLE", "ad, campaign, format, spend, conversions, KPI, CTR, and retained ROAS where available. If commerce + UTM >=60%, rank by retained ROAS with platform ROAS rank beside it and flag any ad where the two disagree."),
    ("TOP 3", "format, angle, hook, common elements."),
    ("BOTTOM 3", "excluding pure waste — diagnosis of what's wrong."),
    ("CREATIVE MIX", "distinct angles and format balance."),
]))

_register(_spec(ReportType.messaging_angles, "Messaging Angle Analysis", "monthly",
    "Categorise ACTIVE ads by messaging angle and compare performance.", [
    ("ANGLE TABLE", "angle (Discount, Product feature, Problem-solution, Social proof, Lifestyle, Urgency, Educational, Brand story, Comparison), number of ads, percent of budget, avg ROAS, avg CTR, verdict, and avg retained ROAS where commerce connected."),
    ("BEST ANGLE", "the best-performing angle."),
    ("OVERSPENDING ANGLE", "the angle taking too much budget for its return."),
    ("MISSING ANGLES", "angles not being used, with industry recommendations."),
    ("DIVERGENCE", "any angle where reported and retained ROAS diverge sharply."),
]))

_register(_spec(ReportType.creative_briefs, "Creative Briefs", "adhoc",
    "Generate 3 creative briefs from performance data.", [
    ("PERFORMANCE SUMMARY", "what works (top 3), what is missing, and what is fatiguing."),
    ("BRIEF 1", "angle name and why, target audience, 2-3 hook options, key message in brand voice, CTA, format and why, visual direction, and a reference to an existing ad."),
    ("BRIEF 2", "same structure as Brief 1 for a distinct angle."),
    ("BRIEF 3", "same structure as Brief 1 for a distinct angle."),
    ("PRIORITY & BUDGET", "priority order and budget guidance; if commerce connected, bias toward angles that retain, not just convert."),
]))

# ===================== Audience & targeting =====================

_register(_spec(ReportType.audience_analysis, "Audience Analysis", "monthly",
    "Analyse performance by audience type.", [
    ("AUDIENCE TABLE", "audience (Broad/Advantage+, Interest, Lookalike, Retargeting), number of ad sets, spend, conversions, CPA, ROAS, frequency, CTR."),
    ("BEST PERFORMERS", "best CPA and best ROAS audiences."),
    ("BUDGET BALANCE", "any audience taking a disproportionate share of budget."),
    ("RETARGETING SHARE", "retargeting share of spend (15-25% is healthy)."),
    ("SATURATION & CONSOLIDATION", "saturation signals and any Andromeda/Advantage+ consolidation opportunity."),
]))

_register(_spec(ReportType.demographic_breakdown, "Demographic Breakdown", "monthly",
    "Break performance down by age, gender and location.", [
    ("AGE", "spend, conversions, CPA, ROAS by age; flag any segment over 30% above average CPA."),
    ("GENDER", "spend, conversions, CPA, ROAS by gender."),
    ("TOP 5 LOCATIONS", "city, spend, conversions, CPA, ROAS, tier."),
    ("BEST & WORST COMBINATIONS", "the best and worst demographic combinations."),
    ("GEO OPPORTUNITIES VS WASTE", "geo opportunities versus waste, and a tier comparison."),
]))

_register(_spec(ReportType.retargeting_audit, "Retargeting Audit", "monthly",
    "Audit the retargeting setup and funnel coverage.", [
    ("AUDIENCE TABLE", "audience, size, spend, conversions, CPA, ROAS, frequency."),
    ("SHARE & FREQUENCY", "percent of total spend (15-25% healthy) and whether frequency is too high (>5)."),
    ("FUNNEL COVERAGE", "funnel coverage and gaps, plus lookback windows."),
    ("GOOGLE", "remarketing, RLSA, customer match coverage."),
]))

_register(_spec(ReportType.geographic_performance, "Geographic Performance", "monthly",
    "Geographic performance for ACTIVE campaigns.", [
    ("TOP 15 CITIES", "city, platform, spend, conversions, CPA, ROAS, tier."),
    ("TIER COMPARISON", "Tier 1 vs 2 vs 3."),
    ("REDUCE", "high spend with poor results."),
    ("INCREASE", "low spend with great results."),
    ("SEPARATE BY TIER?", "whether it's worth separating campaigns by tier; if commerce connected, cross-reference RTO rate by city."),
]))

_register(_spec(ReportType.advantage_plus_readiness, "Advantage+ Readiness", "adhoc",
    "Assess readiness to migrate to Advantage+ / consolidated campaigns.", [
    ("READINESS CHECKLIST", "score each Ready / Needs Work / Not Started: consolidation (2-3 campaigns per objective), creative diversity (5+), audience (narrow vs broad), ad volume (5-10 per campaign), budget (~50 conv/week), and CAPI."),
    ("OVERALL SCORE", "overall readiness verdict."),
    ("MIGRATION PLAN", "a step-by-step migration plan."),
]))

_register(_spec(ReportType.placement_analysis, "Placement Analysis", "monthly",
    "Analyse performance by placement.", [
    ("PLACEMENT TABLE", "placement, spend, percent of budget, conversions, CPA, ROAS, CTR, CPM."),
    ("MOST EFFICIENT", "the most efficient placement."),
    ("MOST EXPENSIVE", "the most expensive placement."),
    ("ZERO-CONVERSION PLACEMENTS", "placements with spend and no conversions."),
    ("REELS & AUDIENCE NETWORK", "Reels utilisation and whether Audience Network should be excluded."),
]))

# ===================== Google-specific =====================

_register(_spec(ReportType.search_terms_audit, "Search Terms Audit", "monthly",
    "Audit search terms for the last 30 days (Google).", [
    ("WINNERS", "terms with 2+ conversions and CPA below average — top 10."),
    ("WASTERS", "terms with over Rs.500 spend and zero conversions."),
    ("OPPORTUNITIES", "terms with CTR over 3% and no keyword yet."),
    ("IRRELEVANT", "unrelated terms."),
    ("RECOMMENDATIONS", "a negative keyword list, new keyword suggestions, and estimated savings."),
]))

_register(_spec(ReportType.shopping_pmax_products, "Shopping & PMax Products", "monthly",
    "Analyse Shopping and Performance Max product performance (Google).", [
    ("TOP 20 PRODUCTS", "product, spend, clicks, conversions, ROAS, CPC, impression share."),
    ("TOP (SCALE)", "top products to scale."),
    ("UNDERPERFORMERS (REVIEW)", "products to review."),
    ("MISSING (FEED ISSUE?)", "products missing — likely feed issues."),
    ("FEED QUALITY", "titles and attributes quality, with title suggestions."),
]))

_register(_spec(ReportType.impression_share, "Impression Share Analysis", "monthly",
    "Analyse impression share for ACTIVE campaigns (Google).", [
    ("IS TABLE", "campaign, type, IS, lost to budget, lost to rank, top-of-page rate, CPC."),
    ("LOST TO BUDGET", "over 15% lost to budget = scaling opportunity."),
    ("LOST TO RANK", "over 15% lost to rank = quality or bid issue."),
    ("BRAND VS NON-BRAND", "brand vs non-brand comparison."),
    ("HEADROOM", "estimated additional conversions at 80% IS."),
]))

_register(_spec(ReportType.keyword_opportunities, "Keyword Opportunities", "monthly",
    "Identify new keyword opportunities (Google).", [
    ("CLOSE VARIANTS", "keyword, searches, competition, CPC."),
    ("LONG-TAIL", "more specific, lower-CPC terms."),
    ("CATEGORY GAPS", "products sold with no keywords."),
    ("COMPETITOR", "competitor terms from the brand guide."),
    ("PRIORITISATION", "for each: match type, CPC, priority, and which campaign."),
]))

# ===================== Cross-platform & planning =====================

_register(_spec(ReportType.weekly_action_plan, "Weekly Action Plan", "weekly",
    "A prioritised weekly action plan, ranked by rupee impact.", [
    ("HEADLINE", "'This week's priority: [theme].' If commerce connected, lead with the biggest retained-revenue leak."),
    ("TOP ACTIONS", "5-7 actions, each one line: action -> impact, 2-3 sentences each, ranked by Rs. impact."),
    ("IMMEDIATE", "pause wasted/fatigued, fix tracking, add negatives."),
    ("THIS WEEK", "new creatives, budget winners, rebalance, Advantage+."),
    ("STRATEGIC", "diversify, test features, review landing pages."),
    ("INDUSTRY CALIBRATION", "E-commerce = creative + scaling; B2B = CPL + quality; new account = structure + tracking; low budget = efficiency only."),
]))

_register(_spec(ReportType.platform_comparison, "Platform Comparison", "weekly",
    "Compare Meta vs Google across connected platforms.", [
    ("COMPARISON TABLE", "metric, Meta, Google, which is better, and the difference — for spend, primary KPI, CPA, CTR, CPM or CPC, conversions. If only one is connected, analyse it and suggest connecting the other."),
    ("KEY INSIGHT", "the single most important takeaway."),
    ("BUDGET RECOMMENDATION", "a budget recommendation with Rs./day, or 'Current split is well-aligned.'"),
]))

_register(_spec(ReportType.cross_platform_budget, "Cross-Platform Budget Allocation", "monthly",
    "Recommend optimal Meta/Google budget allocation.", [
    ("ALLOCATION TABLE", "metric, Meta, Google, total."),
    ("MARGINAL RETURNS", "which platform has better marginal returns; diminishing on either?"),
    ("PLATFORM ROLES", "the role each platform plays, and attribution overlap."),
    ("CURRENT VS RECOMMENDED", "current vs recommended split."),
    ("IMPLEMENTATION & MONITORING", "how to implement and what to monitor."),
]))

_register(_spec(ReportType.funnel_mapping, "Funnel Mapping", "monthly",
    "Map the full funnel across platforms.", [
    ("FUNNEL TABLE", "stage (TOF reach/views, MOF traffic/retargeting, BOF conversions/search), campaigns, platform, spend, percent of budget, conversions, CPA, ROAS."),
    ("BALANCE", "is the funnel balanced?"),
    ("FLOW", "is TOF feeding MOF and BOF?"),
    ("BOF EFFICIENCY", "is BOF efficient?"),
    ("MISSING STAGES", "any missing stages."),
]))

# ===================== Commerce / money =====================

_register(_spec(ReportType.money_flow_report, "Money Flow Report", "monthly",
    "Combine ad data with Shopify orders: what you spent vs what actually reached your bank.", [
    ("THE MONEY STORY", "bold headline 'You spent Rs.X on ads. Rs.X reached your bank.' Then MONEY IN (Total Shopify orders, Successfully delivered, Cancelled, Returned, RTO/failed COD, Revenue that reached you — with orders and Rs.) and MONEY OUT (Ad spend reported, GST 18%, Total actual ad cost)."),
    ("BOTTOM LINE", "'For every Rs.1 spent (incl GST), Rs.X in real revenue reached your store. Margin before COGS: X%.'"),
    ("THE GAP", "'Dashboards report Xx ROAS. Real return is Xx — Rs.X less than the dashboard suggests.' Name the biggest leak (GST/returns/RTO/cancellations) and its Rs./month."),
    ("GST CORRECTION", "table of Revenue, Spend, ROAS across Platform / GST-Corrected / Shopify-Verified."),
    ("CAMPAIGN-LEVEL ROAS", "UTM coverage = orders with UTM / total. 60%+ -> campaign True ROAS from UTM; below 60% -> GST-corrected platform ROAS per campaign, labelled 'Platform-reported, corrected for GST.' State the break-even ('Dashboard Xx = actual break-even')."),
    ("ORDER HEALTH", "Fulfilment %, Cancellation %, Return %, RTO %, COD/Prepaid split; if COD >50% show effective COD vs prepaid CPA."),
    ("ACTIONS", "3-5, highest-impact first, with a UTM fix as one item."),
]))

_register(_spec(ReportType.product_pl, "Product P&L", "monthly",
    "Per-product profit and loss combining store sales with ad spend.", [
    ("PRODUCT SCORECARD", "headline 'X making money. X losing. X selling without ads.' Top 15 by revenue: product, units sold, revenue kept (excl GST/returns/RTO), ad cost (incl GST), profit or loss, verdict (Making money >1.5x, Breaking even, Losing <1.0x, Selling without ads)."),
    ("BEST & WORST", "best product, worst product, and hidden winners."),
    ("PER-PRODUCT P&L", "per product: units, gross revenue, net revenue (excl GST), ad cost (incl GST), returns, RTO, attribution method, True ROAS, contribution, margin %, status."),
    ("ATTRIBUTION METHOD", "state the method used — UTM if 60%+, ad-name inference, or blended."),
    ("SCALING & ORGANIC", "scaling headroom, high-return products killing profit, and organic sellers to test with ads."),
]))

_register(_spec(ReportType.reality_check, "Dashboard vs Reality Check", "monthly",
    "Show the gap between what the dashboards say and what the business actually made.", [
    ("REALITY CHECK", "headline 'Dashboards say Rs.X. The business made Rs.X.' Then where money disappears — GST in revenue, GST on ad spend, cancelled, returned, RTO, platform over-counting — each with amount and % of gap. Name the biggest leak and its Rs./month. State break-even ('When Meta shows Xx, you earn Xx. Break-even: Xx.')."),
    ("PLATFORM COMPARISON", "metric, Meta, Google, combined, store-verified real; attribution overlap; GST-corrected ROAS per platform."),
    ("COD RISK", "COD %, RTO rate, COD vs prepaid CPA."),
    ("MONTHLY SUMMARY", "dashboard vs reality for revenue, spend (incl GST), ROAS."),
    ("ACTIONS", "highest impact first — the leak to fix and the break-even."),
]))

_register(_spec(ReportType.cod_prepaid, "COD vs Prepaid Analysis", "monthly",
    "Cash-on-delivery vs prepaid performance, geographic RTO, and the prepaid-shift math.", [
    ("THE COD COST", "per payment type: orders, revenue, percent of total, RTO rate, effective CPA. 'X% COD. Each failed delivery costs Rs.X. Effective COD CPA: Rs.X vs prepaid Rs.X.'"),
    ("GEOGRAPHIC RTO", "top 10 cities: city, orders, RTO rate, RTO cost, tier; flag hotspots over 30% RTO."),
    ("CAMPAIGN COD RISK", "campaign-level COD % — the highest-risk campaigns."),
    ("PREPAID SHIFT MATH", "for the highest-RTO campaign, compute the break-even prepaid incentive ('A Rs.[X] incentive costs Rs.[X] per prepaid order but saves Rs.[Y] in RTO logistics; break-even prepaid conversion is [Z]%'). Then: exclude high-RTO pin codes, prepaid-only Tier 1 campaigns, landing-page prepaid prominence; and 'if shifted from X% to Y% prepaid: saves Rs.X/month.'"),
    ("ACTIONS", "ranked by Rs. impact."),
]))

_register(_spec(ReportType.customer_quality, "Customer Quality & LTV", "monthly",
    "Customer acquisition quality and lifetime value from store data.", [
    ("CUSTOMER QUALITY", "new vs returning: orders, revenue, percent of revenue, average AOV. 'X% new, X% returning. Returning customers spend Xx more.'"),
    ("REPEAT & RETENTION", "repeat rate at 30, 60, 90 days, and purchases needed to break even."),
    ("ACQUISITION EFFICIENCY", "spend on acquisition vs retargeting; CPA and ROAS for new vs returning; are you over-investing in acquisition?"),
    ("LTV & PAYBACK", "'New customer at Rs.X CPA generates Rs.X over 12 months. Payback: X months.'"),
    ("ACTIONS", "retention shift, best-LTV campaigns, and data needs."),
]))


def get_spec(report_type: ReportType) -> ReportSpec:
    """Return the spec for a report type, or raise if it has no spec."""
    try:
        return SPECS[report_type]
    except KeyError as exc:  # pragma: no cover
        raise KeyError(
            f"No report spec registered for '{report_type.value}'. "
            f"Registered: {sorted(k.value for k in SPECS)}"
        ) from exc


def has_spec(report_type: ReportType) -> bool:
    return report_type in SPECS
