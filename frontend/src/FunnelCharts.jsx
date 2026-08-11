import React from 'react'
import { SERIES_COLORS, fmtFloat, fmtPct } from './funnelFormat'

// Hand-rolled SVG charts — the app ships no charting dependency, and these only
// need to draw a line, a bar and a funnel.

const FUNNEL_STEPS = {
  default: [
    ['item_view_users', 'Item views'],
    ['add_to_cart_users', 'Add to cart'],
    ['begin_checkout_users', 'Checkout'],
    ['purchase_users', 'Purchase'],
  ],
  long: [
    ['item_list_view_users', 'List views'],
    ['item_view_users', 'Item views'],
    ['add_to_cart_users', 'Add to cart'],
    ['view_cart_users', 'View cart'],
    ['begin_checkout_users', 'Checkout'],
    ['add_shipping_users', 'Shipping'],
    ['add_payment_users', 'Payment'],
    ['purchase_users', 'Purchase'],
  ],
  site: [
    ['total_users', 'All users'],
    ['item_view_users', 'Item views'],
    ['add_to_cart_users', 'Add to cart'],
    ['begin_checkout_users', 'Checkout'],
    ['add_shipping_users', 'Shipping'],
    ['add_payment_users', 'Payment'],
    ['purchase_users', 'Purchase'],
  ],
  checkout: [
    ['begin_checkout_users', 'Checkout started'],
    ['add_shipping_users', 'Shipping info'],
    ['add_payment_users', 'Payment info'],
    ['purchase_users', 'Purchased'],
  ],
}

function labelFor(table, key) {
  const col = (table.columns || []).find((c) => c.key === key)
  return col ? col.label : key
}

function ChartFrame({ title, children, legend }) {
  return (
    <div className="fchart">
      <div className="fchart-title">{title}</div>
      {children}
      {legend && legend.length > 0 && (
        <div className="fchart-legend">
          {legend.map((l, i) => (
            <span key={i}><i style={{ background: l.color }} />{l.label}</span>
          ))}
        </div>
      )}
    </div>
  )
}

function Empty({ title }) {
  return (
    <div className="fchart">
      <div className="fchart-title">{title}</div>
      <div className="fchart-empty">No data for this period.</div>
    </div>
  )
}

// --- Line chart -----------------------------------------------------------

function LineChart({ spec, table, prev }) {
  // Date tables arrive newest-first; reversing reads left-to-right in time.
  // Hour/weekday tables are already in their natural order, so `chrono: false`
  // leaves them alone.
  const rows = spec.chrono === false ? (table.rows || []) : [...(table.rows || [])].reverse()
  if (rows.length === 0) return <Empty title={spec.title} />

  // Comparison series: same column from the previous period, matched on the
  // dimension label so a missing hour/day doesn't shift the line.
  const prevRows = spec.compare && prev
    ? (spec.chrono === false ? (prev.rows || []) : [...(prev.rows || [])].reverse())
    : []
  const prevBy = {}
  prevRows.forEach((r) => { prevBy[r.dim] = r })

  const W = 640, H = 210, P = { t: 14, r: 14, b: 30, l: 44 }
  const series = spec.series || []
  const isPct = (table.columns || []).find((c) => c.key === series[0])?.type === 'pct'
  let max = 0
  rows.forEach((r) => series.forEach((s) => { const v = Number(r[s]); if (v > max) max = v }))
  prevRows.forEach((r) => series.forEach((s) => { const v = Number(r[s]); if (v > max) max = v }))
  max = max || 1
  const iw = W - P.l - P.r, ih = H - P.t - P.b
  const x = (i) => P.l + (rows.length === 1 ? iw / 2 : (i / (rows.length - 1)) * iw)
  const y = (v) => P.t + ih - (Math.max(0, Number(v) || 0) / max) * ih

  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => max * f)
  const every = Math.max(1, Math.ceil(rows.length / 9))

  return (
    <ChartFrame
      title={spec.title}
      legend={[
        ...series.map((s, i) => ({ label: labelFor(table, s), color: SERIES_COLORS[i % SERIES_COLORS.length] })),
        ...(prevRows.length ? [{ label: 'Previous period', color: '#9aa3b2' }] : []),
      ]}
    >
      <svg className="fsvg" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMidYMid meet">
        {ticks.map((t, i) => (
          <g key={i}>
            <line x1={P.l} x2={W - P.r} y1={y(t)} y2={y(t)} stroke="#eceff5" strokeWidth="1" />
            <text x={P.l - 8} y={y(t) + 3.5} textAnchor="end" className="fsvg-axis">
              {isPct ? t.toFixed(1) + '%' : Math.round(t).toLocaleString('en-IN')}
            </text>
          </g>
        ))}
        {prevRows.length > 0 && series.map((s) => {
          const pts = rows
            .map((r, i) => {
              const p = prevBy[r.dim]
              return p && p[s] !== null && p[s] !== undefined ? `${x(i)},${y(p[s])}` : null
            })
            .filter(Boolean)
            .join(' ')
          return (
            <polyline key={'prev-' + s} points={pts} fill="none" stroke="#9aa3b2" strokeWidth="1.6"
              strokeDasharray="4 3" strokeLinejoin="round" strokeLinecap="round" />
          )
        })}
        {series.map((s, si) => {
          const color = SERIES_COLORS[si % SERIES_COLORS.length]
          const pts = rows
            .map((r, i) => (r[s] === null || r[s] === undefined ? null : `${x(i)},${y(r[s])}`))
            .filter(Boolean)
            .join(' ')
          return (
            <g key={s}>
              <polyline points={pts} fill="none" stroke={color} strokeWidth="2"
                strokeLinejoin="round" strokeLinecap="round" />
              {rows.map((r, i) => (r[s] === null || r[s] === undefined ? null : (
                <circle key={i} cx={x(i)} cy={y(r[s])} r="2.6" fill={color}>
                  <title>{`${r.dim} — ${labelFor(table, s)}: ${isPct ? fmtPct(r[s]) : fmtFloat(r[s])}`}</title>
                </circle>
              )))}
            </g>
          )
        })}
        {rows.map((r, i) => (i % every === 0 ? (
          <text key={i} x={x(i)} y={H - 10} textAnchor="middle" className="fsvg-axis">{r.dim}</text>
        ) : null))}
      </svg>
    </ChartFrame>
  )
}

// --- Bar chart ------------------------------------------------------------

function BarChart({ spec, table }) {
  const limit = spec.limit || 14
  const rows = (table.rows || []).slice(0, limit)
  if (rows.length === 0) return <Empty title={spec.title} />

  const series = spec.series || []
  const isPct = (table.columns || []).find((c) => c.key === series[0])?.type === 'pct'
  const W = 640, H = 230, P = { t: 14, r: 14, b: 58, l: 46 }
  let max = 0
  rows.forEach((r) => series.forEach((s) => { const v = Number(r[s]); if (v > max) max = v }))
  max = max || 1
  const iw = W - P.l - P.r, ih = H - P.t - P.b
  const slot = iw / rows.length
  const bw = Math.max(3, Math.min(26, (slot - 8) / series.length))
  const y = (v) => P.t + ih - (Math.max(0, Number(v) || 0) / max) * ih
  const ticks = [0, 0.5, 1].map((f) => max * f)

  return (
    <ChartFrame
      title={spec.title}
      legend={series.length > 1
        ? series.map((s, i) => ({ label: labelFor(table, s), color: SERIES_COLORS[i % SERIES_COLORS.length] }))
        : null}
    >
      <svg className="fsvg" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMidYMid meet">
        {ticks.map((t, i) => (
          <g key={i}>
            <line x1={P.l} x2={W - P.r} y1={y(t)} y2={y(t)} stroke="#eceff5" strokeWidth="1" />
            <text x={P.l - 8} y={y(t) + 3.5} textAnchor="end" className="fsvg-axis">
              {isPct ? t.toFixed(1) + '%' : Math.round(t).toLocaleString('en-IN')}
            </text>
          </g>
        ))}
        {rows.map((r, i) => (
          <g key={i}>
            {series.map((s, si) => {
              const cx = P.l + slot * i + slot / 2 - (series.length * bw) / 2 + si * bw
              const h = P.t + ih - y(r[s])
              return (
                <rect key={s} x={cx} y={y(r[s])} width={bw - 2} height={Math.max(0, h)}
                  rx="2" fill={SERIES_COLORS[si % SERIES_COLORS.length]}>
                  <title>{`${r.dim} — ${labelFor(table, s)}: ${isPct ? fmtPct(r[s]) : fmtFloat(r[s])}`}</title>
                </rect>
              )
            })}
            <text x={P.l + slot * i + slot / 2} y={H - 42} className="fsvg-axis fsvg-rot"
              transform={`rotate(-38 ${P.l + slot * i + slot / 2} ${H - 42})`} textAnchor="end">
              {String(r.dim).length > 20 ? String(r.dim).slice(0, 19) + '…' : r.dim}
            </text>
          </g>
        ))}
      </svg>
    </ChartFrame>
  )
}

// --- Funnel ---------------------------------------------------------------

function FunnelChart({ spec, table }) {
  const variant = spec.long ? 'long' : spec.site ? 'site' : spec.checkout ? 'checkout' : 'default'
  const steps = FUNNEL_STEPS[variant]
  const t = table.totals || {}
  const values = steps.map(([k, label]) => ({ key: k, label, value: Number(t[k]) || 0 }))
  const top = values[0]?.value || 0
  if (!top) return <Empty title={spec.title} />

  return (
    <ChartFrame title={spec.title}>
      <div className="ffunnel">
        {values.map((v, i) => {
          const prev = i === 0 ? null : values[i - 1].value
          const share = (v.value / top) * 100
          const step = prev ? (v.value / prev) * 100 : 100
          return (
            <div className="ffunnel-row" key={v.key}>
              <div className="ffunnel-lbl">{v.label}</div>
              <div className="ffunnel-track">
                <div className="ffunnel-fill" style={{
                  width: Math.max(share, 0.6) + '%',
                  background: SERIES_COLORS[i % SERIES_COLORS.length],
                }} />
                <span className="ffunnel-val">{fmtFloat(v.value)}</span>
              </div>
              <div className="ffunnel-pct">
                {share.toFixed(2)}%
                {prev !== null && <span className="ffunnel-step">{step.toFixed(1)}% of prev</span>}
              </div>
            </div>
          )
        })}
      </div>
    </ChartFrame>
  )
}

export default function FunnelCharts({ charts, tables, prevTables }) {
  const byKey = {}
  ;(tables || []).forEach((t) => { byKey[t.key] = t })
  const prevByKey = {}
  ;(prevTables || []).forEach((t) => { prevByKey[t.key] = t })
  const specs = (charts || []).filter((c) => byKey[c.table])
  if (specs.length === 0) return null
  return (
    <div className="fcharts">
      {specs.map((spec, i) => {
        const table = byKey[spec.table]
        if (spec.type === 'line') {
          return <LineChart key={i} spec={spec} table={table} prev={prevByKey[spec.table]} />
        }
        if (spec.type === 'bar') return <BarChart key={i} spec={spec} table={table} />
        if (spec.type === 'funnel') return <FunnelChart key={i} spec={spec} table={table} />
        return null
      })}
    </div>
  )
}
