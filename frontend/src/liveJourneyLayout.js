// Layout maths for the Live Journey graph, kept out of the component so the
// geometry can be reasoned about (and tested) on its own.
//
// The app ships no charting dependency — FunnelCharts.jsx draws its line/bar/
// funnel by hand — so these two views are hand-rolled SVG for the same reasons:
// no 1MB bundle, and the marks inherit the app's own CSS variables.

// Acquisition-channel colours. Order matters twice over: it is the legend
// order, and the palette was validated for colour-blind separation in exactly
// this sequence (adjacent pairs are the ones that must stay distinguishable).
// Four of the five are the app's existing SERIES_COLORS; the amber is a step
// darker than #f5a623 so it sits inside the readable lightness band on white.
export const CHANNEL_COLORS = {
  instagram: '#00a5ff',
  facebook: '#12a150',
  google: '#7c5cff',
  direct: '#d98c00',
  other: '#e5484d',
}

export const CHANNEL_ORDER = ['instagram', 'facebook', 'google', 'direct', 'other']

export const CHANNEL_LABELS = {
  instagram: 'Instagram',
  facebook: 'Facebook',
  google: 'Google',
  direct: 'Direct',
  other: 'Other',
}

// Store pages stay deliberately neutral: colour carries "which channel", and
// spending it on pages too would leave nothing to read the flow by.
export const STAGE_COLOR = '#b6bcc7'

export function colorFor(node) {
  return node.kind === 'channel' ? CHANNEL_COLORS[node.id] || STAGE_COLOR : STAGE_COLOR
}

function groupByColumn(nodes) {
  const cols = new Map()
  nodes.forEach((n) => {
    if (!cols.has(n.col)) cols.set(n.col, [])
    cols.get(n.col).push(n)
  })
  return [...cols.entries()].sort((a, b) => a[0] - b[0]).map(([col, list]) => ({ col, list }))
}

// --- Sankey ---------------------------------------------------------------

/**
 * Stack nodes into funnel-ordered columns and route one ribbon per link.
 * Returns absolute geometry; the component only renders it.
 */
export function sankeyLayout(nodes, links, opts = {}) {
  const {
    width = 900, height = 460, nodeWidth = 10, gap = 12,
    padding = { t: 10, r: 132, b: 10, l: 8 },
  } = opts

  if (!nodes.length) return { nodes: [], ribbons: [], height }

  const columns = groupByColumn(nodes)
  const innerW = width - padding.l - padding.r
  const innerH = height - padding.t - padding.b

  // One shared scale across all columns, otherwise a ribbon's thickness would
  // mean different things at different depths.
  let scale = Infinity
  columns.forEach(({ list }) => {
    const sum = list.reduce((a, n) => a + n.seen, 0)
    const available = innerH - gap * Math.max(0, list.length - 1)
    if (sum > 0 && available > 0) scale = Math.min(scale, available / sum)
  })
  if (!Number.isFinite(scale) || scale <= 0) scale = 1

  // Cap how tall the single biggest node may get. Without this, a column
  // holding one node (a single-channel filter, say) stretches it to the full
  // height and the diagram reads as a solid slab. Shrinking the *shared* scale
  // zooms the whole picture out, so every value stays comparable.
  const biggest = Math.max(...nodes.map((n) => n.seen), 1)
  scale = Math.min(scale, (innerH * 0.62) / biggest)

  const stepX = columns.length > 1 ? (innerW - nodeWidth) / (columns.length - 1) : 0
  const placed = new Map()

  columns.forEach(({ list }, ci) => {
    const totalH = list.reduce((a, n) => a + n.seen * scale, 0) + gap * (list.length - 1)
    let y = padding.t + Math.max(0, (innerH - totalH) / 2)
    list.forEach((n) => {
      const h = Math.max(2, n.seen * scale)
      placed.set(n.id, {
        ...n,
        x: padding.l + ci * stepX,
        y,
        h,
        w: nodeWidth,
        // Cursors track how much of each edge has been consumed by ribbons.
        outAt: y,
        inAt: y,
      })
      y += h + gap
    })
  })

  // Routing ribbons in target order (then source order) keeps crossings down
  // without needing a full iterative sankey relaxation.
  const routed = links
    .filter((l) => placed.has(l.source) && placed.has(l.target) && l.value > 0)
    .sort((a, b) => {
      const ay = placed.get(a.target).y - placed.get(b.target).y
      return ay !== 0 ? ay : placed.get(a.source).y - placed.get(b.source).y
    })

  const ribbons = routed.map((l) => {
    const s = placed.get(l.source)
    const t = placed.get(l.target)
    const h = Math.max(1, l.value * scale)

    const y0 = s.outAt
    const y1 = t.inAt
    s.outAt += h
    t.inAt += h

    const x0 = s.x + s.w
    const x1 = t.x
    const xm = (x0 + x1) / 2

    return {
      key: `${l.source}>${l.target}`,
      source: l.source,
      target: l.target,
      value: l.value,
      color: colorFor(s),
      path:
        `M${x0},${y0}` +
        `C${xm},${y0} ${xm},${y1} ${x1},${y1}` +
        `L${x1},${y1 + h}` +
        `C${xm},${y1 + h} ${xm},${y0 + h} ${x0},${y0 + h}Z`,
    }
  })

  return { nodes: [...placed.values()], ribbons, height }
}

// --- Network --------------------------------------------------------------

/**
 * Positions come from funnel depth, never from a force simulation. That is the
 * whole trick: a force layout re-solves on every refresh, so nodes jump around
 * and a live graph becomes unreadable. Here a node only ever changes size.
 */
export function networkLayout(nodes, links, opts = {}) {
  const {
    width = 900, height = 460, rMin = 7, rMax = 30,
    // Bottom padding leaves room for the two-line label under each node.
    padding = { t: 28, r: 60, b: 50, l: 60 },
  } = opts

  if (!nodes.length) return { nodes: [], edges: [] }

  const columns = groupByColumn(nodes)
  const innerW = width - padding.l - padding.r
  const innerH = height - padding.t - padding.b
  const maxHere = Math.max(1, ...nodes.map((n) => n.here))
  const stepX = columns.length > 1 ? innerW / (columns.length - 1) : 0

  const placed = new Map()
  columns.forEach(({ list }, ci) => {
    const sorted = [...list].sort((a, b) => b.here - a.here || a.id.localeCompare(b.id))
    const stepY = sorted.length > 1 ? innerH / (sorted.length - 1) : 0
    sorted.forEach((n, i) => {
      placed.set(n.id, {
        ...n,
        x: padding.l + ci * stepX,
        y: sorted.length === 1
          ? padding.t + innerH / 2
          : padding.t + i * stepY,
        // Area, not radius, tracks the count — radius would exaggerate ~3x.
        r: rMin + (rMax - rMin) * Math.sqrt(n.here / maxHere),
      })
    })
  })

  const maxV = Math.max(1, ...links.map((l) => l.value))
  const edges = links
    .filter((l) => placed.has(l.source) && placed.has(l.target))
    .map((l) => {
      const s = placed.get(l.source)
      const t = placed.get(l.target)
      // Trim the line to the circle edges so the arrowhead lands on the rim.
      const dx = t.x - s.x
      const dy = t.y - s.y
      const len = Math.hypot(dx, dy) || 1
      const ux = dx / len
      const uy = dy / len
      return {
        key: `${l.source}>${l.target}`,
        source: l.source,
        target: l.target,
        value: l.value,
        x1: s.x + ux * (s.r + 2),
        y1: s.y + uy * (s.r + 2),
        x2: t.x - ux * (t.r + 7),
        y2: t.y - uy * (t.r + 7),
        width: 1 + 5 * (l.value / maxV),
      }
    })

  return { nodes: [...placed.values()], edges }
}
