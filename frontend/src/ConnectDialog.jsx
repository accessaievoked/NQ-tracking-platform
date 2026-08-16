import React, { useState } from 'react'
import { api } from './api'
import { PROVIDERS } from './providers'

export default function ConnectDialog({ prov, brandId, onClose, onDone }) {
  const def = PROVIDERS[prov]
  const [vals, setVals] = useState({})
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  async function save() {
    const config = {}, credentials = {}
    def.fields.forEach((f) => {
      const v = (vals[f.k] || '').trim()
      if (!v) return
      const [group, key] = f.k.split('.')
      ;(group === 'config' ? config : credentials)[key] = v
    })
    setBusy(true); setErr('')
    try {
      const r = await api(`/api/brands/${brandId}/integrations/${prov}/connect`, {
        method: 'POST', body: JSON.stringify({ config, credentials }),
      })
      if (r.status === 'error') throw new Error(r.last_error || 'Connection failed')
      onDone()
    } catch (e) {
      setErr(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="backdrop" onClick={onClose}>
      <div className="dialog" onClick={(e) => e.stopPropagation()}>
        <h3>Connect {def.name}</h3>
        <p className="help">{def.help}</p>
        {def.fields.map((f) => (
          <div className="field" key={f.k}>
            <label>{f.label}</label>
            <input
              type={f.secret ? 'password' : 'text'} placeholder={f.label}
              value={vals[f.k] || ''}
              onChange={(e) => setVals({ ...vals, [f.k]: e.target.value })}
            />
          </div>
        ))}
        <div className="dlg-actions">
          <button className="btn ghost" onClick={onClose}>Cancel</button>
          <button className="btn" onClick={save} disabled={busy}>Connect</button>
        </div>
        <p className="err">{err}</p>
      </div>
    </div>
  )
}
