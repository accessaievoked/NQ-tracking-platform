// Formatting + conditional-colour helpers for the funnel tables.
// Kept out of the components so the heat scale is defined in exactly one place.

export function fmtInt(n) {
  if (n === null || n === undefined) return '—'
  return Number(n).toLocaleString('en-IN', { maximumFractionDigits: 0 })
}

export function fmtFloat(n) {
  if (n === null || n === undefined) return '—'
  const v = Number(n)
  return v.toLocaleString('en-IN', {
    minimumFractionDigits: Number.isInteger(v) ? 0 : 1,
    maximumFractionDigits: 2,
  })
}

export function fmtPct(n) {
  if (n === null || n === undefined) return '—'
  return Number(n).toFixed(2) + '%'
}

export function fmtMoney(n) {
  if (n === null || n === undefined) return '—'
  return 'Rs.' + Math.round(Number(n)).toLocaleString('en-IN')
}

export function fmtCell(value, type) {
  if (type === 'pct') return fmtPct(value)
  if (type === 'money') return fmtMoney(value)
  if (type === 'float') return fmtFloat(value)
  if (type === 'int') return fmtInt(value)
  return value === null || value === undefined || value === '' ? '(not set)' : String(value)
}

// Min/max of a column across the visible rows — the heat scale is relative,
// exactly like Looker's conditional formatting.
export function columnRange(rows, key) {
  let min = Infinity
  let max = -Infinity
  for (const r of rows) {
    const v = r[key]
    if (v === null || v === undefined || Number.isNaN(Number(v))) continue
    const n = Number(v)
    if (n < min) min = n
    if (n > max) max = n
  }
  if (min === Infinity) return null
  return { min, max }
}

// Red -> amber -> green. `inverse` flips it for drop-off columns where low wins.
export function heatStyle(value, range, inverse) {
  if (value === null || value === undefined || !range) return null
  const { min, max } = range
  let t = max === min ? 0.5 : (Number(value) - min) / (max - min)
  if (inverse) t = 1 - t
  t = Math.max(0, Math.min(1, t))
  const hue = 4 + t * 128 // 4 = red, 132 = green
  return {
    background: `hsl(${hue} 78% 90%)`,
    color: `hsl(${hue} 62% 26%)`,
    fontWeight: 600,
  }
}

// Chart palette, reused by every series so colours stay stable across views.
export const SERIES_COLORS = ['#00a5ff', '#7c5cff', '#12a150', '#f5a623', '#e5484d', '#0ea5a5']

export function todayISO(offsetDays = 0) {
  const d = new Date()
  d.setDate(d.getDate() + offsetDays)
  return d.toISOString().slice(0, 10)
}

export function csvFor(table) {
  const head = table.columns.map((c) => `"${c.label}"`).join(',')
  const body = table.rows
    .map((r) => table.columns.map((c) => JSON.stringify(r[c.key] ?? '')).join(','))
    .join('\n')
  const totals = table.columns.map((c) => JSON.stringify(table.totals[c.key] ?? '')).join(',')
  return [head, body, totals].filter(Boolean).join('\n')
}
