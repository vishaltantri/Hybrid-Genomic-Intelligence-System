// Thin API client for the Genomind-India / Genomera FastAPI backend.
// JWT is kept in localStorage; verified with /api/v1/auth/me.

const TOKEN_KEY = 'genomind_token'
let currentUser = null

export function getToken() {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(t) {
  if (t) {
    localStorage.setItem(TOKEN_KEY, t)
  } else {
    localStorage.removeItem(TOKEN_KEY)
  }
}

export function getUser() {
  return currentUser
}

export function setUser(u) {
  currentUser = u
}

export function logout() {
  setToken(null)
  currentUser = null
}

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
    try {
      const j = await res.json()
      detail = j.detail || detail
    } catch {
      /* keep */
    }
    throw new Error(detail)
  }
  return res.json()
}

export async function login(username, password) {
  // OAuth2 password flow (FastAPI's default form contract)
  const data = await request('/auth/token', { method: 'POST', form: { username, password } })
  setToken(data.access_token)
  // Fetch verified profile from /auth/me
  try {
    const me = await request('/auth/me')
    currentUser = { username: me.username, role: me.role, full_name: me.claims?.full_name || '' }
  } catch {
    currentUser = { username, role: data.role || 'clinician', full_name: '' }
  }
  return currentUser
}

export async function verifySession() {
  const token = getToken()
  if (!token) return null
  try {
    const me = await request('/auth/me')
    currentUser = { username: me.username, role: me.role, full_name: me.claims?.full_name || '' }
    return currentUser
  } catch {
    logout()
    return null
  }
}

export const api = {
  // auth
  getMe: () => request('/auth/me'),

  // diagnosis + XAI
  diagnose: (body) => request('/diagnosis', { method: 'POST', body }),
  explain: (body) => request('/xai/explain', { method: 'POST', body }),
  diseaseDetail: (id) => request(`/diseases/${encodeURIComponent(id)}`),
  kgStats: () => request('/kg/stats'),

  // clinical
  ner: (body) => request('/clinical/extract', { method: 'POST', body }),
  mapHpo: (body) => request('/clinical/hpo-map', { method: 'POST', body }),
  reference: () => request('/reference'),

  // patients
  listPatients: () => request('/patients'),
  createPatient: (body) => request('/patients', { method: 'POST', body }),
  getPatient: (id) => request(`/patients/${encodeURIComponent(id)}`),

  // pharmacogenomics: POST /pgx/check { drugs[], state, ethnicity, sex, age, known_genotypes, lang }
  pgxCheck: (body) => request('/pgx/check', { method: 'POST', body }),
  pgxCoverage: () => request('/pgx/coverage'),
  pgxAlleleFreqs: (params = '') => request(`/pgx/allele-frequencies${params}`),

  // reproductive: POST /reproductive/couple-risk { partner_a: PartnerIn, partner_b: PartnerIn, lang }
  counsel: (body) => request('/reproductive/couple-risk', { method: 'POST', body }),
  counselConditions: () => request('/reproductive/conditions'),

  // dashboard
  national: (month) =>
    request(month ? `/dashboard/national?month=${encodeURIComponent(month)}` : '/dashboard/national'),
  policyBrief: () => request('/dashboard/policy-brief', { method: 'POST' }),
  researchGap: () => request('/dashboard/research-gap'),

  // continuous learning
  learningQueue: () => request('/learning/queue'),
  learningDrift: () => request('/learning/drift'),
  kgProposals: (body) => request('/learning/kg-proposals', { method: 'POST', body }),

  // federated learning
  federatedArchetypes: () => request('/federated/archetypes'),
  federatedSimulate: (rounds = 8) =>
    request(`/federated/simulate?rounds=${rounds}`, { method: 'POST' }),

  // triage / ASHA
  triageQuestionnaire: () => request('/triage/questionnaire'),
  triageText: (body) => request('/triage/text', { method: 'POST', body }),

  // EMR / FHIR
  fhirMetadata: () => request('/emr/fhir/metadata'),

  // platform status
  platformStatus: () => request('/platform/status'),
}
