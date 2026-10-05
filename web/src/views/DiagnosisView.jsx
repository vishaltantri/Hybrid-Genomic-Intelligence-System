import React, { useEffect, useState } from 'react'
import { api, consumeNavContext } from '../api.js'
import {
  Stethoscope,
  Sparkles,
  Search,
  CheckCircle2,
  AlertTriangle,
  Info,
  ChevronRight,
  ChevronDown,
  Dna,
  TestTube,
  Building2,
  TrendingUp,
  FileText,
  HelpCircle,
  Layers,
  ArrowRight,
  ExternalLink,
  Code2,
} from 'lucide-react'
import { PageHeader } from '../components/ui/PageHeader.jsx'
import { ClinicalCard } from '../components/ui/ClinicalCard.jsx'
import { StatusBadge, SeverityBadge, ConfidenceBadge } from '../components/ui/StatusBadge.jsx'
import { ScoreBar } from '../components/ui/ScoreBar.jsx'
import { ErrorAlert } from '../components/ui/ErrorAlert.jsx'
import { SkeletonCard } from '../components/ui/LoadingSkeleton.jsx'
import { EmptyState } from '../components/ui/EmptyState.jsx'

const QUICK_CASES = [
  {
    label: 'Case 1: Wilson Disease (Hinglish)',
    text: '6 mahine se pet kharab, aankhon mein brown ring, chalna mushkil ho gaya',
    state: 'Andhra Pradesh',
    community: '',
    sex: 'M',
  },
  {
    label: 'Case 2: Spinal Muscular Atrophy',
    text: 'Floppy infant, progressive symmetrical proximal muscle weakness, hypotonia, tongue fasciculations, absent deep tendon reflexes',
    state: 'Tamil Nadu',
    community: '',
    sex: 'F',
  },
  {
    label: 'Case 3: Gaucher Disease Type 1',
    text: 'Massive splenomegaly, hepatomegaly, bone pain crises, thrombocytopenia, easy bruising, anemia, Erlenmeyer flask deformity',
    state: 'Gujarat',
    community: '',
    sex: 'M',
  },
]

export default function DiagnosisView() {
  const [text, setText] = useState(QUICK_CASES[0].text)
  const [state, setState] = useState(QUICK_CASES[0].state)
  const [community, setCommunity] = useState('')
  const [sex, setSex] = useState(QUICK_CASES[0].sex)
  const [states, setStates] = useState([])
  const [communities, setCommunities] = useState([])
  const [res, setRes] = useState(null)
  const [mapped, setMapped] = useState(null)
  const [xai, setXai] = useState(null)
  const [detail, setDetail] = useState(null)
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)
  const [activeTab, setActiveTab] = useState('cards') // 'cards' | 'matrix'
  const [showRawJson, setShowRawJson] = useState(false)

  // Prefill from the Digital Twin (one-shot): the patient's documented phenotypes and demographics
  useEffect(() => {
    const ctx = consumeNavContext('diagnosis')
    if (!ctx) return
    if (ctx.text) setText(ctx.text)
    if (ctx.state) setState(ctx.state)
    if (ctx.community) setCommunity(ctx.community)
    if (ctx.sex) setSex(ctx.sex)
  }, [])

  useEffect(() => {
    api.reference()
      .then((r) => {
        setStates(r.states || [])
        setCommunities(r.communities || [])
      })
      .catch(() => {})
  }, [])

  async function run() {
    if (!text.trim()) return
    setBusy(true)
    setErr(null)
    setRes(null)
    setXai(null)
    setDetail(null)
    setMapped(null)

    try {
      const body = { text, state, community, sex, top_k: 10 }
      try {
        const m = await api.mapHpo({ text })
        setMapped(m)
      } catch {
        /* HPO mapping non-fatal */
      }

      const r = await api.diagnose(body)
      setRes(r)

      if (r.results?.length) {
        try {
          const x = await api.explain({ ...body, top_k: 5 })
          setXai(x)
        } catch {
          /* XAI non-fatal */
        }
      }
    } catch (ex) {
      setErr(ex.message)
    } finally {
      setBusy(false)
    }
  }

  async function openDisease(id) {
    setErr(null)
    try {
      const d = await api.diseaseDetail(id)
      setDetail(d)
    } catch (ex) {
      setErr(ex.message)
    }
  }

  const applyCase = (c) => {
    setText(c.text)
    setState(c.state)
    setCommunity(c.community)
    setSex(c.sex)
  }

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <PageHeader
        title="Differential Diagnosis Engine"
        subtitle="Multi-lingual clinical phenotype matching with India-specific consanguinity & founder population Bayesian re-ranking."
        badge={{
          label: 'AI + Bayesian Population Prior',
          color: 'primary',
          icon: Sparkles,
        }}
      />

      {/* Clinical Input Panel */}
      <ClinicalCard
        title="Patient Presentation & Epidemiological Context"
        subtitle="Enter narrative observations in English, Hindi, or Hinglish. Epidemiological markers calibrate Bayesian prior probabilities."
        icon={Stethoscope}
      >
        <div className="space-y-4">
          {/* Quick Case Presets */}
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[11px] font-semibold text-outline uppercase tracking-wider">
              Quick Cases:
            </span>
            {QUICK_CASES.map((c, i) => (
              <button
                key={i}
                type="button"
                onClick={() => applyCase(c)}
                className="text-xs px-2.5 py-1 rounded-md bg-surface-container-low hover:bg-surface-container border border-outline-variant/40 text-on-surface-variant hover:text-primary transition-colors font-medium"
              >
                {c.label}
              </button>
            ))}
          </div>

          {/* Narrative Symptoms Textarea */}
          <div>
            <label className="block text-xs font-bold text-on-surface uppercase tracking-wider mb-1.5">
              Clinical Findings / Symptoms (English / Hindi / Hinglish)
            </label>
            <textarea
              rows={3}
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="e.g., 6 mahine se pet kharab, aankhon mein brown ring, chalna mushkil ho gaya..."
              className="w-full p-3 rounded-xl bg-surface-container-low/50 border border-outline-variant/60 text-sm text-on-surface placeholder:text-outline focus:outline-none focus:border-primary focus:bg-white transition-all shadow-inner font-sans"
            />
          </div>

          {/* Demographic & Consanguinity Selectors */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div>
              <label className="block text-xs font-semibold text-on-surface-variant mb-1">
                State (Consanguinity Prior)
              </label>
              <select
                value={state}
                onChange={(e) => setState(e.target.value)}
                className="w-full h-10 px-3 rounded-lg bg-surface-container-low border border-outline-variant/60 text-xs text-on-surface focus:outline-none focus:border-primary font-medium"
              >
                <option value="">Not stated (National default)</option>
                {states.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name} {s.consanguinity_rate ? `(${s.consanguinity_rate}%)` : ''}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-xs font-semibold text-on-surface-variant mb-1">
                Community (Founder Effect)
              </label>
              <select
                value={community}
                onChange={(e) => setCommunity(e.target.value)}
                className="w-full h-10 px-3 rounded-lg bg-surface-container-low border border-outline-variant/60 text-xs text-on-surface focus:outline-none focus:border-primary font-medium"
              >
                <option value="">Not stated</option>
                {communities.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-xs font-semibold text-on-surface-variant mb-1">
                Biological Sex
              </label>
              <select
                value={sex}
                onChange={(e) => setSex(e.target.value)}
                className="w-full h-10 px-3 rounded-lg bg-surface-container-low border border-outline-variant/60 text-xs text-on-surface focus:outline-none focus:border-primary font-medium"
              >
                <option value="">Unspecified</option>
                <option value="M">Male (XY)</option>
                <option value="F">Female (XX)</option>
              </select>
            </div>
          </div>

          {/* Action Row */}
          <div className="flex items-center justify-between pt-2 border-t border-outline-variant/30">
            <span className="text-[11px] text-outline">
              Analysis incorporates Human Phenotype Ontology (HPO) & Indian allele priors
            </span>
            <button
              onClick={run}
              disabled={busy || !text.trim()}
              className="px-5 py-2.5 rounded-lg bg-primary text-white text-xs font-bold hover:bg-primary-hover disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-sm flex items-center gap-2"
            >
              {busy ? (
                <>
                  <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  <span>Analyzing Phenotypes…</span>
                </>
              ) : (
                <>
                  <Sparkles size={15} />
                  <span>Run Differential Diagnosis</span>
                </>
              )}
            </button>
          </div>
        </div>
      </ClinicalCard>

      {/* Error Alert */}
      {err && <ErrorAlert error={err} onRetry={run} />}

      {/* Loading Skeletons */}
      {busy && (
        <div className="space-y-4">
          <SkeletonCard />
          <SkeletonCard />
        </div>
      )}

      {/* NER HPO Mapping Results */}
      {mapped && !busy && (
        <div className="p-4 rounded-xl bg-white border border-outline-variant/40 shadow-xs space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-secondary"></span>
              <span className="text-xs font-bold text-on-surface uppercase tracking-wider">
                Clinical NLP Entity Extraction (Understood HPO Terms)
              </span>
            </div>
            <span className="text-[11px] font-mono text-outline">
              HPO Extractor: {mapped.language_detected || 'Multilingual NER'}
            </span>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {mapped.hpo_profile?.length ? (
              mapped.hpo_profile.map((h, i) => (
                <div
                  key={i}
                  className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-surface-container-low border border-outline-variant/50 text-xs"
                >
                  <span className="font-semibold text-primary">
                    {h.hpo_name || h.hpo_id}
                  </span>
                  <span className="text-[10px] font-mono text-outline">
                    {h.hpo_id}
                  </span>
                  {h.confidence != null && (
                    <ConfidenceBadge confidence={h.confidence} />
                  )}
                </div>
              ))
            ) : (
              <span className="text-xs text-outline italic">
                No standard phenotypes mapped. Try describing clinical terms (e.g. “piliya”, “daure”, “ataxia”).
              </span>
            )}
          </div>

          {mapped.unmapped_symptoms?.length > 0 && (
            <div className="pt-2 border-t border-outline-variant/30 text-xs text-amber-700 flex items-center gap-1.5">
              <AlertTriangle size={14} className="shrink-0" />
              <span>Unmapped colloquial tokens:</span>
              <span className="font-mono">{mapped.unmapped_symptoms.join(', ')}</span>
            </div>
          )}
        </div>
      )}

      {/* Results Section */}
      {res?.results?.length > 0 && !busy && (
        <div className="space-y-6">
          {/* Engine Header Info */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-3.5 rounded-xl bg-surface-container-low border border-outline-variant/40">
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-primary"></span>
              <span className="text-xs font-bold text-on-surface">
                Differential Results ({res.results.length} Candidates Ranked)
              </span>
              <span className="text-[11px] text-outline">
                · Engine: {res.engine || 'Bayesian Phenotype Prior'}
              </span>
            </div>

            {/* View Mode Toggle */}
            <div className="flex items-center gap-1 p-0.5 rounded-lg bg-surface-container-high border border-outline-variant/30 text-xs">
              <button
                onClick={() => setActiveTab('cards')}
                className={`px-3 py-1 rounded-md font-semibold transition-colors ${
                  activeTab === 'cards'
                    ? 'bg-white text-primary shadow-xs'
                    : 'text-on-surface-variant hover:text-on-surface'
                }`}
              >
                Ranked Cards
              </button>
              <button
                onClick={() => setActiveTab('matrix')}
                className={`px-3 py-1 rounded-md font-semibold transition-colors ${
                  activeTab === 'matrix'
                    ? 'bg-white text-primary shadow-xs'
                    : 'text-on-surface-variant hover:text-on-surface'
                }`}
              >
                Differential Matrix
              </button>
            </div>
          </div>

          {/* Primary Diagnosis Highlight (#1) */}
          {res.results[0] && (
            <div className="p-6 rounded-2xl bg-gradient-to-br from-white to-primary-container/10 border-2 border-primary/30 shadow-md space-y-5">
              <div className="flex flex-col md:flex-row md:items-start justify-between gap-4">
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="px-2 py-0.5 rounded-full bg-primary text-white text-[11px] font-bold uppercase tracking-wider">
                      PRIMARY SUSPECT #1
                    </span>
                    <span className="text-xs font-mono font-semibold text-outline">
                      {res.results[0].disease_id}
                    </span>
                    {res.results[0].inheritance && (
                      <span className="px-2 py-0.5 rounded-md bg-surface-container-high text-on-surface-variant text-[11px] font-medium border border-outline-variant/40">
                        {res.results[0].inheritance}
                      </span>
                    )}
                  </div>
                  <h3 className="text-xl lg:text-2xl font-bold text-on-surface">
                    {res.results[0].disease_name}
                  </h3>
                  {res.results[0].genes?.length > 0 && (
                    <div className="flex items-center gap-1.5 text-xs text-primary font-mono pt-1">
                      <Dna size={14} />
                      <span>Associated Genes: {res.results[0].genes.join(', ')}</span>
                    </div>
                  )}
                </div>

                {/* Probability Score Pill */}
                <div className="flex flex-col items-start md:items-end p-3 rounded-xl bg-white border border-primary/20 shadow-xs min-w-[180px]">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-outline">
                    Posterior Probability
                  </span>
                  <div className="text-2xl font-bold font-mono text-primary">
                    {(res.results[0].probability * 100).toFixed(1)}%
                  </div>
                  <div className="w-full mt-1.5">
                    <ScoreBar
                      score={res.results[0].probability}
                      showPercentage={false}
                      color="primary"
                      size="sm"
                    />
                  </div>
                  {res.results[0].probability_ci && (
                    <span className="text-[10px] font-mono text-outline mt-1">
                      95% CI: {(res.results[0].probability_ci[0] * 100).toFixed(1)}%–
                      {(res.results[0].probability_ci[1] * 100).toFixed(1)}%
                    </span>
                  )}
                </div>
              </div>

              {/* India-Specific Population Prior Re-ranking Info */}
              {res.results[0].population_prior && (
                <div className="p-3.5 rounded-xl bg-surface-container-low border border-outline-variant/40 text-xs space-y-2">
                  <div className="flex items-center gap-2 font-bold text-on-surface">
                    <TrendingUp size={15} className="text-secondary" />
                    <span>India Epidemiological Weighting</span>
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-xs">
                    <div className="p-2 rounded-lg bg-white border border-outline-variant/30">
                      <div className="text-[10px] text-outline uppercase font-semibold">
                        Base Prevalence
                      </div>
                      <div className="font-mono font-bold text-on-surface">
                        {res.results[0].population_prior.prevalence_per_100k ?? '—'} / 100k
                      </div>
                    </div>
                    <div className="p-2 rounded-lg bg-white border border-outline-variant/30">
                      <div className="text-[10px] text-outline uppercase font-semibold">
                        Consanguinity Multiplier
                      </div>
                      <div className="font-mono font-bold text-secondary">
                        ×{res.results[0].population_prior.consanguinity_multiplier ?? 1.0}
                      </div>
                    </div>
                    <div className="p-2 rounded-lg bg-white border border-outline-variant/30">
                      <div className="text-[10px] text-outline uppercase font-semibold">
                        Founder Effect Multiplier
                      </div>
                      <div className="font-mono font-bold text-secondary">
                        ×{res.results[0].population_prior.founder_multiplier ?? 1.0}
                      </div>
                    </div>
                  </div>
                  {res.results[0].population_prior.india_notes?.length > 0 && (
                    <div className="text-[11px] text-on-surface-variant">
                      {res.results[0].population_prior.india_notes.join(' · ')}
                    </div>
                  )}
                </div>
              )}

              {/* Confirmatory Tests & Referral Protocol */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* Tests */}
                <div className="p-4 rounded-xl bg-white border border-outline-variant/40 space-y-2.5">
                  <div className="flex items-center gap-1.5 text-xs font-bold text-on-surface">
                    <TestTube size={15} className="text-primary" />
                    <span>Recommended Confirmatory Testing Protocol</span>
                  </div>
                  {res.results[0].confirmatory_tests?.first_line?.length > 0 && (
                    <div>
                      <span className="text-[10px] font-bold uppercase tracking-wider text-outline block">
                        First-Line Diagnostic Tests:
                      </span>
                      <ul className="mt-1 space-y-1">
                        {res.results[0].confirmatory_tests.first_line.map((t, idx) => (
                          <li
                            key={idx}
                            className="text-xs text-on-surface flex items-start gap-1.5"
                          >
                            <CheckCircle2 size={13} className="text-secondary shrink-0 mt-0.5" />
                            <span>{t}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {res.results[0].confirmatory_tests?.genetic && (
                    <div className="pt-2 border-t border-outline-variant/30 text-xs">
                      <span className="text-[10px] font-bold uppercase tracking-wider text-outline block">
                        Target Molecular Testing:
                      </span>
                      <span className="font-medium text-primary">
                        {res.results[0].confirmatory_tests.genetic}
                      </span>
                    </div>
                  )}
                  {res.results[0].confirmatory_tests?.india_note && (
                    <div className="text-[11px] text-on-surface-variant italic pt-1">
                      Note: {res.results[0].confirmatory_tests.india_note}
                    </div>
                  )}
                </div>

                {/* Referrals & Specialist Labs */}
                <div className="p-4 rounded-xl bg-white border border-outline-variant/40 space-y-2.5">
                  <div className="flex items-center gap-1.5 text-xs font-bold text-on-surface">
                    <Building2 size={15} className="text-secondary" />
                    <span>Specialist Referral Pathways</span>
                  </div>
                  {res.results[0].referral?.specialists?.length > 0 && (
                    <div>
                      <span className="text-[10px] font-bold uppercase tracking-wider text-outline block">
                        Recommended Specialties:
                      </span>
                      <div className="flex flex-wrap gap-1.5 mt-1">
                        {res.results[0].referral.specialists.map((sp, idx) => (
                          <span
                            key={idx}
                            className="px-2 py-0.5 rounded-md bg-secondary-container/20 text-secondary text-xs font-medium border border-secondary/20"
                          >
                            {sp}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                  {res.results[0].referral?.labs?.length > 0 && (
                    <div className="pt-2 border-t border-outline-variant/30">
                      <span className="text-[10px] font-bold uppercase tracking-wider text-outline block">
                        Accredited Indian Reference Centers:
                      </span>
                      <div className="text-xs text-on-surface-variant mt-1 space-y-0.5">
                        {res.results[0].referral.labs.map((lb, idx) => (
                          <div key={idx} className="flex items-center gap-1">
                            <span className="w-1.5 h-1.5 rounded-full bg-outline"></span>
                            <span>{lb}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>

              {/* Action Buttons */}
              <div className="flex items-center justify-between pt-2">
                <button
                  onClick={() => openDisease(res.results[0].disease_id)}
                  className="text-xs font-bold text-primary hover:text-primary-hover flex items-center gap-1"
                >
                  <span>Inspect Full Disease Profile & Phenotypes</span>
                  <ArrowRight size={14} />
                </button>
              </div>
            </div>
          )}

          {/* Cards View for Remaining Candidates */}
          {activeTab === 'cards' && res.results.length > 1 && (
            <div className="space-y-3">
              <h4 className="text-xs font-bold text-outline uppercase tracking-wider">
                Differential Candidates (#2 – #{res.results.length})
              </h4>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {res.results.slice(1).map((r, i) => (
                  <div
                    key={r.disease_id}
                    className="p-4 rounded-xl bg-white border border-outline-variant/40 hover:border-primary/40 transition-all shadow-xs space-y-3 flex flex-col justify-between"
                  >
                    <div className="space-y-2">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span className="w-5 h-5 rounded-full bg-surface-container-high flex items-center justify-center text-[10px] font-bold text-on-surface-variant">
                            #{i + 2}
                          </span>
                          <span className="text-xs font-mono text-outline">
                            {r.disease_id}
                          </span>
                        </div>
                        {r.inheritance && (
                          <span className="text-[10px] px-2 py-0.5 rounded bg-surface-container-low text-on-surface-variant border border-outline-variant/30">
                            {r.inheritance}
                          </span>
                        )}
                      </div>

                      <h5 className="font-bold text-sm text-on-surface line-clamp-1">
                        {r.disease_name}
                      </h5>

                      <div className="space-y-1">
                        <div className="flex items-center justify-between text-xs">
                          <span className="text-outline text-[11px]">Match Probability:</span>
                          <span className="font-mono font-bold text-primary">
                            {(r.probability * 100).toFixed(1)}%
                          </span>
                        </div>
                        <ScoreBar score={r.probability} showPercentage={false} size="sm" />
                      </div>

                      {/* Confirmatory Tests Snippet */}
                      {r.confirmatory_tests?.first_line?.length > 0 && (
                        <div className="text-[11px] text-on-surface-variant line-clamp-1">
                          <span className="text-outline font-medium">Tests: </span>
                          {r.confirmatory_tests.first_line.join(', ')}
                        </div>
                      )}
                    </div>

                    <div className="pt-2 border-t border-outline-variant/30 flex items-center justify-between">
                      <span className="text-[10px] text-outline">
                        {r.genes?.length ? `Genes: ${r.genes.join(', ')}` : ''}
                      </span>
                      <button
                        onClick={() => openDisease(r.disease_id)}
                        className="text-xs font-semibold text-primary hover:text-primary-hover flex items-center gap-1"
                      >
                        <span>Evidence</span>
                        <ChevronRight size={14} />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Comparative Matrix View */}
          {activeTab === 'matrix' && (
            <div className="overflow-x-auto rounded-xl border border-outline-variant/40 bg-white shadow-xs">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="bg-surface-container-low text-on-surface-variant border-b border-outline-variant/40 font-semibold uppercase tracking-wider text-[10px]">
                    <th className="p-3 w-12 text-center">#</th>
                    <th className="p-3">Candidate Disease</th>
                    <th className="p-3 w-40">Posterior Probability</th>
                    <th className="p-3">Inheritance</th>
                    <th className="p-3">India Factors</th>
                    <th className="p-3">Confirmatory Tests</th>
                    <th className="p-3 text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-outline-variant/20">
                  {res.results.map((r, i) => (
                    <tr
                      key={r.disease_id}
                      className="hover:bg-surface-container-low/50 transition-colors"
                    >
                      <td className="p-3 text-center font-bold text-outline">
                        {i + 1}
                      </td>
                      <td className="p-3">
                        <div className="font-bold text-on-surface">{r.disease_name}</div>
                        <div className="text-[10px] font-mono text-outline">{r.disease_id}</div>
                      </td>
                      <td className="p-3">
                        <div className="font-mono font-bold text-primary mb-1">
                          {(r.probability * 100).toFixed(1)}%
                        </div>
                        <ScoreBar score={r.probability} showPercentage={false} size="sm" />
                      </td>
                      <td className="p-3 text-on-surface-variant">
                        {r.inheritance || '—'}
                      </td>
                      <td className="p-3 text-[11px] text-on-surface-variant">
                        {r.population_prior?.consanguinity_multiplier !== 1 && (
                          <span className="inline-block px-1.5 py-0.5 rounded bg-secondary-container/20 text-secondary font-mono mr-1">
                            consanguinity ×{r.population_prior?.consanguinity_multiplier}
                          </span>
                        )}
                        {r.population_prior?.founder_multiplier !== 1 && (
                          <span className="inline-block px-1.5 py-0.5 rounded bg-secondary-container/20 text-secondary font-mono">
                            founder ×{r.population_prior?.founder_multiplier}
                          </span>
                        )}
                      </td>
                      <td className="p-3 text-[11px] text-on-surface-variant max-w-xs truncate">
                        {r.confirmatory_tests?.first_line?.join(', ') || '—'}
                      </td>
                      <td className="p-3 text-right">
                        <button
                          onClick={() => openDisease(r.disease_id)}
                          className="px-2.5 py-1 rounded bg-surface-container-high hover:bg-primary hover:text-white text-on-surface-variant font-semibold transition-colors"
                        >
                          Details
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Explainable AI (XAI) Attribution Card */}
          {xai?.explanation && (
            <ClinicalCard
              title={`Explainable AI Attribution: Why #${1} — ${xai.explanation.disease_name}?`}
              subtitle={`Attribution method: ${xai.explanation.attribution?.method || 'Integrated Gradients / Bayesian Prior Attribution'}`}
              icon={Sparkles}
              headerBadge={{
                label: 'XAI Audit',
                color: 'secondary',
              }}
            >
              <div className="space-y-5">
                {/* Attribution Breakdown Table */}
                {xai.explanation.attribution?.attributions?.length > 0 && (
                  <div>
                    <h5 className="text-xs font-bold text-on-surface uppercase tracking-wider mb-2">
                      Phenotypic Feature Attributions
                    </h5>
                    <div className="space-y-2">
                      {xai.explanation.attribution.attributions.map((a) => (
                        <div
                          key={a.hpo_id}
                          className="p-2.5 rounded-lg bg-surface-container-low/60 border border-outline-variant/30 flex items-center justify-between gap-4"
                        >
                          <div className="min-w-0 flex-1">
                            <div className="text-xs font-semibold text-on-surface">
                              {a.hpo_name || a.hpo_id}
                            </div>
                            <div className="text-[10px] font-mono text-outline">
                              {a.hpo_id}
                            </div>
                          </div>
                          <div className="w-48 flex items-center gap-3">
                            <div className="flex-1">
                              <ScoreBar
                                score={(a.weight_pct || 0) / 100}
                                showPercentage={false}
                                color="secondary"
                                size="sm"
                              />
                            </div>
                            <span className="text-xs font-mono font-bold text-secondary w-12 text-right">
                              {a.weight_pct ?? '—'}%
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Missing Findings to Raise Certainty */}
                {xai.explanation.missing_findings?.length > 0 && (
                  <div className="p-4 rounded-xl bg-surface-container-low border border-outline-variant/40 space-y-2">
                    <div className="flex items-center gap-1.5 text-xs font-bold text-on-surface">
                      <HelpCircle size={15} className="text-primary" />
                      <span>Missing Findings That Would Raise Diagnostic Certainty</span>
                    </div>
                    <p className="text-[11px] text-on-surface-variant">
                      Clinical verification of these negative or unexamined phenotypes would provide the highest information gain:
                    </p>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-1">
                      {xai.explanation.missing_findings.slice(0, 6).map((m) => (
                        <div
                          key={m.hpo_id}
                          className="p-2 rounded-lg bg-white border border-outline-variant/30 text-xs flex items-center justify-between"
                        >
                          <span className="font-medium text-on-surface">
                            {m.hpo_name || m.hpo_id}
                          </span>
                          <span className="text-[10px] font-mono text-primary font-semibold">
                            {m.would_increase}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Narrative Explanation Markdown */}
                {xai.explanation.narrative?.markdown && (
                  <div className="p-4 rounded-xl bg-surface-container-low/50 border border-outline-variant/40 space-y-2">
                    <div className="flex items-center gap-1.5 text-xs font-bold text-on-surface">
                      <FileText size={15} className="text-primary" />
                      <span>Synthesized Clinical Narrative Explanation</span>
                    </div>
                    <div className="text-xs text-on-surface-variant leading-relaxed whitespace-pre-wrap bg-white p-3.5 rounded-lg border border-outline-variant/30">
                      {xai.explanation.narrative.markdown}
                    </div>
                  </div>
                )}
              </div>
            </ClinicalCard>
          )}

          {/* Disease Deep Profile Detail Card */}
          {detail?.disease && (
            <ClinicalCard
              title={`Disease Profile: ${detail.disease.name}`}
              subtitle={`ID: ${detail.disease.id || detail.disease.disease_id || ''}`}
              icon={Dna}
              actions={
                <button
                  onClick={() => setDetail(null)}
                  className="text-xs text-outline hover:text-on-surface px-2 py-1 rounded"
                >
                  Close
                </button>
              }
            >
              <div className="space-y-4">
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <div className="p-3 rounded-lg bg-surface-container-low border border-outline-variant/30">
                    <span className="text-[10px] font-bold uppercase text-outline">
                      Prevalence
                    </span>
                    <div className="text-sm font-bold font-mono text-on-surface mt-0.5">
                      {detail.disease.prevalence_per_100k ?? '—'} / 100k
                    </div>
                  </div>
                  <div className="p-3 rounded-lg bg-surface-container-low border border-outline-variant/30">
                    <span className="text-[10px] font-bold uppercase text-outline">
                      Inheritance Mode
                    </span>
                    <div className="text-sm font-bold text-on-surface mt-0.5">
                      {detail.disease.inheritance || '—'}
                    </div>
                  </div>
                  <div className="p-3 rounded-lg bg-surface-container-low border border-outline-variant/30">
                    <span className="text-[10px] font-bold uppercase text-outline">
                      Causal Genes
                    </span>
                    <div className="text-sm font-bold font-mono text-primary mt-0.5">
                      {detail.genes?.join(', ') || '—'}
                    </div>
                  </div>
                </div>

                {detail.phenotypes?.length > 0 && (
                  <div>
                    <h6 className="text-xs font-bold text-outline uppercase tracking-wider mb-2">
                      Phenotype Annotations ({detail.phenotypes.length})
                    </h6>
                    <div className="flex flex-wrap gap-1.5">
                      {detail.phenotypes.slice(0, 15).map((p, idx) => (
                        <span
                          key={idx}
                          className="px-2.5 py-1 rounded-md bg-surface-container-low text-xs text-on-surface border border-outline-variant/30"
                        >
                          {p.name || p.hpo_name || p}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {detail.founder_risk?.length > 0 && (
                  <div className="p-3 rounded-lg bg-amber-50 border border-amber-200 text-xs text-amber-900">
                    <span className="font-bold">Indian Founder Risk: </span>
                    {detail.founder_risk.map((f) => `${f.community} (${f.note})`).join('; ')}
                  </div>
                )}
              </div>
            </ClinicalCard>
          )}

          {/* Raw JSON Debug Accordion */}
          <div className="pt-2">
            <button
              onClick={() => setShowRawJson(!showRawJson)}
              className="text-xs font-mono text-outline hover:text-on-surface flex items-center gap-1.5"
            >
              <Code2 size={14} />
              <span>{showRawJson ? 'Hide Raw Clinical Payload' : 'Inspect Raw JSON Payload (Audit Log)'}</span>
            </button>
            {showRawJson && (
              <pre className="mt-2 p-4 rounded-xl bg-surface-container-lowest border border-outline-variant/40 text-[11px] font-mono text-on-surface-variant overflow-x-auto max-h-96">
                {JSON.stringify(res, null, 2)}
              </pre>
            )}
          </div>
        </div>
      )}

      {/* Empty State when no results and not busy */}
      {!res && !busy && (
        <EmptyState
          icon={Stethoscope}
          title="No Differential Analysis Run"
          description="Enter clinical notes above and click 'Run Differential Diagnosis' to generate ranked Bayesian candidates with Indian population priors."
          actionText="Run Demonstration Case"
          onAction={() => {
            applyCase(QUICK_CASES[0])
            run()
          }}
        />
      )}
    </div>
  )
}
