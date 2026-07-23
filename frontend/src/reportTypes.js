// Report types the Insights page can generate, grouped for the picker.
// These match the backend spec registry (31 reports).
export const REPORT_GROUPS = [
  { group: 'Commerce / Money', items: [
    { type: 'money_flow_report', label: 'Money Flow Report' },
    { type: 'product_pl', label: 'Product P&L' },
    { type: 'reality_check', label: 'Dashboard vs Reality Check' },
    { type: 'cod_prepaid', label: 'COD vs Prepaid Analysis' },
    { type: 'customer_quality', label: 'Customer Quality & LTV' },
  ]},
  { group: 'Account & Performance', items: [
    { type: 'account_audit', label: 'Full Account Audit' },
    { type: 'weekly_performance', label: 'Weekly Performance Report' },
    { type: 'cpa_diagnosis', label: 'CPA Increase Diagnosis' },
    { type: 'day_of_week', label: 'Day-of-Week Performance' },
  ]},
  { group: 'Spend & Budget', items: [
    { type: 'wasted_spend', label: 'Wasted Spend Analysis' },
    { type: 'budget_reallocation', label: 'Budget Reallocation Plan' },
    { type: 'scaling_opportunities', label: 'Scaling Opportunities' },
    { type: 'diminishing_returns', label: 'Diminishing Returns' },
  ]},
  { group: 'Creative', items: [
    { type: 'creative_fatigue', label: 'Creative Fatigue Analysis' },
    { type: 'ad_ranking', label: 'Ad Ranking (Top & Bottom)' },
    { type: 'messaging_angles', label: 'Messaging Angle Analysis' },
    { type: 'creative_briefs', label: 'Creative Briefs' },
  ]},
  { group: 'Audience & Targeting', items: [
    { type: 'audience_analysis', label: 'Audience Analysis' },
    { type: 'demographic_breakdown', label: 'Demographic Breakdown' },
    { type: 'retargeting_audit', label: 'Retargeting Audit' },
    { type: 'geographic_performance', label: 'Geographic Performance' },
    { type: 'advantage_plus_readiness', label: 'Advantage+ Readiness' },
    { type: 'placement_analysis', label: 'Placement Analysis' },
  ]},
  { group: 'Google', items: [
    { type: 'search_terms_audit', label: 'Search Terms Audit' },
    { type: 'shopping_pmax_products', label: 'Shopping & PMax Products' },
    { type: 'impression_share', label: 'Impression Share Analysis' },
    { type: 'keyword_opportunities', label: 'Keyword Opportunities' },
  ]},
  { group: 'Cross-Platform & Planning', items: [
    { type: 'weekly_action_plan', label: 'Weekly Action Plan' },
    { type: 'platform_comparison', label: 'Platform Comparison' },
    { type: 'cross_platform_budget', label: 'Cross-Platform Budget' },
    { type: 'funnel_mapping', label: 'Funnel Mapping' },
  ]},
]

// Reports that produce a full report from currently-connected data (Shopify).
export const READY = new Set([
  'money_flow_report', 'product_pl', 'reality_check', 'cod_prepaid', 'customer_quality',
])
