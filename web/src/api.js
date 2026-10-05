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
      if (detail && typeof detail === 'object' && !Array.isArray(detail)) detail = detail.message || JSON.stringify(detail)
      else if (Array.isArray(detail)) detail = detail.map((d) => d.msg || JSON.stringify(d)).join('; ')
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
  kgTypes: () => request('/kg/types'),
  kgSearch: (p) => request(`/kg/search?${new URLSearchParams(Object.entries(p).filter(([, v]) => v !== '' && v != null))}`),
  kgNode: (key) => request(`/kg/node?${new URLSearchParams({ key })}`),
  kgNeighborhood: (p) => request(`/kg/neighborhood?${new URLSearchParams(Object.entries(p).filter(([, v]) => v !== '' && v != null))}`),
  kgPath: (p) => request(`/kg/path?${new URLSearchParams(p)}`),
  kgCase: (pid) => request(`/kg/case/${encodeURIComponent(pid)}`),

  // clinical
  ner: (body) => request('/clinical/extract', { method: 'POST', body }),
  mapHpo: (body) => request('/clinical/hpo-map', { method: 'POST', body }),
  reference: () => request('/reference'),

  // phenotype intelligence (Phase 7)
  phenoSearch: (q) => request(`/phenotype/search?q=${encodeURIComponent(q)}`),
  phenoTerm: (id, pid) => request(`/phenotype/term/${encodeURIComponent(id)}${pid ? `?patient_id=${encodeURIComponent(pid)}` : ''}`),
  phenoCase: (pid) => request(`/phenotype/case/${encodeURIComponent(pid)}`),
  phenoCompare: (pid, did) => request(`/phenotype/case/${encodeURIComponent(pid)}/compare?disease_id=${encodeURIComponent(did)}`),
  phenoImport: (pid, items) => request(`/phenotype/case/${encodeURIComponent(pid)}/import`, { method: 'POST', body: { items } }),

  // diagnosis intelligence (Phase 8)
  dxCase: (pid) => request(`/dx/case/${encodeURIComponent(pid)}`),
  dxWhy: (pid, did) => request(`/dx/case/${encodeURIComponent(pid)}/why?disease_id=${encodeURIComponent(did)}`),
  dxMatrix: (pid) => request(`/dx/case/${encodeURIComponent(pid)}/matrix`),
  dxDiscriminating: (pid) => request(`/dx/case/${encodeURIComponent(pid)}/discriminating`),
  dxWhatIf: (pid, body) => request(`/dx/case/${encodeURIComponent(pid)}/whatif`, { method: 'POST', body }),

  // patients
  listPatients: () => request('/patients'),
  createPatient: (body) => request('/patients', { method: 'POST', body }),
  getPatient: (id) => request(`/patients/${encodeURIComponent(id)}`),

  // pharmacogenomics: POST /pgx/check { drugs[], state, ethnicity, sex, age, known_genotypes, lang }
  pgxCheck: (body) => request('/pgx/check', { method: 'POST', body }),
  pgxCase: (pid) => request(`/pgx/case/${encodeURIComponent(pid)}`),
  reproMembers: (pid) => request(`/repro/case/${encodeURIComponent(pid)}/members`),
  reproCase: (pid, a, b) => request(`/repro/case/${encodeURIComponent(pid)}${a && b ? `?partner_a=${encodeURIComponent(a)}&partner_b=${encodeURIComponent(b)}` : ''}`),
  reproPunnett: (parent_a, parent_b) => request('/repro/punnett', { method: 'POST', body: { parent_a, parent_b } }),
  reproMonteCarlo: (pid, body) => request(`/repro/case/${encodeURIComponent(pid)}/montecarlo`, { method: 'POST', body }),
  reproScenario: (pid, body) => request(`/repro/case/${encodeURIComponent(pid)}/scenario`, { method: 'POST', body }),
  reproExplain: (pid, disease_id) => request(`/repro/case/${encodeURIComponent(pid)}/explain?disease_id=${encodeURIComponent(disease_id)}`),
  reportSections: () => request('/reports/sections'),
  reportGenerate: (pid, sections) => request(`/reports/case/${encodeURIComponent(pid)}`, { method: 'POST', body: { sections } }),
  reportVersions: (pid) => request(`/reports/case/${encodeURIComponent(pid)}`),
  reportGet: (id) => request(`/reports/${encodeURIComponent(id)}`),
  reportRefresh: (id) => request(`/reports/${encodeURIComponent(id)}/refresh`, { method: 'POST' }),
  reportFinalize: (id) => request(`/reports/${encodeURIComponent(id)}/finalize`, { method: 'POST' }),
  pgxCaseDrug: (pid, name) => request(`/pgx/case/${encodeURIComponent(pid)}/drug?name=${encodeURIComponent(name)}`),
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

  // workflow + notifications
  notifList: () => request('/workflow/notifications'),
  notifCount: () => request('/workflow/notifications/count'),
  notifRead: (id) => request(`/workflow/notifications/${encodeURIComponent(id)}/read`, { method: 'POST' }),
  notifReadAll: () => request('/workflow/notifications/read-all', { method: 'POST' }),
  wfGet: (pid) => request(`/workflow/case/${encodeURIComponent(pid)}`),
  wfStatus: (pid, body) => request(`/workflow/case/${encodeURIComponent(pid)}/status`, { method: 'POST', body }),
  wfAssign: (pid, body) => request(`/workflow/case/${encodeURIComponent(pid)}/assign`, { method: 'POST', body }),

  // community referrals
  refCreateText: (body) => request('/community/referrals/from-text', { method: 'POST', body }),
  refList: () => request('/community/referrals'),
  refSummary: () => request('/community/summary'),
  refFollowUp: (id, body) => request(`/community/referrals/${encodeURIComponent(id)}/followup`, { method: 'POST', body }),
  refHandoff: (id, body) => request(`/community/referrals/${encodeURIComponent(id)}/handoff`, { method: 'POST', body }),

  // EMR / FHIR
  fhirMetadata: () => request('/emr/fhir/metadata'),
  fhirCaseExport: (pid) => request(`/emr/fhir/case/${encodeURIComponent(pid)}`),
  fhirValidate: (body) => request('/emr/fhir/validate', { method: 'POST', body }),
  fhirImportPreview: (body) => request('/emr/fhir/import-preview', { method: 'POST', body }),
  abdmStatus: () => request('/emr/abdm/status'),
  analytics: (section, params = {}) => {
    const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '')).toString()
    return request(`/analytics/${section}${qs ? `?${qs}` : ''}`)
  },
  searchGlobal: (q, types) => request(`/search?q=${encodeURIComponent(q)}${types ? `&types=${types}` : ''}`),

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

  // clinical text NLP (Phase 5)
  nlpAnalyze: (body) => request('/nlp/analyze', { method: 'POST', body }),
  nlpNormalize: (phrases, top_k = 3) => request('/nlp/normalize', { method: 'POST', body: { phrases, top_k } }),
  nlpCapabilities: () => request('/nlp/capabilities'),

  // evidence & literature (Phase 4)
  evidenceSources: () => request('/evidence/sources'),
  evidenceSearch: (params) => request(`/evidence/search?${new URLSearchParams(Object.entries(params).filter(([, v]) => v !== '' && v != null))}`),
  evidencePmid: (pmid) => request(`/evidence/pmid/${encodeURIComponent(pmid)}`),
  evidenceVariant: (aid, vid, page = 1) => request(`/evidence/variant/${encodeURIComponent(aid)}?variant_id=${encodeURIComponent(vid)}&page=${page}`),
  evidenceCase: (cid) => request(`/evidence/case/${encodeURIComponent(cid)}`),
  evidenceSave: (cid, body) => request(`/evidence/case/${encodeURIComponent(cid)}`, { method: 'POST', body }),
  evidencePatch: (cid, eid, body) => request(`/evidence/case/${encodeURIComponent(cid)}/${encodeURIComponent(eid)}`, { method: 'PATCH', body }),
  evidenceDelete: (cid, eid) => request(`/evidence/case/${encodeURIComponent(cid)}/${encodeURIComponent(eid)}`, { method: 'DELETE' }),
  evidenceReport: (cid) => request(`/evidence/case/${encodeURIComponent(cid)}/report`),

  // pedigree & inheritance (Phase 3E)
  pedigree: (cid) => request(`/pedigree/${encodeURIComponent(cid)}`),
  pedigreeAddMember: (cid, body) => request(`/pedigree/${encodeURIComponent(cid)}/members`, { method: 'POST', body }),
  pedigreePatchMember: (cid, mid, body) => request(`/pedigree/${encodeURIComponent(cid)}/members/${encodeURIComponent(mid)}`, { method: 'PATCH', body }),
  pedigreeDeleteMember: (cid, mid) => request(`/pedigree/${encodeURIComponent(cid)}/members/${encodeURIComponent(mid)}`, { method: 'DELETE' }),
  pedigreeSetProband: (cid, mid) => request(`/pedigree/${encodeURIComponent(cid)}/members/${encodeURIComponent(mid)}/proband`, { method: 'POST' }),
  pedigreeSetPhenotypes: (cid, mid, hpo_ids) => request(`/pedigree/${encodeURIComponent(cid)}/members/${encodeURIComponent(mid)}/phenotypes`, { method: 'PUT', body: { hpo_ids } }),
  pedigreeAddRelationship: (cid, body) => request(`/pedigree/${encodeURIComponent(cid)}/relationships`, { method: 'POST', body }),
  pedigreeDeleteRelationship: (cid, rid) => request(`/pedigree/${encodeURIComponent(cid)}/relationships/${encodeURIComponent(rid)}`, { method: 'DELETE' }),
  pedigreeSetGenotype: (cid, mid, body) => request(`/pedigree/${encodeURIComponent(cid)}/members/${encodeURIComponent(mid)}/genotypes`, { method: 'POST', body }),
  pedigreeDeleteGenotype: (cid, mid, vkey) => request(`/pedigree/${encodeURIComponent(cid)}/members/${encodeURIComponent(mid)}/genotypes/${encodeURIComponent(vkey)}`, { method: 'DELETE' }),
  pedigreeImportGenotypes: (cid, mid, body) => request(`/pedigree/${encodeURIComponent(cid)}/members/${encodeURIComponent(mid)}/genotypes/import`, { method: 'POST', body }),
  pedigreeAnalysis: (cid, vkey) => request(`/pedigree/${encodeURIComponent(cid)}/analysis?variant_key=${encodeURIComponent(vkey)}`),
  pedigreeOverview: (cid) => request(`/pedigree/${encodeURIComponent(cid)}/overview`),
  pedigreePrioritization: (cid) => request(`/pedigree/${encodeURIComponent(cid)}/prioritization`),
  pedigreeReproductive: (cid, a, b) => request(`/pedigree/${encodeURIComponent(cid)}/reproductive-context${a && b ? `?partner_a=${encodeURIComponent(a)}&partner_b=${encodeURIComponent(b)}` : ''}`),
  pedigreeDemoFamily: (cid) => request(`/pedigree/${encodeURIComponent(cid)}/demo-family`, { method: 'POST' }),
  pedigreeHpoSearch: (q) => request(`/pedigree/hpo-search?q=${encodeURIComponent(q)}`),

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

// Authenticated analytics export (CSV / JSON), generated and authorised by the backend.
export async function downloadAnalytics(section, format, range = {}) {
  const token = getToken()
  const qs = new URLSearchParams({ section, format, ...(range.from ? { from: range.from } : {}), ...(range.to ? { to: range.to } : {}) })
  const res = await fetch(`/api/v1/analytics/export?${qs}`, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
  if (!res.ok) throw new Error(res.status === 403 ? 'Your role may not export analytics.' : `Export failed (${res.status})`)
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `genomera_${section.replace(':', '_')}.${format}`
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
  return blob.size
}

// Authenticated binary download (PDF / JSON export) - the file is produced by the backend, never in the browser.
export async function downloadReport(reportId, kind) {
  const token = getToken()
  const res = await fetch(`/api/v1/reports/${encodeURIComponent(reportId)}/${kind}`, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
  if (!res.ok) throw new Error(`Download failed (${res.status})`)
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${reportId}.${kind}`
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
  return blob.size
}
