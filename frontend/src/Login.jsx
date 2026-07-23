import React, { useState } from 'react'
import { api, setToken } from './api'

export default function Login({ onLogin }) {
  const [email, setEmail] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit() {
    if (!email.trim()) return
    setErr(''); setBusy(true)
    try {
      const issued = await api('/api/auth/magic-link', {
        method: 'POST', body: JSON.stringify({ email }),
      })
      if (!issued.dev_login_url) throw new Error('No dev login URL (is APP_ENV=local?).')
      const token = new URL(issued.dev_login_url, location.origin).searchParams.get('token')
      const session = await api('/api/auth/verify?token=' + encodeURIComponent(token))
      setToken(session.token)
      const me = await api('/api/auth/me')
      onLogin(me)
    } catch (e) {
      setErr(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login-wrap">
      <div className="login-card">
        <div className="logo">N Q</div>
        <h1>Sign in</h1>
        <p>Enter your email — in dev mode you're logged in directly.</p>
        <div className="pill-input">
          <span className="ms" style={{ color: 'var(--t40)' }}>mail</span>
          <input
            type="email" placeholder="you@brand.com" value={email}
            onChange={(e) => setEmail(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && submit()}
          />
        </div>
        <button className="btn block" onClick={submit} disabled={busy}>Continue</button>
        <p className="err">{err}</p>
      </div>
    </div>
  )
}
