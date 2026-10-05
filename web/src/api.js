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

export async function uploadVcfFile(formData) {
  const headers = {}
  const token = getToken()
  if (token) headers['Authorization'] = `Bearer ${token}`
  const res = await fetch('/api/v1/variants/upload', {
    method: 'POST',
    headers,
    body: formData,
  })
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

  // variants / ACMG intelligence
  listVariantAnalyses: () => request('/variants/analyses'),
  getVariantAnalysis: (id) => request(`/variants/analyses/${encodeURIComponent(id)}`),
  getVariantDetail: (analysisId, variantId) =>
    request(`/variants/analyses/${encodeURIComponent(analysisId)}/variants/${encodeURIComponent(variantId)}`),
  getDemoVcf: () => request('/variants/demo-vcf'),
  handoffToDiagnosis: (analysisId, body) =>
    request(`/variants/analyses/${encodeURIComponent(analysisId)}/diagnosis-handoff`, { method: 'POST', body }),
  handoffToReport: (analysisId, body) =>
    request(`/variants/analyses/${encodeURIComponent(analysisId)}/report-handoff`, { method: 'POST', body }),

  // assistant / clinical copilot
  assistantChat: (body) => request('/assistant/chat', { method: 'POST', body }),
  getAssistantConversation: (id) => request(`/assistant/conversations/${encodeURIComponent(id)}`),
  clearAssistantConversation: (id) => request(`/assistant/conversations/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  getAssistantContext: (params = '') => request(`/assistant/context${params}`),

  // digital twin (Phase 3D)
  twin: (pid, analysisId) =>
    request(`/digital-twin/${encodeURIComponent(pid)}${analysisId ? `?analysis_id=${encodeURIComponent(analysisId)}` : ''}`),
  twinTimeline: (pid) => request(`/digital-twin/${encodeURIComponent(pid)}/timeline`),
  twinSaveSnapshot: (pid, analysisId) =>
    request(`/digital-twin/${encodeURIComponent(pid)}/snapshot${analysisId ? `?analysis_id=${encodeURIComponent(analysisId)}` : ''}`, { method: 'POST' }),
  twinSnapshots: (pid) => request(`/digital-twin/${encodeURIComponent(pid)}/snapshots`),
  twinCreateScenario: (pid, body) =>
    request(`/digital-twin/${encodeURIComponent(pid)}/scenarios`, { method: 'POST', body }),
  twinScenarios: (pid) => request(`/digital-twin/${encodeURIComponent(pid)}/scenarios`),
  twinScenario: (pid, sid) =>
    request(`/digital-twin/${encodeURIComponent(pid)}/scenarios/${encodeURIComponent(sid)}`),
  twinDeleteScenario: (pid, sid) =>
    request(`/digital-twin/${encodeURIComponent(pid)}/scenarios/${encodeURIComponent(sid)}`, { method: 'DELETE' }),
  twinReportHandoff: (pid, body) =>
    request(`/digital-twin/${encodeURIComponent(pid)}/report-handoff`, { method: 'POST', body }),

  // platform status
  platformStatus: () => request('/platform/status'),
}

export async function streamAssistantChat(payload, onChunk, onCitations, onDone, onError) {
  const token = getToken()
  const headers = { 'Content-Type': 'application/json' }
  if (token) headers['Authorization'] = `Bearer ${token}`

  try {
    const res = await fetch('/api/v1/assistant/chat/stream', {
      method: 'POST',
      headers,
      body: JSON.stringify(payload),
    })

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

    const reader = res.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let buffer = ''

    while (true) {
      const { value, done } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() // retain trailing partial line

      for (const line of lines) {
        const trimmed = line.trim()
        if (trimmed.startsWith('data: ')) {
          const jsonStr = trimmed.slice(6).trim()
          try {
            const data = JSON.parse(jsonStr)
            if (data.type === 'content' && onChunk) {
              onChunk(data.delta)
            } else if (data.type === 'citations' && onCitations) {
              onCitations(data.citations, data.context_summary)
            } else if (data.type === 'done' && onDone) {
              onDone(data.citations)
            }
          } catch {
            /* ignore individual malformed frame */
          }
        }
      }
    }
  } catch (err) {
    if (onError) onError(err)
    else console.error('Streaming error:', err)
  }
}


// ---------------------------------------------------------------------------
// Cross-view navigation context. Views are routed by hash only, so a view that
// wants to open another one *at a specific record* leaves a one-shot hint here.
// The target view calls consumeNavContext(<its route>) on mount.
// ---------------------------------------------------------------------------
const NAV_KEY = 'genomera_nav_context'

export function setNavContext(target, context) {
  try {
    sessionStorage.setItem(NAV_KEY, JSON.stringify({ target, context, ts: Date.now() }))
  } catch {
    /* storage unavailable: navigation still works, just without preselection */
  }
}

export function consumeNavContext(target) {
  try {
    const raw = sessionStorage.getItem(NAV_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (parsed.target !== target) return null
    sessionStorage.removeItem(NAV_KEY)
    return parsed.context || null
  } catch {
    return null
  }
}
