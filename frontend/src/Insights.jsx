import React, { useState } from 'react'
import { api } from './api'
import { REPORT_GROUPS, READY } from './reportTypes'
import { parseReport } from './mdReport'
import MoneyFlowReport from './MoneyFlowReport'

export default function Insights({ brandId }) {
  const [type, setType] = useState('money_flow_report')
  const [days, setDays] = useState(30)
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState('')
  const [report, setReport] = useState(null)

  async function generate() {
    setErr(''); setLoading(true); setReport(null)
    try {
      const r = await api(`/api/brands/${brandId}/reports/generate`, {
        method: 'POST', body: JSON.stringify({ type, days: Number(days) || 30 }),
      })
      setReport(r)
    } catch (e) {
      setErr(e.message)
    } finally {
      setLoading(false)
    }
  }

  const parsed = report ? parseReport(report.narrative_md) : null

  return (
    <>
      <h1 className="page">Insights &amp; Reports</h1>
      <p className="page-sub">Pick a report and generate it from your connected data.</p>

      <div className="report-controls card">
        <div className="rc-row">
          <div className="rc-field">
            <label>Report</label>
            <select value={type} onChange={(e) => setType(e.target.value)}>
              {REPORT_GROUPS.map((g) => (
                <optgroup key={g.group} label={g.group}>
                  {g.items.map((it) => (
                    <option key={it.type} value={it.type}>
                      {it.label}{READY.has(it.type) ? '' : '  (needs more connectors)'}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
          </div>
          <div className="rc-field days">
            <label>Period (days)</label>
            <input type="number" min="1" value={days} onChange={(e) => setDays(e.target.value)} />
          </div>
          <button className="btn" onClick={generate} disabled={loading || !brandId}>
            {loading ? 'Generating…' : 'Generate report'}
          </button>
        </div>
        {!READY.has(type) && (
          <p className="rc-note">This report needs ad-platform / commerce data that isn't connected yet —
            it will generate but note the sections it can't fill.</p>
        )}
        {err && <p className="err">{err}</p>}
      </div>

      {loading && <div className="report-loading">Computing metrics and writing the report…</div>}

      {report && report.type === 'money_flow_report' && report.facts && report.facts.headline_metrics && (
        <MoneyFlowReport report={report} />
      )}

      {report && parsed && !(report.type === 'money_flow_report' && report.facts && report.facts.headline_metrics) && (
        <div className="report-view">
          <div className="report-hero">
            <span className="badge">{report.title}</span>
            <div className="rh-period">{report.period}</div>
          </div>
          {parsed.pre && parsed.pre.trim() && (
            <div className="scard narrative" dangerouslySetInnerHTML={{ __html: parsed.pre }} />
          )}
          {parsed.sections.map((sec, idx) => (
            <div key={idx}>
              <div className="seclabel">{sec.name}</div>
              <div className="scard narrative" dangerouslySetInnerHTML={{ __html: sec.html }} />
            </div>
          ))}
        </div>
      )}
    </>
  )
}
