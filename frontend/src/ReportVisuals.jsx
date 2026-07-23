import React from 'react'

function inr(n) {
  if (n === null || n === undefined) return '—'
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

function Tile({ val, label, sub, color }) {
  return (
    <div className="oh-tile">
      <div className={'oh-val ' + color}>{val}</div>
      <div className="oh-lbl">{label}</div>
      <div className="oh-sub">{sub}</div>
    </div>
  )
}

function DailyChart({ days }) {
  const max = Math.max(...days.map((d) => Math.max(d.net || 0, d.spend || 0)), 1)
  const H = 150
  const hasSpend = days.some((d) => d.spend != null)
  return (
    <div className="scard chart-card">
      <div className="chart-title">{hasSpend ? 'Daily Net Sales vs Ad Spend' : 'Daily Net Sales'}</div>
      <div className="chart" style={{ ['--h']: H + 'px' }}>
        {days.map((d, i) => (
          <div className="col" key={i}>
            <div className="bars">
              <div className="bar" title={'Net ' + inr(d.net)}
                style={{ height: (d.net / max * H) + 'px', background: d.best ? 'var(--green)' : '#7c8cff' }} />
              {hasSpend && (
                <div className="bar" title={'Ad spend ' + inr(d.spend)}
                  style={{ height: ((d.spend || 0) / max * H) + 'px', background: '#f5a623' }} />
              )}
            </div>
            <div className="xlabel">{d.label}</div>
          </div>
        ))}
      </div>
      <div className="chart-legend">
        <span><i style={{ background: '#7c8cff' }} />Net Sales</span>
        {hasSpend && <span><i style={{ background: '#f5a623' }} />Daily Ad Spend (est.)</span>}
        <span><i style={{ background: 'var(--green)' }} />Best Day</span>
      </div>
    </div>
  )
}

function Bar({ label, pct, color }) {
  const w = Math.max(0, Math.min(100, Number(pct) || 0))
  return (
    <div className="ohbar">
      <div className="ohbar-lbl" style={{ color }}>{label}</div>
      <div className="ohbar-track"><div className="ohbar-fill" style={{ width: w + '%', background: color }} /></div>
      <div className="ohbar-pct">{pct == null ? 'N/A' : pct + '%'}</div>
    </div>
  )
}

export default function ReportVisuals({ facts }) {
  const oh = facts && facts.order_health
  const daily = (facts && facts.daily) || []
  if (!oh && daily.length === 0) return null
  return (
    <>
      {oh && (
        <>
          <div className="seclabel">Order Health</div>
          <div className="oh-grid">
            <Tile color="green" val={oh.fulfilled_pct + '%'} label="Fulfillment Rate" sub={oh.fulfilled_orders + ' of ' + oh.total_orders + ' orders'} />
            <Tile color="red" val={oh.return_rate_pct + '%'} label="Reversal Rate" sub="Returns + cancels" />
            <Tile color="amber" val={oh.unfulfilled_pct + '%'} label="Unfulfilled" sub={oh.unfulfilled_orders + ' pending'} />
            <Tile color="purple" val={inr(oh.aov)} label="Avg. Order Value" sub={oh.total_orders + ' total orders'} />
            <Tile color="amber" val={oh.utm_coverage_pct == null ? 'N/A' : oh.utm_coverage_pct + '%'}
              label="UTM Coverage" sub={oh.utm_coverage_pct == null ? 'Not connected' : 'of orders tagged'} />
          </div>
          <div className="scard oh-bars">
            <Bar label="Fulfilled" pct={oh.fulfilled_pct} color="#34d399" />
            <Bar label="Unfulfilled" pct={oh.unfulfilled_pct} color="#fbbf24" />
            <Bar label="Reversals (of gross sales)" pct={oh.return_rate_pct} color="#f87171" />
            {oh.utm_coverage_pct != null && <Bar label="UTM Coverage" pct={oh.utm_coverage_pct} color="#fbbf24" />}
          </div>
        </>
      )}
      {daily.length > 0 && <DailyChart days={daily} />}
    </>
  )
}
