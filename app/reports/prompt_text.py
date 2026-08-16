"""Verbatim report prompts (as supplied in the source document).

These are the exact instructions each report is generated from. specs.py pairs
each with a canonical list of H2 headings and the shared guardrails; the narrator
feeds this verbatim text to the model so output matches the source prompts.
"""
from __future__ import annotations

from app.models import ReportType

PROMPTS: dict[ReportType, str] = {
    ReportType.account_audit: """Analyze this ad account and produce a structured audit report.
STEP 1: ASSESS DATA VOLUME
30+ days, 5+ campaigns, 10+ ads: FULL AUDIT.
7-30 days or fewer: LIMITED. State the limitation.
Under 7 days: TOO EARLY. Give benchmarks plus a checklist.
STEP 2: HEALTH SCORE
If commerce NOT connected: 4 dimensions x 25 points.
If commerce connected: 5 dimensions x 20 points.
SPEND EFFICIENCY: Wasted % = (0-conv ACTIVE ad spend, 14d) / total.
0-5%=full | 5-10%=80% | 10-20%=60% | 20-35%=32% | 35%+=8%.
CREATIVE HEALTH: Fatigued = freq >3.0 AND CTR declining >10%.
0 fatigued=full | 1-2=72% | 3-5=48% | 5+=20%.
PERFORMANCE TREND: 7d vs prev 7d primary KPI.
Improving >10%=full | Stable=72% | Declining 10-25%=40% | 25%+=12%.
STRUCTURE: award for Advantage+, consolidation, both platforms,
budget on winners, mixed formats. Penalize fragmentation, single format.
RETAINED REVENUE HEALTH (commerce only): gap between reported and
retained ROAS after GST, cancellations, returns, RTO.
Gap <10%=full | 10-25%=60% | 25-40%=30% | >40%=10%.
SECTIONS: 1. Score and one-line verdict 2. Spend overview
3. Wasted spend 4. Creative health 5. Top 3 and bottom 3
6. Retained revenue gap (commerce only) 7. Priority actions ranked by Rs. impact.""",

    ReportType.weekly_performance: """Generate a weekly performance report.
1. HEADLINE: one sentence, the biggest change.
2. METRICS BLOCK: Spend, Conversions, CPA, ROAS, CTR, CPM,
each with this week, last week, and direction.
3. WHAT WORKED: top 2-3 wins with data.
4. WHAT UNDERPERFORMED: top 2-3 issues with root cause.
5. CREATIVE STATUS: any ACTIVE ads critical or warning?
6. TOP 3 ACTIONS ranked by Rs. impact.
If commerce connected: add one line on the week's retained ROAS vs reported.""",

    ReportType.cpa_diagnosis: """My CPA has increased. Diagnose why. Compare last 7d vs prev 7d:
1. Campaign-level CPA changes
2. Creative fatigue (frequency, CTR on ACTIVE ads)
3. Audience saturation (reach declining, frequency rising)
4. CPM inflation (competitive or seasonal pressure)
5. Conversion rate changes (clicks stable, conversions dropped)
6. Budget changes (spend up without results)
Show each hypothesis with evidence for, evidence against, and probability.
Then: most likely cause, immediate fix, structural fix, what to monitor.""",

    ReportType.wasted_spend: """Identify all wasted spend. Read business_category for conversion type.
TIER 1 WASTE (always): ACTIVE AND (spent >Rs.500 in 14d AND zero conv
OR spent >3x avg CPA with only 1 conv).
Traffic or awareness objective: only if CTR <0.5% AND spend >Rs.1,000.
TIER 2 WASTE (commerce connected, UTM >=60%): CONVERTING BUT NOT RETAINING.
ACTIVE ads where realized revenue after GST, cancellations, returns and RTO
is below ad cost, even though platform shows conversions.
Flag each with reported ROAS and retained ROAS side by side.
Headline: 'Rs.[total] wasted across [N] ACTIVE ads (X% of spend).'
If Tier 2 present: 'Rs.[X] more looks profitable but is not retaining.'
List each ad with platform, 14d spend, conversions, days active,
and retained ROAS where available.
Monthly projection. WHY analysis. Reallocation to the best retained-ROAS campaign.
No waste? Flag borderline. All waste? Diagnose root cause.""",

    ReportType.budget_reallocation: """Create a budget reallocation plan for ACTIVE campaigns.
Classify each: SCALE | MAINTAIN | REDUCE | PAUSE.
If commerce connected and UTM >=60%: classify on RETAINED ROAS.
Show campaign, platform, current budget, reported ROAS, retained ROAS,
classification, and new budget.
1. Budget flow with Rs. amounts.
2. Expected blended retained ROAS improvement.
3. Gradual implementation over 5 days.
4. Warning signals to watch.
5. Should the Meta to Google split change?""",

    ReportType.scaling_opportunities: """Analyze budget allocation and scaling opportunities.
1. BUDGET-LIMITED WINNERS: above-average results, hitting caps.
2. OVERSPENDING UNDERPERFORMERS: high budget, poor results.
3. LEARNING PHASE: stuck campaigns (need ~50 conv/week).
4. SCALING HEADROOM: room to grow without saturation?
Give a scale table and a pull-back table with Rs. amounts.
Reallocation plan. Scaling guardrails.
If commerce connected: note any winner whose retained ROAS does not justify scaling.""",

    ReportType.diminishing_returns: """Analyze ACTIVE campaigns for diminishing returns.
For each spending over Rs.500/day:
1. Is ROAS trending worse as spend increased over 30d?
2. Frequency over 3.0 or impression share stagnating?
3. Is incremental conversion cost increasing?
Classify: ROOM TO GROW | APPROACHING CEILING | PAST CEILING.
Show campaign, platform, spend, ROAS trend, frequency or IS, status.
Past ceiling: give optimal budget. Room to grow: give capacity estimate.""",

    ReportType.day_of_week: """Analyze performance by day of week for the last 30 days.
Show day, spend, conversions, CPA, ROAS, CTR, and a best or worst flag.
Identify best and worst days, and any day with CPA over 25% above average.
Weekend versus weekday. Peak hours if hourly data is available.
Recommendations: scheduling, pacing, bid adjustments.""",

    ReportType.creative_fatigue: """Analyze all ACTIVE ads for creative fatigue.
CRITICAL: freq >4.5 OR (freq >3.0 AND CTR dropped >20%).
WARNING: freq 3.0-4.5 AND CTR dropped 10-20%.
HEALTHY: freq <2.5 AND CTR stable or improving.
Google: use CTR trend and ad age (no frequency).
Summary: '[X] of [total] ACTIVE ads need attention.'
Show ad, platform, frequency, CTR 7d, CPM 7d, days running, status,
and retained ROAS where commerce is connected.
Distinct angles present. Missing angles. Cost of inaction.
Mark fatiguing ads with strong retained ROAS as replace-first.""",

    ReportType.ad_ranking: """Rank all ACTIVE ads by primary KPI.
If commerce connected and UTM >=60%: rank by retained ROAS,
show platform ROAS rank beside it, and flag any ad where the two disagree.
Show ad, campaign, format, spend, conversions, KPI, CTR,
and retained ROAS where available.
TOP 3: format, angle, hook, common elements.
BOTTOM 3 (excluding pure waste): diagnosis.
Creative mix: distinct angles, format balance.""",

    ReportType.messaging_angles: """Categorize all ACTIVE ads by messaging angle.
Angles: Discount, Product feature, Problem-solution, Social proof,
Lifestyle, Urgency, Educational, Brand story, Comparison.
Show angle, number of ads, percent of budget, avg ROAS, avg CTR, verdict,
and avg retained ROAS where commerce is connected.
Best angle, overspending angle, missing angles, industry recommendations.
Call out any angle where reported and retained ROAS diverge sharply.""",

    ReportType.creative_briefs: """Generate 3 creative briefs from performance data.
First: what works (top 3), what is missing, what is fatiguing.
Each brief: angle name and why, target audience, 2-3 hook options,
key message in brand voice, CTA, format and why, visual direction,
and a reference to an existing ad.
Give priority order and budget guidance.
If commerce connected: bias briefs toward angles that retain, not just convert.""",

    ReportType.audience_analysis: """Analyze by audience type: Broad or Advantage+, Interest, Lookalike, Retargeting.
Show audience, number of ad sets, spend, conversions, CPA, ROAS, frequency, CTR.
Best CPA and ROAS, disproportionate budget, retargeting share (15-25% healthy),
saturation signals, Andromeda consolidation opportunity.""",

    ReportType.demographic_breakdown: """Break down by demographics.
AGE: spend, conversions, CPA, ROAS. Flag any segment over 30% above avg CPA.
GENDER: spend, conversions, CPA, ROAS.
TOP 5 LOCATIONS: city, spend, conversions, CPA, ROAS, tier.
Best and worst combinations. Geo opportunities versus waste. Tier comparison.""",

    ReportType.retargeting_audit: """Audit retargeting setup.
Show audience, size, spend, conversions, CPA, ROAS, frequency.
Percent of total (15-25% healthy). Frequency too high (>5)?
Funnel coverage and gaps. Lookback windows.
Google: remarketing, RLSA, customer match.""",

    ReportType.geographic_performance: """Geographic performance for ACTIVE campaigns.
Top 15: city, platform, spend, conversions, CPA, ROAS, tier.
Tier 1 vs 2 vs 3. High spend with poor results (reduce).
Low spend with great results (increase). Worth separating by tier?
If commerce connected: cross-reference RTO rate by city from Action 31 data.""",

    ReportType.advantage_plus_readiness: """Assess for Advantage+ readiness. Check:
1. Consolidation (2-3 campaigns per objective) 2. Creative diversity (5+)
3. Audience (narrow vs broad) 4. Ad volume (5-10 per campaign)
5. Budget (~50 conv/week) 6. CAPI.
Score each Ready, Needs Work, or Not Started. Give a migration plan.""",

    ReportType.placement_analysis: """Analyze by placement.
Show placement, spend, percent of budget, conversions, CPA, ROAS, CTR, CPM.
Most efficient, most expensive, zero-conversion placements,
Reels utilization, Audience Network exclusion?""",

    ReportType.search_terms_audit: """Audit search terms for the last 30 days.
1. WINNERS: 2+ conversions, CPA below average. Top 10.
2. WASTERS: over Rs.500 spend, zero conversions.
3. OPPORTUNITIES: CTR over 3%, no keyword yet.
4. IRRELEVANT: unrelated terms.
Give a negative keyword list, new keyword suggestions, estimated savings.""",

    ReportType.shopping_pmax_products: """Analyze Shopping and PMax products. Top 20:
product, spend, clicks, conversions, ROAS, CPC, impression share.
TOP (scale), UNDERPERFORMER (review), MISSING (feed issue?).
Feed quality: titles, attributes. Title suggestions.""",

    ReportType.impression_share: """Analyze impression share for ACTIVE campaigns.
Show campaign, type, IS, lost to budget, lost to rank, top-of-page rate, CPC.
Over 15% lost to budget: scaling opportunity.
Over 15% lost to rank: quality or bid issue.
Brand vs non-brand. Estimated additional conversions at 80% IS.""",

    ReportType.keyword_opportunities: """Identify new keyword opportunities.
1. CLOSE VARIANTS: keyword, searches, competition, CPC.
2. LONG-TAIL: more specific, lower CPC.
3. CATEGORY GAPS: products sold with no keywords.
4. COMPETITOR: from brand guide.
For each: match type, CPC, priority, which campaign.""",

    ReportType.weekly_action_plan: """Create a prioritized weekly action plan.
Headline: 'This week's priority: [theme].'
5-7 actions, each one line: action then arrow then impact, 2-3 sentences each.
If commerce connected: lead with the biggest retained-revenue leak.
IMMEDIATE: pause wasted or fatigued, fix tracking, add negatives.
THIS WEEK: new creatives, budget winners, rebalance, Advantage+.
STRATEGIC: diversify, test features, review landing pages.
Industry calibration: E-commerce=creative plus scaling. B2B=CPL plus quality.
New account=structure plus tracking. Low budget=efficiency only.""",

    ReportType.platform_comparison: """Compare across connected platforms.
If only one connected: analyze it and suggest connecting the other.
Show metric, Meta, Google, which is better, and the difference,
for spend, primary KPI, CPA, CTR, CPM or CPC, conversions.
Key insight. Budget recommendation with Rs./day,
or 'Current split is well-aligned.'""",

    ReportType.cross_platform_budget: """Recommend optimal budget allocation.
Show metric, Meta, Google, total.
Which has better marginal returns? Diminishing on one?
Platform roles. Attribution overlap.
Current vs recommended. Implementation. Monitoring.""",

    ReportType.funnel_mapping: """Map the full funnel across platforms.
TOF (reach, views), MOF (traffic, retargeting), BOF (conversions, search).
Show stage, campaigns, platform, spend, percent of budget, conversions, CPA, ROAS.
Balanced? Is TOF feeding MOF and BOF? Is BOF efficient? Missing stages?""",

    ReportType.money_flow_report: """Generate a Money Flow Report combining ad data with Shopify orders.
PART A: THE MONEY STORY
Bold headline: 'You spent Rs.X on ads. Rs.X reached your bank.'
MONEY IN:
| | Orders | Amount |
| Total Shopify orders | X | Rs.X |
| Successfully delivered | X | Rs.X |
| Cancelled | X | Rs.X |
| Returned | X | Rs.X |
| RTO (failed COD) | X | Rs.X |
| Revenue that reached you | X | Rs.X |
MONEY OUT:
| | Amount |
| Ad spend (reported) | Rs.X |
| GST on ad spend (18%) | Rs.X |
| Total actual ad cost | Rs.X |
BOTTOM LINE:
'For every Rs.1 spent (incl GST), Rs.X in real revenue reached
your store. Margin before COGS: X%.'
GAP: 'Dashboards report Xx ROAS. Real return is Xx.
That is Rs.X less than dashboard suggests.'
Biggest leak: [GST/returns/RTO/cancellations]. Rs.X/month.
PART B: TECHNICAL DEPTH
GST CORRECTION:
| Metric | Platform | GST-Corrected | Shopify Verified |
| Revenue | Rs.X | Rs.X / 1.18 | Rs.X (fulfilled) |
| Spend | Rs.X | Rs.X x 1.18 | - |
| ROAS | Xx | Xx | Xx (store-level) |
CAMPAIGN-LEVEL:
UTM coverage = (orders with UTM) / total.
60%+: campaign True ROAS from UTM data.
Below 60%: GST-corrected platform ROAS per campaign.
Label: 'Platform-reported, corrected for GST.'
BREAK-EVEN: 'Dashboard Xx = actual break-even.'
ORDER HEALTH:
Fulfillment %, Cancellation %, Return %, RTO %, COD/Prepaid.
If COD >50%: effective COD vs prepaid CPA.
ACTIONS (3-5): highest-impact first. UTM fix as one item.""",

    ReportType.product_pl: """Generate a Product P&L combining store sales with ad spend.
PART A: PRODUCT SCORECARD
Headline: 'X making money. X losing. X selling without ads.'
Top 15 by revenue: product, units sold,
revenue kept (excl GST, returns, RTO), ad cost (incl GST), profit or loss, verdict.
Verdict: Making money (>1.5x), Breaking even, Losing (<1.0x),
Selling without ads (organic).
Best product, worst product, hidden winners.
PART B: TECHNICAL P&L
Attribution: UTM if 60%+, ad name inference, or blended. State the method.
Per product: units, gross revenue, net revenue (excl GST), ad cost (incl GST),
returns, RTO, method, True ROAS, contribution, margin %, status.
Scaling headroom. High-return products killing profit.
Organic sellers: recommend testing ads.""",

    ReportType.reality_check: """Show the gap between dashboards and reality.
PART A: REALITY CHECK
Headline: 'Dashboards say Rs.X. The business made Rs.X.'
WHERE MONEY DISAPPEARS, each with amount and percent of gap:
GST in revenue, GST on ad spend, cancelled, returned, RTO, platform over-counting.
'Biggest leak: [X] at Rs.X/month.'
'When Meta shows Xx, you earn Xx. Break-even: Xx.'
PART B: PLATFORM COMPARISON
Metric, Meta, Google, combined, store-verified real.
Attribution overlap. GST-corrected ROAS per platform.
COD risk: COD %, RTO rate, COD vs prepaid CPA.
Monthly summary: dashboard vs reality for revenue, spend (incl GST), ROAS.
ACTIONS: highest impact, the leak to fix, break-even.""",

    ReportType.cod_prepaid: """Analyze COD versus prepaid performance.
PART A: THE COD COST
Per payment type: orders, revenue, percent of total, RTO rate, effective CPA.
'X% COD. Each failed delivery costs Rs.X.
Effective COD CPA: Rs.X vs prepaid Rs.X.'
PART B: GEOGRAPHIC RTO
Top 10 cities: city, orders, RTO rate, RTO cost, tier. Hotspots over 30% RTO.
Campaign-level COD %: highest-risk campaigns.
PART C: PREPAID SHIFT MATH (v4)
For the highest-RTO campaign, compute the break-even prepaid incentive:
'A Rs.[X] prepaid incentive costs Rs.[X] per converted prepaid order
but saves Rs.[Y] in RTO logistics. Break-even prepaid conversion is [Z]%.'
Then: exclude high-RTO pin codes, prepaid-only Tier 1 campaigns,
landing page prepaid prominence.
If shifted from X% to Y% prepaid: saves Rs.X/month.""",

    ReportType.customer_quality: """Analyze customer acquisition quality from store data.
PART A: CUSTOMER QUALITY
New vs returning: orders, revenue, percent of revenue, average AOV.
'X% new, X% returning. Returning customers spend Xx more.'
Repeat rate at 30, 60, 90 days. Purchases needed to break even.
PART B: ACQUISITION EFFICIENCY
Spend on acquisition vs retargeting. CPA and ROAS for new vs returning.
Balance: over-investing in acquisition?
LTV: 'New customer at Rs.X CPA generates Rs.X over 12 months.
Payback: X months.'
ACTIONS: retention shift, best-LTV campaigns, data needs.""",
}
