import React from 'react'
import ReportVisuals from './ReportVisuals'
import { parseReport } from './mdReport'

function inr(n) {
  if (n === null || n === undefined) return 'Not connected'
  let x = Math.round(Number(n)); const neg = x < 0; x = Math.abs(x)
  let s = String(x)
  if (s.length > 3) {
    const last3 = s.slice(-3); let rest = s.slice(0, -3); const parts = []
    while (rest.length > 2) { parts.unshift(rest.slice(-2)); rest = rest.slice(0, -2) }
    if (rest) parts.unshift(rest)
    s = parts.join(',') + ',' + last3
  }
  return (neg ? '-' : '') + 'Rs.' + s
}

function Metric({ color, label, val, sub }) {
  return (
    <div className={'mf-metric ' + color}>
      <div className="mf-metric-label">{label}</div>
      <div className="mf-metric-val">{val}</div>
      <div className="mf-metric-sub">{sub}</div>
    </div>
  )
}

function MoneyPanels({ story }) {
  const rows = story.money_in || []
  const out = story.money_out || {}
  return (
    <>
      <div className="scard mf-panel">
        <div className="mf-panel-head green">💰 Money In — Shopify Order Health</div>
        <table>
          <thead><tr><th>Category</th><th>Orders</th><th>Amount</th><th>% of Gross</th></tr></thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i} className={r.category.startsWith('Collected') || r.category.startsWith('Total') ? '' : 'muted'}>
                <td>{r.category}</td>
                <td>{r.orders == null ? '—' : r.orders}</td>
                <td>{inr(r.amount)}</td>
                <td>{r.pct_of_gross}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="scard mf-panel">
        <div className="mf-panel-head red">💸 Money Out — Ad Cost Breakdown</div>
        <table>
          <tbody>
            <tr><td>Ad spend (reported)</td><td>{inr(out.ad_spend_reported)}</td></tr>
            <tr><td>GST on ad spend (18%)</td><td>{inr(out.gst_on_ad_spend)}</td></tr>
            <tr className="total"><td>Total actual ad cost (incl. GST)</td><td>{inr(out.total_actual_ad_cost)}</td></tr>
          </tbody>
        </table>
      </div>
    </>
  )
}

// Sections shown structurally above — don't repeat them as prose.
const SKIP = new Set(['THE MONEY STORY', 'ORDER HEALTH'])

export default function MoneyFlowReport({ report }) {
  const f = report.facts || {}
  const hero = f.hero || {}
  const m = f.headline_metrics || {}
  const story = f.the_money_story
  const parsed = parseReport(report.narrative_md)
  const gap = hero.reported_roas != null

  return (
    <div className="report-view mf">
      <div className="mf-hero">
        <div className="mf-brand">{report.title}</div>
        <div className="mf-headline">{hero.headline || report.title}</div>
        <div className="mf-meta">{report.period}</div>
        {gap && (
          <div className="mf-gap-pill">
            ⚠ Dashboard ROAS {hero.reported_roas}x → Real retained ROAS {hero.true_roas}x
            {hero.gap_amount != null && <> · {inr(hero.gap_amount)} gap between ad claims and Shopify net</>}
          </div>
        )}
      </div>

      <div className="seclabel">Part A — The Money Story</div>
      <div className="mf-metrics">
        <Metric color="green" label="Net Revenue (Shopify)" val={inr(m.net_revenue)} sub="After discounts + reversals" />
        <Metric color="purple" label="Total Ad Spend" val={inr(m.total_ad_spend)} sub="excl. GST" />
        <Metric color="red" label="Total Ad Cost (incl. GST)" val={inr(m.total_ad_cost)} sub="Spend × 1.18" />
        <Metric color="amber" label="Gross Sales" val={inr(m.gross_sales)} sub="Before reversals & discounts" />
      </div>

      {story && <MoneyPanels story={story} />}

      <ReportVisuals facts={f} />

      {parsed.sections
        .filter((sec) => !SKIP.has(sec.name.toUpperCase()))
        .map((sec, i) => (
          <div key={i}>
            <div className="seclabel">{sec.name}</div>
            <div className="scard narrative" dangerouslySetInnerHTML={{ __html: sec.html }} />
          </div>
        ))}
    </div>
  )
}
