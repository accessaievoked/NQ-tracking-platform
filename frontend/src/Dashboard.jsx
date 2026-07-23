import React, { useEffect, useState } from 'react'
import { api } from './api'
import { PROVIDERS, COMING } from './providers'
import Sidebar from './Sidebar'
import ConnectDialog from './ConnectDialog'
import Insights from './Insights'

const PAGE_TITLES = { chats: 'Chats', workflows: 'Workflows' }

export default function Dashboard({ me, onLogout }) {
  const [page, setPage] = useState('library')
  const [collapsed, setCollapsed] = useState(localStorage.getItem('nq_collapsed') === '1')
  const [brands, setBrands] = useState([])
  const [brandId, setBrandId] = useState(localStorage.getItem('nq_brand') || '')
  const [integrations, setIntegrations] = useState([])
  const [filter, setFilter] = useState('all')
  const [search, setSearch] = useState('')
  const [dialogProv, setDialogProv] = useState(null)
  const [toast, setToast] = useState('')

  useEffect(() => { loadBrands() }, [])
  useEffect(() => { if (brandId) loadIntegrations() }, [brandId])

  function showToast(m) { setToast(m); setTimeout(() => setToast(''), 2200) }
  function toggleCollapsed() {
    const v = !collapsed
    setCollapsed(v); localStorage.setItem('nq_collapsed', v ? '1' : '0')
  }

  async function loadBrands() {
    // Every account is provisioned with a brand at registration — no create-brand UI.
    const list = await api('/api/brands')
    setBrands(list)
    let id = brandId
    if (!id || !list.find((b) => b.id === id)) id = list[0] ? list[0].id : ''
    setBrandId(id); localStorage.setItem('nq_brand', id)
  }
  async function loadIntegrations() {
    try { setIntegrations(await api(`/api/brands/${brandId}/integrations`)) } catch (e) { setIntegrations([]) }
  }
  function statusOf(p) { const it = integrations.find((i) => i.provider === p); return it ? it.status : 'not_connected' }
  async function disconnect(p) {
    await api(`/api/brands/${brandId}/integrations/${p}/disconnect`, { method: 'POST', body: '{}' })
    showToast('Disconnected'); loadIntegrations()
  }

  const provs = Object.keys(PROVIDERS)
  const total = provs.length
  const connected = provs.filter((p) => statusOf(p) === 'connected').length
  const notset = total - connected
  const cur = brands.find((b) => b.id === brandId)
  const brandName = cur ? cur.name : 'Brand'
  const initials = (me.email || 'NQ').slice(0, 2).toUpperCase()

  const entries = [
    ...provs.map((k) => [k, PROVIDERS[k], false]),
    ...Object.keys(COMING).map((k) => [k, COMING[k], true]),
  ]
  const visible = entries.filter(([prov, def, soon]) => {
    const isConn = !soon && statusOf(prov) === 'connected'
    if (filter === 'connected' && !isConn) return false
    if (filter === 'notset' && isConn) return false
    if (search && !def.name.toLowerCase().includes(search.toLowerCase())) return false
    return true
  })

  return (
    <div className={`app ${collapsed ? 'collapsed' : ''}`}>
      <button className="side-toggle" onClick={toggleCollapsed}
        title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}>
        <span className="ms">{collapsed ? 'chevron_right' : 'chevron_left'}</span>
      </button>

      <Sidebar page={page} setPage={setPage} me={me} onLogout={onLogout} />

      <main className="main">
        <div className="topbar">
          <div className="brand-select">
            <select value={brandId}
              onChange={(e) => { setBrandId(e.target.value); localStorage.setItem('nq_brand', e.target.value) }}>
              {brands.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
            </select>
            <span className="ms" style={{ color: 'var(--t40)' }}>expand_more</span>
          </div>
          <div className="conn-icons">
            {provs.map((p) => {
              const on = statusOf(p) === 'connected'
              return (
                <div key={p} className={`cic ${on ? '' : 'off'}`}
                  style={on ? { background: PROVIDERS[p].color } : {}}
                  title={PROVIDERS[p].name + (on ? ' (connected)' : '')}>
                  {PROVIDERS[p].letter}
                </div>
              )
            })}
          </div>
          <div className="spacer" />
          <div className="avatar">{initials}</div>
        </div>

        {page === 'library' ? (
          <>
            <h1 className="page">Brand Library</h1>
            <p className="page-sub">Manage your brand workspaces and connected data integrations.</p>

            <div className="card">
              <div className="card-head">
                <div className="avatar">{(brandName[0] || 'B').toUpperCase()}</div>
                <div className="bname">{brandName}</div>
                <button className="more"><span className="ms">more_vert</span></button>
              </div>
              <div className="divider" />
              <div className="setup">
                <div className="lbl">
                  <span className="ms">check_circle</span>
                  <span>{connected === total ? 'Setup complete' : 'Setup progress'}</span>
                </div>
                <div className="prog">
                  <div className="segs">
                    {Array.from({ length: total }).map((_, i) => (
                      <div key={i} className={`seg ${i < connected ? 'on' : ''}`} />
                    ))}
                  </div>
                  <div className="ptxt">{connected} out of {total} complete</div>
                </div>
              </div>
              <div className="search-int pill-input">
                <span className="ms" style={{ color: 'var(--t40)' }}>search</span>
                <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search Integrations" />
              </div>
              <div className="filters">
                {[['all', 'All'], ['connected', `Connected (${connected})`], ['notset', `Not setup (${notset})`]].map(([f, l]) => (
                  <button key={f} className={`chip ${filter === f ? 'active' : ''}`} onClick={() => setFilter(f)}>{l}</button>
                ))}
              </div>

              <div className="grid">
                {visible.length === 0 && <div className="empty">No integrations match.</div>}
                {visible.map(([prov, def, soon]) => {
                  const st = soon ? 'not_connected' : statusOf(prov)
                  const isConn = st === 'connected'
                  const isErr = st === 'error'
                  return (
                    <div key={prov} className={`ic ${soon ? 'soon' : ''}`}>
                      <div className="top">
                        <div className="cico" style={{ background: def.color }}>{def.letter}</div>
                        <div>
                          <div className="nm">{def.name}</div>
                          <div className={`st ${soon ? 'no' : isConn ? 'ok' : isErr ? 'err' : 'no'}`}>
                            {soon ? 'Coming soon' : isConn ? '✓ Connected' : isErr ? '⚠ Error' : 'Not set up'}
                          </div>
                        </div>
                      </div>
                      {!soon && (
                        <div className="act">
                          <button className={`lnk ${isConn ? 'grey' : ''}`} onClick={() => setDialogProv(prov)}>
                            {isConn ? 'Reconnect' : 'Connect'}
                          </button>
                          {isConn && <button className="lnk grey" onClick={() => disconnect(prov)}>Disconnect</button>}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
          </>
        ) : page === 'insights' ? (
          <Insights brandId={brandId} />
        ) : (
          <div className="stub">
            <h1 className="page">{PAGE_TITLES[page]}</h1>
            <p className="page-sub">Coming soon.</p>
          </div>
        )}
      </main>

      {dialogProv && (
        <ConnectDialog
          prov={dialogProv} brandId={brandId}
          onClose={() => setDialogProv(null)}
          onDone={() => { setDialogProv(null); showToast('Connected ' + PROVIDERS[dialogProv].name); loadIntegrations() }}
        />
      )}
      {toast && <div className="toast show">{toast}</div>}
    </div>
  )
}
