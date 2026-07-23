import React, { useEffect, useState } from 'react'
import { api, getToken, clearAuth } from './api'
import Login from './Login'
import Dashboard from './Dashboard'

export default function App() {
  // undefined = loading, null = logged out, object = current user
  const [me, setMe] = useState(undefined)

  useEffect(() => {
    if (!getToken()) { setMe(null); return }
    api('/api/auth/me')
      .then(setMe)
      .catch(() => { clearAuth(); setMe(null) })
  }, [])

  if (me === undefined) return <div className="loading">Loading…</div>
  if (!me) return <Login onLogin={setMe} />
  return <Dashboard me={me} onLogout={() => { clearAuth(); setMe(null) }} />
}
