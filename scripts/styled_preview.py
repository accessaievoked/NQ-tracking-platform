"""Styled (adverti-look) HTML renderer for report previews.

A developer preview tool: takes a *rich* facts bundle and renders the
card-based, dark-theme layout (gradient hero, coloured ROAS tiles, Money In /
Money Out panels, GST bridge table, platform cards). It is NOT wired into the
app — it exists so you can eyeball what a polished report looks like.

Currently composes the True ROAS / Money Flow report; other report types fall
back to the plain Markdown preview in scripts/preview_report.py.
"""
from __future__ import annotations

import html
import re

_COLORS = {
    "red": "#f87171", "amber": "#fbbf24", "green": "#34d399",
    "purple": "#c4b5fd", "white": "#ffffff", "muted": "#8b8b9e",
}


def esc(x) -> str:
    return html.escape(str(x))


def inline(text: str) -> str:
    """Escape, then render **bold** (bold picks up the accent-white colour)."""
    t = esc(text)
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)


def _c(color: str | None) -> str:
    return _COLORS.get(color or "", "")


# --------------------------------------------------------------------------
# Components
# --------------------------------------------------------------------------

def hero(brand: str, title: str, period: str, platforms: str, h: dict) -> str:
    line = (
        f"You spent <span style='color:{_COLORS['amber']}'>{esc(h['spent'])}</span> on ads. "
        f"<span style='color:{_COLORS['amber']}'>{esc(h['net_revenue'])}</span> net revenue "
        f"reached your store. Dashboards claimed "
        f"<span style='color:{_COLORS['amber']}'>{esc(h['dashboard_roas'])}</span> ROAS. "
        f"Your real return: <span style='color:{_COLORS['green']}'>{esc(h['true_roas'])}</span>."
    )
    return (
        "<div class='hero'>"
        f"<div class='hero-top'><span class='badge'>{esc(brand)}</span>"
        f"<span class='hero-meta'>{esc(title)} &nbsp;·&nbsp; {esc(period)} &nbsp;·&nbsp; {esc(platforms)}</span></div>"
        f"<div class='hero-line'>{line}</div>"
        f"<div class='hero-note'>{inline(h.get('note',''))}</div>"
        "</div>"
    )


def warning(text: str) -> str:
    return f"<div class='warn'><span class='warn-ic'>⚠</span><div>{inline(text)}</div></div>"


def alert_card(title: str, body: str) -> str:
    return (
        "<div class='alert'>"
        f"<div class='alert-title'>🔴 {inline(title)}</div>"
        f"<div class='alert-body'>{inline(body)}</div></div>"
    )


def section_label(text: str) -> str:
    return f"<div class='seclabel'>{esc(text)}</div>"


def roas_cards(cards: list[dict]) -> str:
    cells = []
    for c in cards:
        col = _c(c.get("color"))
        cells.append(
            "<div class='rcard' style='border-top-color:" + (col or "#333") + "'>"
            f"<div class='rcard-label'><span class='dot' style='background:{col}'></span>{esc(c['label'])}</div>"
            f"<div class='rcard-val' style='color:{col}'>{esc(c['value'])}</div>"
            f"<div class='rcard-cap'>{esc(c.get('caption',''))}</div></div>"
        )
    return "<div class='grid3'>" + "".join(cells) + "</div>"


def panel(header: str, rows: list[dict], accent: str) -> str:
    col = _c(accent)
    body = []
    for r in rows:
        rc = _c(r.get("color"))
        label_style = f"color:{rc}" if rc else ""
        val_style = f"color:{rc};font-weight:700" if rc else "font-weight:700"
        cls = "prow total" if r.get("highlight") else "prow"
        dot = f"<span class='dot' style='background:{rc}'></span>" if r.get("highlight") and rc else ""
        body.append(
            f"<div class='{cls}'><div style='{label_style}'>{dot}{inline(r['label'])}</div>"
            f"<div style='{val_style}'>{inline(str(r['value']))}</div></div>"
        )
    return (
        "<div class='panel'>"
        f"<div class='panel-head' style='color:{col}'>{esc(header)}</div>"
        + "".join(body) + "</div>"
    )


def two_panels(left: str, right: str) -> str:
    return f"<div class='grid2'>{left}{right}</div>"


def stat_grid(stats: list[dict]) -> str:
    cells = []
    for s in stats:
        col = _c(s.get("color"))
        cells.append(
            "<div class='stat'>"
            f"<div class='stat-label'>{esc(s['label'])}</div>"
            f"<div class='stat-val' style='color:{col}'>{esc(s['value'])}</div>"
            f"<div class='stat-cap'>{inline(s.get('caption',''))}</div></div>"
        )
    return "<div class='statgrid'>" + "".join(cells) + "</div>"


def _badge(value: str, color: str) -> str:
    col = _c(color)
    return f"<span class='pill' style='color:{col};border-color:{col}55;background:{col}18'>{esc(value)}</span>"


def compare_table(title: str, tag: str, cols: list[str], rows: list[dict]) -> str:
    head = "".join(f"<th>{esc(c)}</th>" for c in cols)
    body = []
    for r in rows:
        cells = []
        for cell in r["cells"]:
            if isinstance(cell, dict):  # a badge cell {value,color}
                cells.append(f"<td>{_badge(cell['value'], cell.get('color','purple'))}</td>")
            else:
                cells.append(f"<td>{inline(str(cell))}</td>")
        body.append("<tr>" + "".join(cells) + "</tr>")
    tagh = f"<span class='tag'>{esc(tag)}</span>" if tag else ""
    return (
        "<div class='panel'>"
        f"<div class='panel-head neutral'>{esc(title)} {tagh}</div>"
        f"<table class='ctable'><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table></div>"
    )


def platform_card(p: dict) -> str:
    metrics = []
    for m in p["metrics"]:
        col = _c(m.get("color"))
        metrics.append(
            "<div class='pm'>"
            f"<div class='pm-label'>{esc(m['label'])}</div>"
            f"<div class='pm-val' style='color:{col}'>{esc(m['value'])}</div>"
            f"<div class='pm-cap'>{esc(m.get('caption',''))}</div></div>"
        )
    icon = p.get("icon", "●")
    icon_bg = p.get("icon_bg", "#333")
    return (
        "<div class='pcard'>"
        f"<div class='pcard-head'><span class='picon' style='background:{icon_bg}'>{esc(icon)}</span>"
        f"<span class='pname'>{esc(p['name'])}</span>"
        f"<span class='pspend'>{esc(p['spend'])}</span></div>"
        f"<div class='pmgrid'>{''.join(metrics)}</div></div>"
    )


def platform_cards(cards: list[dict]) -> str:
    return "<div class='grid2'>" + "".join(platform_card(p) for p in cards) + "</div>"


def _status_color(status: str) -> str:
    s = (status or "").lower()
    if "scale" in s:
        return "green"
    if "pause" in s or "kill" in s:
        return "red"
    if "review" in s:
        return "amber"
    return "amber"


def campaign_table(ct: dict) -> str:
    cols = ct["cols"]
    head = "".join(f"<th>{esc(c)}</th>" for c in cols)
    body = []
    for r in ct["rows"]:
        scolor = _status_color(r.get("status", ""))
        camp = f"<div class='cname'>{esc(r['campaign'])}</div>"
        if r.get("sub"):
            camp += f"<div class='sub'>{esc(r['sub'])}</div>"
        body.append(
            "<tr>"
            f"<td>{camp}</td>"
            f"<td>{esc(r.get('platform',''))}</td>"
            f"<td>{esc(r.get('spend',''))}</td>"
            f"<td>{esc(r.get('gst_adj_spend',''))}</td>"
            f"<td>{esc(r.get('reported_rev',''))}</td>"
            f"<td>{_badge(r.get('gst_roas',''), scolor)}</td>"
            f"<td><span class='stxt' style='color:{_c(scolor)}'>● {esc(r.get('status',''))}</span></td>"
            "</tr>"
        )
    if ct.get("total"):
        t = ct["total"]
        body.append(
            "<tr class='ctotal'>"
            f"<td><strong>{esc(t.get('campaign','TOTAL'))}</strong></td>"
            f"<td>{esc(t.get('platform',''))}</td>"
            f"<td><strong>{esc(t.get('spend',''))}</strong></td>"
            f"<td><strong>{esc(t.get('gst_adj_spend',''))}</strong></td>"
            f"<td><strong>{esc(t.get('reported_rev',''))}</strong></td>"
            f"<td><strong>{esc(t.get('gst_roas',''))}</strong></td>"
            f"<td><strong style='color:{_COLORS['purple']}'>{esc(t.get('status',''))}</strong></td>"
            "</tr>"
        )
    tag = f"<span class='tag'>{esc(ct['tag'])}</span>" if ct.get("tag") else ""
    return (
        "<div class='panel'>"
        f"<div class='panel-head neutral'>{esc(ct.get('title','Campaign-Level ROAS'))} {tag}</div>"
        f"<div class='tscroll'><table class='ctable'><thead><tr>{head}</tr></thead>"
        f"<tbody>{''.join(body)}</tbody></table></div></div>"
    )


def statgrid_n(stats: list[dict], cols: int) -> str:
    cells = []
    for s in stats:
        col = _c(s.get("color"))
        cells.append(
            "<div class='stat'>"
            f"<div class='stat-val' style='color:{col}'>{esc(s['value'])}</div>"
            f"<div class='stat-label2'>{esc(s['label'])}</div>"
            f"<div class='stat-cap'>{inline(s.get('caption',''))}</div></div>"
        )
    return (
        f"<div class='statgrid' style='grid-template-columns:repeat({cols},1fr)'>"
        + "".join(cells) + "</div>"
    )


def breakeven(be: dict) -> str:
    cards = roas_cards(be["cards"])
    crit = f"<div class='alert'><div class='alert-body'>{inline(be['critical'])}</div></div>" if be.get("critical") else ""
    return cards + crit


def bar_chart(chart: dict) -> str:
    days = chart["days"]
    if not days:
        return ""
    mx = max(max(d.get("net", 0), d.get("spend", 0)) for d in days) or 1
    H = 150
    bars = []
    bw = 100.0 / len(days)
    for i, d in enumerate(days):
        x = i * bw
        nh = d.get("net", 0) / mx * H
        sh = d.get("spend", 0) / mx * H
        bars.append(
            f"<rect x='{x + bw*0.18:.2f}%' y='{H - nh:.1f}' width='{bw*0.28:.2f}%' height='{nh:.1f}' fill='{_COLORS['green']}' rx='1'/>"
            f"<rect x='{x + bw*0.5:.2f}%' y='{H - sh:.1f}' width='{bw*0.28:.2f}%' height='{sh:.1f}' fill='{_COLORS['amber']}' rx='1'/>"
        )
    labels = "".join(
        f"<div style='flex:1;text-align:center'>{esc(d['day'])}</div>" for d in days
    )
    notes = "".join(f"<span class='cnote'>{inline(n)}</span>" for n in chart.get("notes", []))
    return (
        "<div class='panel'><div class='panel-head neutral'>"
        f"{esc(chart.get('title','Daily Net Sales vs Ad Spend'))}</div>"
        "<div style='padding:18px'>"
        "<div class='legend'><span><i style='background:" + _COLORS['green'] + "'></i>Net Sales</span>"
        "<span><i style='background:" + _COLORS['amber'] + "'></i>Daily Ad Spend (est.)</span></div>"
        f"<svg viewBox='0 0 100 {H}' preserveAspectRatio='none' style='width:100%;height:170px'>{''.join(bars)}</svg>"
        f"<div class='xaxis'>{labels}</div>"
        f"<div class='cnotes'>{notes}</div>"
        "</div></div>"
    )


def actions_list(actions: dict) -> str:
    items = []
    for a in actions["items"]:
        idir = a.get("impact_dir", "up")
        icol = _COLORS["green"] if idir == "up" else _COLORS["red"]
        arrow = "↑" if idir == "up" else "↓"
        items.append(
            "<div class='action'>"
            f"<div class='anum'>{esc(a['n'])}</div>"
            "<div class='abody'>"
            f"<div class='atitle'>{inline(a['title'])}</div>"
            f"<div class='atext'>{inline(a['body'])}</div>"
            f"<div class='aimpact' style='color:{icol}'>{arrow} {inline(a['impact'])}</div>"
            "</div></div>"
        )
    sub = f"<span class='tag'>{esc(actions['subtitle'])}</span>" if actions.get("subtitle") else ""
    return (
        "<div class='panel'>"
        f"<div class='panel-head neutral'>{esc(actions.get('title','Highest-Impact Actions'))} {sub}</div>"
        f"<div class='actions'>{''.join(items)}</div></div>"
    )


def footer_block(lines: list[str]) -> str:
    return "<div class='rfoot'>" + "".join(f"<div>{inline(l)}</div>" for l in lines) + "</div>"


CSS = """
:root{color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;background:#0a0a0f;color:#e6e6ef;
 font:15px/1.55 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif}
.wrap{max-width:940px;margin:0 auto;padding:28px 20px 80px}
.badge{display:inline-block;font-size:12px;font-weight:700;letter-spacing:.06em;
 color:#fff;background:#7c3aed;padding:5px 12px;border-radius:999px}
.hero{background:linear-gradient(135deg,#171233 0%,#0e1030 60%,#0c0c1a 100%);
 border:1px solid #241d45;border-radius:18px;padding:26px 28px;margin-bottom:18px}
.hero-top{display:flex;align-items:center;gap:14px;margin-bottom:16px;flex-wrap:wrap}
.hero-meta{color:#9a9ab0;font-size:13px}
.hero-line{font-size:30px;line-height:1.28;font-weight:800;color:#fff;letter-spacing:-.01em}
.hero-note{margin-top:14px;color:#9a9ab0;font-size:13.5px;max-width:760px}
.warn{display:flex;gap:12px;background:rgba(245,166,35,.08);border:1px solid rgba(245,166,35,.35);
 border-radius:14px;padding:16px 18px;margin:16px 0;color:#e6cf9e;font-size:13.5px;line-height:1.5}
.warn strong{color:#fbbf24}
.warn-ic{color:#fbbf24;font-size:18px;line-height:1.3}
.alert{background:rgba(248,113,113,.07);border:1px solid rgba(248,113,113,.3);border-radius:14px;
 padding:18px 20px;margin:16px 0}
.alert-title{color:#f87171;font-weight:800;font-size:17px;margin-bottom:8px}
.alert-body{color:#d9b3b3;font-size:13.5px;line-height:1.6}
.alert-body strong{color:#f87171}
.seclabel{color:#8b7bf0;font-size:12px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;
 margin:28px 0 12px}
.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.rcard{background:#12121c;border:1px solid #201f30;border-top:3px solid #333;border-radius:14px;padding:18px}
.rcard-label{font-size:11.5px;letter-spacing:.05em;text-transform:uppercase;color:#8b8b9e;
 display:flex;align-items:center;gap:8px;font-weight:700}
.rcard-val{font-size:38px;font-weight:800;margin:8px 0 6px;letter-spacing:-.02em}
.rcard-cap{color:#8b8b9e;font-size:12.5px;line-height:1.4}
.dot{width:9px;height:9px;border-radius:50%;display:inline-block}
.panel{background:#111019;border:1px solid #201f30;border-radius:14px;overflow:hidden}
.panel-head{padding:14px 18px;font-size:13px;font-weight:800;letter-spacing:.04em;text-transform:uppercase;
 background:rgba(255,255,255,.02);border-bottom:1px solid #201f30}
.panel-head.neutral{color:#e6e6ef;display:flex;align-items:center;gap:10px}
.prow{display:flex;justify-content:space-between;gap:14px;padding:13px 18px;border-bottom:1px solid #191826;font-size:14px}
.prow>div:first-child{color:#b9b9c8}
.prow.total{background:rgba(124,58,237,.08)}
.tag{font-size:10.5px;font-weight:700;color:#fbbf24;background:rgba(245,166,35,.14);
 border:1px solid rgba(245,166,35,.35);padding:3px 8px;border-radius:6px;letter-spacing:.03em}
.statgrid{display:grid;grid-template-columns:1fr 1fr;gap:22px 34px;background:#111019;border:1px solid #201f30;
 border-radius:14px;padding:24px 26px;margin:2px 0}
.stat-label{font-size:11.5px;letter-spacing:.05em;text-transform:uppercase;color:#8b8b9e;font-weight:700}
.stat-val{font-size:30px;font-weight:800;margin:6px 0 4px;letter-spacing:-.02em}
.stat-cap{color:#8b8b9e;font-size:12.5px;line-height:1.4}
.ctable{width:100%;border-collapse:collapse;font-size:13.5px}
.ctable th{text-align:right;padding:12px 16px;font-size:11px;letter-spacing:.04em;text-transform:uppercase;
 color:#8b8b9e;border-bottom:1px solid #201f30}
.ctable th:first-child{text-align:left}
.ctable td{text-align:right;padding:13px 16px;border-bottom:1px solid #191826}
.ctable td:first-child{text-align:left;color:#c7c7d4}
.pill{display:inline-block;font-weight:800;font-size:13px;padding:4px 11px;border-radius:999px;border:1px solid}
.pcard{background:#111019;border:1px solid #201f30;border-radius:14px;overflow:hidden}
.pcard-head{display:flex;align-items:center;gap:12px;padding:16px 18px;border-bottom:1px solid #201f30}
.picon{width:30px;height:30px;border-radius:8px;display:flex;align-items:center;justify-content:center;
 color:#fff;font-weight:800;font-size:15px}
.pname{font-weight:800;font-size:16px}
.pspend{margin-left:auto;color:#9a9ab0;font-size:13px}
.pmgrid{display:grid;grid-template-columns:repeat(3,1fr)}
.pm{padding:14px 16px;border-right:1px solid #191826;border-bottom:1px solid #191826}
.pm-label{font-size:10.5px;letter-spacing:.04em;text-transform:uppercase;color:#8b8b9e;font-weight:700;min-height:26px}
.pm-val{font-size:22px;font-weight:800;margin:4px 0 2px}
.pm-cap{color:#8b8b9e;font-size:11.5px}
.foot{color:#5f5f74;font-size:12px;margin-top:36px}
.tscroll{overflow-x:auto}
.cname{font-weight:700;color:#e6e6ef;font-size:13px}
.sub{color:#7b7b8f;font-size:11px;margin-top:2px}
.stxt{font-weight:700;font-size:12.5px;white-space:nowrap}
.ctable td{vertical-align:top}
.ctotal td{background:rgba(124,58,237,.08);border-top:1px solid #2a2740}
.stat-label2{font-size:12px;color:#b9b9c8;font-weight:600;margin-top:4px}
.legend{display:flex;gap:18px;color:#9a9ab0;font-size:12px;margin-bottom:8px}
.legend i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:6px;vertical-align:middle}
.xaxis{display:flex;color:#6b6b80;font-size:9.5px;margin-top:6px}
.cnotes{margin-top:10px;display:flex;gap:16px;flex-wrap:wrap}
.cnote{color:#8b8b9e;font-size:11.5px}
.actions{padding:6px 0}
.action{display:flex;gap:16px;padding:18px 20px;border-bottom:1px solid #191826}
.anum{flex:0 0 30px;height:30px;border-radius:8px;background:#7c3aed;color:#fff;font-weight:800;
 display:flex;align-items:center;justify-content:center;font-size:15px}
.atitle{font-weight:700;color:#fff;font-size:14.5px;margin-bottom:6px}
.atext{color:#a9a9bb;font-size:13px;line-height:1.55}
.aimpact{font-size:12.5px;font-weight:700;margin-top:8px}
.rfoot{color:#6b6b80;font-size:11.5px;line-height:1.7;margin-top:30px;
 border-top:1px solid #1a1a26;padding-top:16px}
"""


def page(brand: str, title: str, blocks: list[str]) -> str:
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{esc(brand)} — {esc(title)}</title><style>{CSS}</style></head>"
        f"<body><div class='wrap'>{''.join(blocks)}"
        "<div class='foot'>NQ Tracking Platform — styled report preview. "
        "Every figure comes only from the computed facts bundle.</div>"
        "</div></body></html>"
    )


def render_true_roas(facts: dict) -> str:
    """Compose the True ROAS / Money Flow report from a rich facts bundle."""
    brand = facts.get("brand", "Brand")
    title = facts.get("report_title", "True ROAS / Money Flow Report")
    blocks: list[str] = [
        hero(brand, title, facts.get("period", ""), facts.get("platforms", ""), facts["hero"]),
    ]
    if facts.get("warning"):
        blocks.append(warning(facts["warning"]))
    if facts.get("roas_cards"):
        blocks.append(section_label("Part A — The ROAS Reality"))
        blocks.append(roas_cards(facts["roas_cards"]))
    if facts.get("inflation_callout"):
        ic = facts["inflation_callout"]
        blocks.append(alert_card(ic["title"], ic["body"]))
    if facts.get("money_in") and facts.get("money_out"):
        blocks.append(section_label("Money In & Money Out"))
        blocks.append(two_panels(
            panel(facts["money_in"]["header"], facts["money_in"]["rows"], "green"),
            panel(facts["money_out"]["header"], facts["money_out"]["rows"], "red"),
        ))
    if facts.get("stat_grid"):
        blocks.append(stat_grid(facts["stat_grid"]))
    if facts.get("gst_bridge"):
        gb = facts["gst_bridge"]
        blocks.append(section_label("Part B — Technical Depth"))
        blocks.append(compare_table(gb.get("title", "GST Correction Bridge"),
                                    gb.get("tag", ""), gb["cols"], gb["rows"]))
    if facts.get("platform_cards"):
        blocks.append(section_label("Platform Breakdown"))
        blocks.append(platform_cards(facts["platform_cards"]))
    if facts.get("campaign_table"):
        blocks.append(campaign_table(facts["campaign_table"]))
    if facts.get("breakeven"):
        blocks.append(section_label("Break-Even Analysis"))
        blocks.append(breakeven(facts["breakeven"]))
    if facts.get("order_health"):
        oh = facts["order_health"]
        blocks.append(section_label(oh.get("title", "Order Health")))
        blocks.append(statgrid_n(oh["tiles"], len(oh["tiles"])))
    if facts.get("chart"):
        blocks.append(bar_chart(facts["chart"]))
    if facts.get("actions"):
        blocks.append(section_label("Highest-Impact Actions — Priority Order"))
        blocks.append(actions_list(facts["actions"]))
    if facts.get("footer"):
        blocks.append(footer_block(facts["footer"]))
    return page(brand, title, blocks)


# report_type value -> composer
COMPOSERS = {"true_roas_money_flow": render_true_roas}


def render_styled(report_type_value: str, facts: dict) -> str | None:
    """Return styled HTML if this report type has a composer AND the facts look
    rich (contain a 'hero'); otherwise None so the caller can fall back."""
    fn = COMPOSERS.get(report_type_value)
    if fn and isinstance(facts, dict) and "hero" in facts:
        return fn(facts)
    return None
