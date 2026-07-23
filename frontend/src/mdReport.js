// Minimal Markdown -> HTML for report narratives (headings, tables, lists,
// blockquotes, bold). Also splits a report into a title, period, and sections
// so the Insights page can render each "## SECTION" as its own card.

function esc(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}
function inline(t) {
  return esc(t).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
}

export function mdToHtml(md) {
  const lines = (md || '').split('\n')
  const out = []
  let i = 0
  while (i < lines.length) {
    const s = lines[i].trim()
    if (!s) { i++; continue }
    // table
    if (s.startsWith('|') && i + 1 < lines.length && /^\|[\s:|-]+\|$/.test(lines[i + 1].trim())) {
      const head = s.replace(/^\||\|$/g, '').split('|').map((c) => c.trim())
      i += 2
      const rows = []
      while (i < lines.length && lines[i].trim().startsWith('|')) {
        rows.push(lines[i].trim().replace(/^\||\|$/g, '').split('|').map((c) => c.trim()))
        i++
      }
      const th = head.map((c) => `<th>${inline(c)}</th>`).join('')
      const tb = rows.map((r) => '<tr>' + r.map((c) => `<td>${inline(c)}</td>`).join('') + '</tr>').join('')
      out.push(`<table><thead><tr>${th}</tr></thead><tbody>${tb}</tbody></table>`)
      continue
    }
    if (s.startsWith('### ')) { out.push(`<h3>${inline(s.slice(4))}</h3>`); i++; continue }
    if (s.startsWith('## ')) { out.push(`<h2>${inline(s.slice(3))}</h2>`); i++; continue }
    if (s.startsWith('> ')) {
      const q = []
      while (i < lines.length && lines[i].trim().startsWith('>')) { q.push(lines[i].trim().replace(/^>+/, '').trim()); i++ }
      out.push(`<blockquote>${inline(q.join(' '))}</blockquote>`)
      continue
    }
    if (s.startsWith('- ')) {
      const items = []
      while (i < lines.length && lines[i].trim().startsWith('- ')) { items.push(`<li>${inline(lines[i].trim().slice(2))}</li>`); i++ }
      out.push(`<ul>${items.join('')}</ul>`)
      continue
    }
    const para = []
    while (i < lines.length && lines[i].trim() && !/^(#|>|\||- )/.test(lines[i].trim())) { para.push(lines[i].trim()); i++ }
    out.push(`<p>${inline(para.join(' '))}</p>`)
  }
  return out.join('\n')
}

// Split "# Title / _period_ / ## Section ..." into structured parts.
export function parseReport(md) {
  const lines = (md || '').split('\n')
  const sections = []
  let cur = null
  const pre = []
  for (const ln of lines) {
    const s = ln.trim()
    if (s.startsWith('## ')) { cur = { name: s.slice(3), body: [] }; sections.push(cur) }
    else if (s.startsWith('# ')) { /* doc title -> hero (we already have title) */ }
    else if (!cur && /^_.*_$/.test(s)) { /* period -> hero */ }
    else if (!cur) { pre.push(ln) }
    else { cur.body.push(ln) }
  }
  return {
    pre: mdToHtml(pre.join('\n')),
    sections: sections.map((sec) => ({ name: sec.name, html: mdToHtml(sec.body.join('\n')) })),
  }
}
