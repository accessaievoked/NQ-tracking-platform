import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api } from './api'
import { fmtInt } from './funnelFormat'
import {
  CHANNEL_COLORS,
  CHANNEL_LABELS,
  CHANNEL_ORDER,
  STAGE_COLOR,
  colorFor,
  networkLayout,
  sankeyLayout,
} from './liveJourneyLayout'

// Poll rather than stream. SSE would need the session token in a query string
// (EventSource can't send headers) and a long-lived connection per open tab;
// a 3s poll against an indexed 30-minute window is cheaper and survives every
// proxy in the path. Swap to SSE if this ever needs sub-second latency.
const POLL_MS = 3000
// While the pixel has never reported, re-check for it. This is what makes the
// install screen slide into the graph on its own the moment the first event
// lands — the merchant pastes the pixel, switches back, and sees it work.
const STATUS_POLL_MS = 4000

const W = 940
const H = 460

// --- tooltip ---------------------------------------------------------------

function useTooltip() {
  const [tip, setTip] = useState(null)
  const box = useRef(null)

  const show = useCallback((e, title, lines) => {
    const rect = box.current?.getBoundingClientRect()
    if (!rect) return
    setTip({ x: e.clientX - rect.left, y: e.clientY - rect.top, title, lines })
  }, [])
  const hide = useCallback(() => setTip(null), [])

  const node = tip ? (
    <div
      className="lj-tip"
      style={{
        left: Math.min(tip.x + 14, W - 150),
        top: Math.max(tip.y - 10, 0),
      }}
    >
      <div className="lj-tip-t">{tip.title}</div>
      {tip.lines.map((l, i) => <div key={i}>{l}</div>)}
    </div>
  ) : null

  return { box, show, hide, node }
}

// --- views -----------------------------------------------------------------

function FlowView({ graph, tip }) {
  const layout = useMemo(
    () => sankeyLayout(graph.nodes, graph.sankey_links, { width: W, height: H }),
    [graph],
  )
  if (!layout.nodes.length) return null

  return (
    <svg className="lj-svg" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMidYMid meet">
      <g>
        {layout.ribbons.map((r) => (
          <path
            key={r.key}
            d={r.path}
            fill={r.color}
            fillOpacity={0.3}
            onMouseMove={(e) =>
              tip.show(e, `${labelOf(graph, r.source)} → ${labelOf(graph, r.target)}`, [
                `${fmtInt(r.value)} visitor${r.value === 1 ? '' : 's'}`,
              ])
            }
            onMouseLeave={tip.hide}
          />
        ))}
      </g>
      <g>
        {layout.nodes.map((n) => (
          <g key={n.id}>
            <rect
              x={n.x} y={n.y} width={n.w} height={n.h} rx={2}
              fill={colorFor(n)}
              onMouseMove={(e) =>
                tip.show(e, n.label, [
                  `${fmtInt(n.here)} here now`,
                  `${fmtInt(n.seen)} passed through`,
                ])
              }
              onMouseLeave={tip.hide}
            />
            {/* Direct labels, not colour alone — and the relief the amber and
                blue slots need to stay readable against a white card. */}
            <text className="lj-node-label" x={n.x + n.w + 7} y={n.y + n.h / 2 + 4}>
              {n.label} <tspan className="lj-node-num">{fmtInt(n.seen)}</tspan>
            </text>
          </g>
        ))}
      </g>
    </svg>
  )
}

function NetworkView({ graph, tip }) {
  const layout = useMemo(
    () => networkLayout(graph.nodes, graph.links, { width: W, height: H }),
    [graph],
  )
  if (!layout.nodes.length) return null

  return (
    <svg className="lj-svg" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMidYMid meet">
      <defs>
        <marker id="lj-arrow" viewBox="0 0 10 10" refX="9" refY="5"
          markerWidth="6" markerHeight="6" orient="auto-start-reverse">
          <path d="M0,1 L9,5 L0,9 z" fill="#c3c8d2" />
        </marker>
      </defs>
      <g>
        {layout.edges.map((e) => (
          <line
            key={e.key}
            x1={e.x1} y1={e.y1} x2={e.x2} y2={e.y2}
            stroke="#c3c8d2" strokeWidth={e.width} strokeOpacity={0.75}
            markerEnd="url(#lj-arrow)"
            onMouseMove={(ev) =>
              tip.show(ev, `${labelOf(graph, e.source)} → ${labelOf(graph, e.target)}`, [
                `${fmtInt(e.value)} visitor${e.value === 1 ? '' : 's'}`,
              ])
            }
            onMouseLeave={tip.hide}
          />
        ))}
      </g>
      <g>
        {layout.nodes.map((n) => (
          <g key={n.id}>
            <circle
              cx={n.x} cy={n.y} r={n.r}
              fill={colorFor(n)} stroke="#fff" strokeWidth={2}
              onMouseMove={(e) =>
                tip.show(e, n.label, [
                  `${fmtInt(n.here)} here now`,
                  `${fmtInt(n.seen)} passed through`,
                ])
              }
              onMouseLeave={tip.hide}
            />
            <text className="lj-node-label" x={n.x} y={n.y + n.r + 15} textAnchor="middle">
              {n.label}
            </text>
            <text className="lj-node-num lj-node-label" x={n.x} y={n.y + n.r + 28}
              textAnchor="middle">
              {fmtInt(n.here)}
            </text>
          </g>
        ))}
      </g>
    </svg>
  )
}

function TableView({ graph }) {
  return (
    <div className="lj-tables">
      <div>
        <div className="lj-cap">Nodes — visitors present now, and everyone who passed through.</div>
        <table className="lj-table">
          <thead>
            <tr><th>Node</th><th>Type</th><th className="num">Here now</th><th className="num">Passed through</th></tr>
          </thead>
          <tbody>
            {graph.nodes.map((n) => (
              <tr key={n.id}>
                <td>{n.label}</td>
                <td>{n.kind === 'channel' ? 'Channel' : 'Page'}</td>
                <td className="num">{fmtInt(n.here)}</td>
                <td className="num">{fmtInt(n.seen)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div>
        <div className="lj-cap">Transitions — distinct visitors who made each hop.</div>
        <table className="lj-table">
          <thead><tr><th>From</th><th>To</th><th className="num">Visitors</th></tr></thead>
          <tbody>
            {graph.links.slice(0, 40).map((l) => (
              <tr key={`${l.source}>${l.target}`}>
                <td>{labelOf(graph, l.source)}</td>
                <td>{labelOf(graph, l.target)}</td>
                <td className="num">{fmtInt(l.value)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function labelOf(graph, id) {
  const n = graph.nodes.find((x) => x.id === id)
  return n ? n.label : id
}

// --- setup state -----------------------------------------------------------

function PixelSetup({ brandId }) {
  const [pixel, setPixel] = useState(null)
  const [copied, setCopied] = useState(false)
  const [err, setErr] = useState('')

  useEffect(() => {
    api(`/api/brands/${brandId}/live/pixel`).then(setPixel).catch((e) => setErr(e.message))
  }, [brandId])

  async function copy() {
    try {
      await navigator.clipboard.writeText(pixel.code)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch (e) {
      setErr('Could not copy — select the code and copy manually.')
    }
  }

  return (
    <div className="card lj-setup">
      <h2>Install the pixel to start seeing live journeys</h2>
      <p className="page-sub">
        This is the only setup step. The snippet below already has this brand's
        ingest URL baked in — nothing to edit.
      </p>
      <ol className="lj-steps">
        <li>In Shopify admin, go to <b>Settings → Customer events</b>.</li>
        <li>Click <b>Add custom pixel</b> and name it <b>NQ Live Journey</b>.</li>
        <li>Paste the code below, click <b>Save</b>, then <b>Connect</b>.</li>
        <li>Open the storefront in another tab — visitors appear here within seconds.</li>
      </ol>
      <div className="lj-listening">
        <i />Listening for the first event — this page switches to the graph on its own.
      </div>
      {err && <p className="err">{err}</p>}
      {pixel && (
        <>
          <div className="lj-code-head">
            <span>Custom pixel code</span>
            <button className="btn ghost lj-copy" onClick={copy}>
              {copied ? 'Copied' : 'Copy code'}
            </button>
          </div>
          <pre className="lj-code">{pixel.code}</pre>
        </>
      )}
    </div>
  )
}

// --- page ------------------------------------------------------------------

export default function LiveJourney({ brandId }) {
  const [status, setStatus] = useState(null)
  const [graph, setGraph] = useState(null)
  const [windowMin, setWindowMin] = useState(30)
  const [channel, setChannel] = useState('all')
  const [view, setView] = useState('flow')
  const [err, setErr] = useState('')
  const tip = useTooltip()

  useEffect(() => {
    setStatus(null)
    setGraph(null)
    if (!brandId) return
    let alive = true
    let timer

    async function check() {
      try {
        const s = await api(`/api/brands/${brandId}/live/status`)
        if (!alive) return
        setStatus(s)
        setErr('')
        if (!s.pixel_installed) timer = setTimeout(check, STATUS_POLL_MS)
      } catch (e) {
        if (alive) setErr(e.message)
      }
    }
    check()
    return () => { alive = false; clearTimeout(timer) }
  }, [brandId])

  useEffect(() => {
    if (!brandId || !status?.pixel_installed) return
    let alive = true
    let timer

    async function tick() {
      try {
        const g = await api(
          `/api/brands/${brandId}/live/graph?window=${windowMin}&channel=${channel}`,
        )
        if (!alive) return
        setGraph(g)
        setErr('')
      } catch (e) {
        if (alive) setErr(e.message)
      }
      if (alive) timer = setTimeout(tick, POLL_MS)
    }
    tick()
    return () => { alive = false; clearTimeout(timer) }
  }, [brandId, windowMin, channel, status?.pixel_installed])

  if (!brandId) return <div className="stub"><h1 className="page">Live Journey</h1></div>
  if (err && !status) return <div className="stub"><p className="err">{err}</p></div>
  if (!status) return <div className="loading">Loading…</div>
  if (!status.pixel_installed) {
    return (
      <>
        <h1 className="page">Live Journey</h1>
        <p className="page-sub">Where every visitor is right now, and how they got there.</p>
        <PixelSetup brandId={brandId} />
      </>
    )
  }

  const k = graph?.kpis
  const topChannel = k && Object.keys(k.channels).sort((a, b) => k.channels[b] - k.channels[a])[0]
  const presentChannels = CHANNEL_ORDER.filter((c) => graph?.nodes.some((n) => n.id === c))
  const hasData = graph && graph.nodes.length > 0

  return (
    <>
      <h1 className="page">
        Live Journey
        <span className={`lj-live ${graph ? 'on' : ''}`}>
          <i /> {graph ? 'live' : 'connecting…'}
        </span>
      </h1>
      <p className="page-sub">
        Every visitor threaded by their Shopify <code>clientId</code> — nodes are where
        people are, ribbons are where they went.
      </p>

      {/* One filter row above everything it scopes. */}
      <div className="lj-filters">
        <div className="lj-seg">
          {[5, 30].map((m) => (
            <button key={m} className={windowMin === m ? 'on' : ''}
              onClick={() => setWindowMin(m)}>Last {m} min</button>
          ))}
        </div>
        <select value={channel} onChange={(e) => setChannel(e.target.value)}
          aria-label="Acquisition channel">
          <option value="all">All channels</option>
          {CHANNEL_ORDER.map((c) => (
            <option key={c} value={c}>{CHANNEL_LABELS[c]}</option>
          ))}
        </select>
        <div className="lj-seg">
          {[['flow', 'Flow'], ['network', 'Network'], ['table', 'Table']].map(([v, l]) => (
            <button key={v} className={view === v ? 'on' : ''} onClick={() => setView(v)}>{l}</button>
          ))}
        </div>
      </div>

      <div className="lj-tiles">
        <Tile k="Active visitors" v={k ? fmtInt(k.active_visitors) : '—'}
          n={`in the last ${windowMin} min`} />
        <Tile k="Sessions" v={k ? fmtInt(k.sessions) : '—'} n="distinct visits" />
        <Tile k="Reached purchase" v={k ? fmtInt(k.purchases) : '—'}
          n={k ? `${k.conversion_rate_pct}% of visitors` : ''} />
        <Tile k="Top channel" v={topChannel ? CHANNEL_LABELS[topChannel] : '—'}
          n={topChannel ? `${fmtInt(k.channels[topChannel])} visitors` : 'no traffic yet'} />
      </div>

      <div className="card lj-card">
        <div className="lj-card-head">
          <div>
            <div className="fchart-title">
              {view === 'flow' ? 'Traffic flow' : view === 'network' ? 'Live network' : 'Table view'}
            </div>
            <div className="lj-hint">
              {view === 'flow'
                ? 'Ribbon width is the number of distinct visitors who made that hop.'
                : view === 'network'
                  ? 'Node size is how many visitors are on that page right now.'
                  : 'The same numbers, readable without colour.'}
            </div>
          </div>
        </div>

        {/* Hold the previous render while refetching — no skeleton flash. */}
        <div className="lj-plot" ref={tip.box} style={{ opacity: graph ? 1 : 0.45 }}>
          {!hasData && (
            <div className="fchart-empty">
              {graph ? 'No visitors in this window yet.' : 'Waiting for the first snapshot…'}
            </div>
          )}
          {hasData && view === 'flow' && <FlowView graph={graph} tip={tip} />}
          {hasData && view === 'network' && <NetworkView graph={graph} tip={tip} />}
          {hasData && view === 'table' && <TableView graph={graph} />}
          {tip.node}
        </div>

        {/* Legend is always present for >= 2 series. */}
        <div className="fchart-legend">
          {presentChannels.map((c) => (
            <span key={c}><i style={{ background: CHANNEL_COLORS[c] }} />{CHANNEL_LABELS[c]}</span>
          ))}
          <span><i style={{ background: STAGE_COLOR }} />Store page</span>
        </div>
      </div>
      {err && <p className="err">{err}</p>}
    </>
  )
}

function Tile({ k, v, n }) {
  return (
    <div className="lj-tile">
      <div className="lj-tile-k">{k}</div>
      <div className="lj-tile-v">{v}</div>
      <div className="lj-tile-n">{n}</div>
    </div>
  )
}
