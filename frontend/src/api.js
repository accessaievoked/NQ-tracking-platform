// Thin API client for the NQ backend. Auth is a bearer session token stored in
// localStorage; requests go to /api/* which Vite proxies to FastAPI in dev.

export function getToken() {
  return localStorage.getItem('nq_token') || ''
}
export function setToken(t) {
  localStorage.setItem('nq_token', t)
}
export function clearAuth() {
  localStorage.removeItem('nq_token')
  localStorage.removeItem('nq_brand')
}

export async function api(path, opts = {}) {
  const headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) }
  const t = getToken()
  if (t) headers.Authorization = 'Bearer ' + t
  const res = await fetch(path, { ...opts, headers })
  if (!res.ok) {
    let data = {}
    try { data = await res.json() } catch (e) { /* ignore */ }
    throw new Error(data.detail || 'HTTP ' + res.status)
  }
  return res.status === 204 ? null : res.json()
}
