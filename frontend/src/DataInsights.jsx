import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api } from './api'
import FunnelCharts from './FunnelCharts'
import { columnRange, csvFor, fmtCell, fmtInt, heatStyle, todayISO } from './funnelFormat'

const PAGE_SIZE = 30
const PRESETS = [
  { label: '7D', days: 7 },
  { label: '14D', days: 14 },
  { label: '30D', days: 30 },
  { label: '90D', days: 90 },
]

// --- Page-title filter ----------------------------------------------------

function DimensionFilter({ label, options, selected, onChange, loading }) {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const box = useRef(null)

  useEffect(() => {
    function onDoc(e) { if (box.current && !box.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [])

  const shown = useMemo(() => {
    const needle = q.trim().toLowerCase()
    return needle ? options.filter((o) => o.value.toLowerCase().includes(needle)) : options
  }, [options, q])

  const all = selected.length === 0
  function toggle(v) {
    onChange(selected.includes(v) ? selected.filter((s) => s !== v) : [...selected, v])
  }

  return (
    <div className="ptf" ref={box}>
      <button className="ptf-btn" onClick={() => setOpen((o) => !o)} disabled={loading}>
        <span className="ptf-lbl">{label}</span>
        <span className="ptf-val">{all ? 'All' : `${selected.length} selected`}</span>
        <span className="ms">expand_more</span>
      </button>
      {open && (
        <div className="ptf-menu">
          <div className="ptf-head">
            <label className="ptf-item">
              <input type="checkbox" checked={all} onChange={() => onChange([])} />
              <span className="ptf-name">{label}</span>
              <span className="ptf-users">Total users</span>
            </label>
          </div>
          <div className="ptf-search pill-input">
            <span className="ms" style={{ color: 'var(--t40)' }}>search</span>
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Type to search" />
          </div>
          <div className="ptf-list">
            {shown.length === 0 && <div className="ptf-empty">No values match.</div>}
            {shown.map((o) => (
              <label className="ptf-item" key={o.value}>
                <input type="checkbox" checked={all || selected.includes(o.value)}
                  onChange={() => toggle(o.value)} />
                <span className="ptf-name" title={o.value}>{o.value || '(not set)'}</span>
                <span className="ptf-users">{fmtInt(o.total_users)}</span>
              </label>
            ))}
          </div>
          {selected.length > 0 && (
            <button className="ptf-clear" onClick={() => onChange([])}>Clear filter</button>
          )}
        </div>
      )}
    </div>
  )
}

// --- Table ----------------------------------------------------------------

function FunnelTable({ table }) {
  const [page, setPage] = useState(0)
  const [sort, setSort] = useState(null) // { key, dir }

  useEffect(() => { setPage(0); setSort(null) }, [table])

  const rows = useMemo(() => {
    if (!sort) return table.rows
    const dir = sort.dir === 'asc' ? 1 : -1
    return [...table.rows].sort((a, b) => {
      const x = a[sort.key], y = b[sort.key]
      if (x === y) return 0
      if (x === null || x === undefined) return 1
      if (y === null || y === undefined) return -1
      return (typeof x === 'number' && typeof y === 'number' ? x - y : String(x).localeCompare(String(y))) * dir
    })
  }, [table, sort])

  const pages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE))
  const slice = rows.slice(page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE)

  // Heat scales are computed across the whole table, not just the visible page,
  // so paging doesn't change a cell's colour.
  const ranges = useMemo(() => {
    const out = {}
    table.columns.forEach((c) => { if (c.heat) out[c.key] = columnRange(table.rows, c.key) })
    return out
  }, [table])

  function download() {
    const blob = new Blob([csvFor(table)], { type: 'text/csv;charset=utf-8' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `${table.key}.csv`
    a.click()
    URL.revokeObjectURL(a.href)
  }

  function toggleSort(key) {
    setPage(0)
    setSort((s) => (s && s.key === key
      ? (s.dir === 'desc' ? { key, dir: 'asc' } : null)
      : { key, dir: 'desc' }))
  }

  return (
    <div className="ftable-card">
      <div className="ftable-head">
        <div className="ftable-title">{table.title}</div>
        {/* Only item-scoped tables are badged — they count items rather than
            users, so their rates aren't comparable to the other tables. */}
        {table.scope === 'items' && (
          <span className="fscope items"
            title="Counts items (a basket can hold several) and attributes purchases to the product, so rates differ from the user-scoped tables. Not affected by the page-title filter.">
            {table.scope_label}
          </span>
        )}
        <button className="ftable-dl" onClick={download} title="Download CSV">
          <span className="ms">download</span>
        </button>
      </div>
      <div className="ftable-scroll">
        <table className="ftable">
          <thead>
            <tr>
              <th className="ftable-idx" />
              {table.columns.map((c) => (
                <th key={c.key} className={c.type === 'text' ? 'l' : ''} onClick={() => toggleSort(c.key)}>
                  {c.label}
                  {sort && sort.key === c.key && <span className="ms sort">{sort.dir === 'asc' ? 'arrow_upward' : 'arrow_downward'}</span>}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {slice.length === 0 && (
              <tr><td className="fempty" colSpan={table.columns.length + 1}>No rows for this period.</td></tr>
            )}
            {slice.map((r, i) => (
              <tr key={r._key ?? r.dim_raw ?? i}>
                <td className="ftable-idx">{page * PAGE_SIZE + i + 1}.</td>
                {table.columns.map((c) => (
                  <td key={c.key} className={c.type === 'text' ? 'l' : ''}
                    style={c.heat ? heatStyle(r[c.key], ranges[c.key], c.inverse) : undefined}
                    title={c.type === 'text' ? String(r[c.key] ?? '') : undefined}>
                    {fmtCell(r[c.key], c.type)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <td className="ftable-idx" />
              {table.columns.map((c, i) => (
                <td key={c.key} className={c.type === 'text' ? 'l' : ''}>
                  {i === 0 ? 'Grand total' : fmtCell(table.totals[c.key], c.type)}
                </td>
              ))}
            </tr>
          </tfoot>
        </table>
      </div>
      <div className="ftable-foot">
        <span>{rows.length === 0 ? '0' : `${page * PAGE_SIZE + 1} - ${Math.min(rows.length, (page + 1) * PAGE_SIZE)}`} / {table.row_count}</span>
        <button disabled={page === 0} onClick={() => setPage((p) => p - 1)}><span className="ms">chevron_left</span></button>
        <button disabled={page >= pages - 1} onClick={() => setPage((p) => p + 1)}><span className="ms">chevron_right</span></button>
      </div>
    </div>
  )
}

// --- Page -----------------------------------------------------------------

const FILTERS = [
  { key: 'page_title', label: 'Page title' },
  { key: 'source_medium', label: 'Source / medium' },
  { key: 'browser', label: 'Browser' },
]
const NO_FILTERS = { page_title: [], source_medium: [], browser: [] }

export default function DataInsights({ brandId, onGoToLibrary }) {
  const [status, setStatus] = useState(null)
  const [views, setViews] = useState([])
  const [view, setView] = useState('overview')
  const [start, setStart] = useState(todayISO(-29))
  const [end, setEnd] = useState(todayISO(0))
  const [options, setOptions] = useState({})
  const [filters, setFilters] = useState(NO_FILTERS)
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState('')

  const qs = useCallback(() => {
    const p = new URLSearchParams({ start, end })
    FILTERS.forEach(({ key }) => (filters[key] || []).forEach((v) => p.append(key, v)))
    return p.toString()
  }, [start, end, filters])

  // 1. Connection check — nothing renders until GA4 is actually live.
  useEffect(() => {
    if (!brandId) return
    setStatus(null); setData(null); setErr('')
    api(`/api/brands/${brandId}/analytics/status`).then(setStatus).catch((e) => {
      setStatus({ can_render: false }); setErr(e.message)
    })
  }, [brandId])

  useEffect(() => {
    if (!status || !status.can_render) return
    api(`/api/brands/${brandId}/analytics/views`).then((v) => {
      setViews(v)
      if (v.length && !v.find((x) => x.key === view)) setView(v[0].key)
    }).catch(() => {})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status, brandId])

  // Filter dropdown values follow the selected period.
  useEffect(() => {
    if (!status || !status.can_render) return
    let live = true
    Promise.all(FILTERS.map(({ key }) =>
      api(`/api/brands/${brandId}/analytics/filter-values/${key}?start=${start}&end=${end}`)
        .then((vals) => [key, vals]).catch(() => [key, []])
    )).then((pairs) => { if (live) setOptions(Object.fromEntries(pairs)) })
    return () => { live = false }
  }, [status, brandId, start, end])

  const load = useCallback(async () => {
    if (!brandId || !status || !status.can_render) return
    setLoading(true); setErr('')
    try {
      setData(await api(`/api/brands/${brandId}/analytics/funnel/${view}?${qs()}`))
    } catch (e) {
      setErr(e.message); setData(null)
    } finally {
      setLoading(false)
    }
  }, [brandId, status, view, qs])

  useEffect(() => { load() }, [load])

  function applyPreset(days) {
    setStart(todayISO(-(days - 1)))
    setEnd(todayISO(0))
  }

  // Each view declares the horizon it is meant to be read over — Hourly is a
  // single day, the long/dropout views run months — so switching tab retunes
  // the range instead of leaving a meaningless one behind.
  function selectView(v) {
    setView(v.key)
    if (v.default_days) applyPreset(v.default_days)
  }

  function setFilter(key, values) {
    setFilters((f) => ({ ...f, [key]: values }))
  }

  const activeFilters = FILTERS.reduce((n, { key }) => n + (filters[key] || []).length, 0)

  // --- Not connected ---
  if (status && !status.can_render) {
    const ga4 = status.ga4 || {}
    return (
      <>
        <h1 className="page">Data Insights &amp; Charts</h1>
        <p className="page-sub">Funnel analytics built on your Google Analytics 4 property.</p>
        <div className="card fnotconn">
          <div className="fnotconn-icon"><span className="ms">insights</span></div>
          <h3>Google Analytics 4 isn&apos;t connected</h3>
          <p>
            This page reads live GA4 event data — item views, add to cart, checkout and purchase.
            {ga4.status === 'error'
              ? ' The saved credentials were rejected, so reconnect the property.'
              : ' Connect the property in Brand Library and the report appears here.'}
          </p>
          {ga4.last_error && <p className="fnotconn-err">{ga4.last_error}</p>}
          <button className="btn" onClick={onGoToLibrary}>Go to Brand Library</button>
        </div>
      </>
    )
  }

  const current = views.find((v) => v.key === view)

  return (
    <>
      <h1 className="page">Data Insights &amp; Charts</h1>
      <p className="page-sub">
        {current ? current.blurb : 'Funnel analytics built on your Google Analytics 4 property.'}
      </p>

      {/* Option bar: every funnel view on one page */}
      <div className="fviews">
        {views.map((v) => (
          <button key={v.key} className={`fview ${v.key === view ? 'active' : ''}`}
            onClick={() => selectView(v)}>{v.label}</button>
        ))}
      </div>

      <div className="fcontrols card">
        {FILTERS.map((f) => (
          <DimensionFilter key={f.key} label={f.label} options={options[f.key] || []}
            selected={filters[f.key] || []} onChange={(v) => setFilter(f.key, v)} loading={loading} />
        ))}
        {activeFilters > 0 && (
          <button className="ptf-reset" onClick={() => setFilters(NO_FILTERS)}
            title="Clear all filters"><span className="ms">filter_alt_off</span></button>
        )}
        <div className="fdates">
          <input type="date" value={start} max={end} onChange={(e) => setStart(e.target.value)} />
          <span className="fdash">—</span>
          <input type="date" value={end} min={start} max={todayISO(0)} onChange={(e) => setEnd(e.target.value)} />
        </div>
        <div className="fpresets">
          {PRESETS.map((p) => (
            <button key={p.label} className="chip" onClick={() => applyPreset(p.days)}>{p.label}</button>
          ))}
        </div>
        <div className="spacer" />
        <button className="btn ghost" onClick={load} disabled={loading}>
          <span className="ms">refresh</span> {loading ? 'Loading…' : 'Refresh'}
        </button>
      </div>

      {err && <p className="err">{err}</p>}
      {loading && !data && <div className="report-loading">Pulling GA4 funnel data…</div>}

      {data && (
        <>
          {data.prev_period && (
            <p className="fcompare">
              Comparison period: {data.prev_period.start} — {data.prev_period.end}
            </p>
          )}
          <div className="ftables">
            {data.tables.map((t) => <FunnelTable key={t.key} table={t} />)}
          </div>
          <FunnelCharts charts={data.charts} tables={data.tables} prevTables={data.prev_tables} />
          <p className="fnote">
            Rates are user-based: ATC % = users who added to cart ÷ users who viewed an item;
            Checkout % and Purchase % / CR % use the same denominator, so ATC × ATC→Checkout ×
            Checkout→Purchase equals Purchase %. &ldquo;Add to baskets&rdquo; counts events, not users,
            so it runs higher than ATC % implies. Grand totals come from GA4 de-duplicated over the
            whole period, so they are not the sum of the rows — and they are identical across the
            by-date and by-page tables. CAS / CAF / GCI / ASI / API are custom events; check
            <code> /analytics/events </code> to confirm the property&apos;s real event names.
          </p>
        </>
      )}
    </>
  )
}
