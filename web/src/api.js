// Thin API client for the Genomind-India FastAPI backend.
// JWT is kept in localStorage (single-clinician desktop console; switch to
// httpOnly cookies for multi-user deployments).

const TOKEN_KEY = 'genomind_token'
let currentUser = null

export function getToken() { return localStorage.getItem(TOKEN_KEY) }
export function setToken(t) { t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY) }
export function getUser() { return currentUser }
export function logout() { setToken(null); currentUser = null }

async function request(path, { method = 'GET', body, form } = {}) {
  const headers = {}
  const token = getToken()
  if (token) headers['Authorization'] = `Bearer ${token}`
  let payload
  if (form) {
    headers['Content-Type'] = 'application/x-www-form-urlencoded'
    payload = new URLSearchParams(form).toString()
  } else if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    payload = JSON.stringify(body)
  }
  const res = await fetch(`/api/v1${path}`, { method, headers, body: payload })
  if (res.status === 401) {
    logout()
    const err = new Error('Session expired — please sign in again.')
    err.status = 401
    throw err
  }
  if (!res.ok) {
    let detail = res.statusText
    try { const j = await res.json(); detail = j.detail || detail } catch { /* keep */ }
    throw new Error(detail)
  }
  return res.json()
}

export async function login(username, password) {
  // OAuth2 password flow (FastAPI's default form contract)
  const data = await request('/auth/token', { method: 'POST', form: { username, password } })
  setToken(data.access_token)
  currentUser = { username, role: data.role || 'clinician' }
  return currentUser
}

export const api = {
  // diagnosis + XAI
  diagnose: (body) => request('/diagnosis', { method: 'POST', body }),
  explain: (body) => request('/xai/explain', { method: 'POST', body }),
  diseaseDetail: (id) => request(`/diseases/${encodeURIComponent(id)}`),
  kgStats: () => request('/kg/stats'),

  // clinical
  ner: (body) => request('/clinical/ner', { method: 'POST', body }),
  mapHpo: (body) => request('/clinical/map-hpo', { method: 'POST', body }),

  // pharmacogenomics / reproductive / triage
  pgx: (body) => request('/pgx/assess', { method: 'POST', body }),
  counsel: (body) => request('/reproductive/counsel', { method: 'POST', body }),
  triage: (body) => request('/triage', { method: 'POST', body }),

  // dashboard
  national: () => request('/dashboard/national'),
  policyBrief: () => request('/dashboard/policy-brief'),
  researchGap: () => request('/dashboard/research-gap'),

  // learning / federated
  learningIngest: (body) => request('/learning/ingest', { method: 'POST', body }),
  federatedRun: (body) => request('/federated/train', { method: 'POST', body }),
}
