import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { AlertTriangle, FlaskConical, GitBranch, UserPlus, X } from 'lucide-react'
import { api, consumeNavContext, setNavContext } from '../api.js'
import { PageHeader } from '../components/ui/PageHeader.jsx'
import PedigreeCanvas, { PedigreeLegend } from '../components/pedigree/PedigreeCanvas.jsx'
import MemberInspector, { AddMemberForm } from '../components/pedigree/MemberInspector.jsx'
import { EvidenceTab, InheritanceTab, PrioritisationTab, ReproTab, SegregationTab } from '../components/pedigree/AnalysisPanel.jsx'
import PedigreeAssistantPanel from '../components/pedigree/PedigreeAssistantPanel.jsx'

const TABS = [['inheritance', 'Inheritance'], ['segregation', 'Segregation & trio'], ['evidence', 'ACMG & diagnosis'], ['prioritisation', 'Prioritisation'], ['repro', 'Reproductive']]
const SEV = { error: 'bg-red-50 border-red-200 text-red-800', warning: 'bg-amber-50 border-amber-200 text-amber-900', info: 'bg-sky-50 border-sky-200 text-sky-900' }

// Fallback genotype state (backend analysis is authoritative once loaded)
function localState(gt, sex, chrom) {
  if (!gt || gt === 'unknown') return 'unknown'
  if (gt === 'hemizygous') return 'hemi'
  if (gt === '0/0') return 'absent'
  if (gt === '0/1') return 'het'
  if (gt === '1/1') return chrom === 'chrX' && sex === 'M' ? 'hemi' : 'hom'
  return 'unknown'
}

export default function PedigreeView({ onNavigate }) {
  const [patients, setPatients] = useState([])
  const [caseId, setCaseId] = useState('')
  const [ped, setPed] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [selectedId, setSelectedId] = useState(null)
  const [showAdd, setShowAdd] = useState(false)
  const [variantKey, setVariantKey] = useState('')
  const [analysis, setAnalysis] = useState(null)
  const [analysisErr, setAnalysisErr] = useState(null)
  const [tab, setTab] = useState('inheritance')
  const [prio, setPrio] = useState(null)
  const [repro, setRepro] = useState({ data: null, error: null, busy: false })
  const [demoBusy, setDemoBusy] = useState(false)
  const seq = useRef(0)

  const nav = useCallback((route, ctx) => { setNavContext(route, ctx); onNavigate?.(route) }, [onNavigate])

  useEffect(() => {
    const ctx = consumeNavContext('pedigree')
    api.listPatients().then((l) => { setPatients(l || []); if (ctx?.patient_id) setCaseId(ctx.patient_id) }).catch((ex) => setError(ex.message))
  }, [])

  const load = useCallback(async (cid, keep = true) => {
    const mine = ++seq.current
    if (!cid) { setPed(null); return null }
    if (!keep) setPed(null)
    setLoading(true)
    setError(null)
    try {
      const p = await api.pedigree(cid)
      if (mine === seq.current) setPed(p)
      return p
    } catch (ex) {
      if (mine === seq.current) setError(ex.message)
      return null
    } finally {
      if (mine === seq.current) setLoading(false)
    }
  }, [])

  // A different case always starts from a clean workspace (no stale members, selection or analysis)
  useEffect(() => {
    setSelectedId(null); setShowAdd(false); setVariantKey(''); setAnalysis(null); setAnalysisErr(null); setPrio(null)
    setRepro({ data: null, error: null, busy: false }); setTab('inheritance')
    load(caseId, false)
  }, [caseId, load])

  const loadAnalysis = useCallback(async (cid, vk) => {
    setAnalysisErr(null)
    if (!cid || !vk) { setAnalysis(null); return }
    try { setAnalysis(await api.pedigreeAnalysis(cid, vk)) } catch (ex) { setAnalysis(null); setAnalysisErr(ex.message) }
  }, [])

  useEffect(() => { loadAnalysis(caseId, variantKey) }, [caseId, variantKey, loadAnalysis])
  useEffect(() => {
    if (tab === 'prioritisation' && caseId) api.pedigreePrioritization(caseId).then(setPrio).catch(() => setPrio({ method: 'Could not load prioritisation.', rows: [] }))
  }, [tab, caseId, ped])

  // After any confirmed mutation: refresh the pedigree and the open analysis.
  const changed = useCallback(async () => {
    const p = await load(caseId)
    if (p && selectedId && !p.members.some((m) => m.member_id === selectedId)) setSelectedId(null)
    if (p && variantKey && !p.variants.some((v) => v.variant_key === variantKey)) setVariantKey('')
    else if (variantKey) await loadAnalysis(caseId, variantKey)
    setPrio(null)
  }, [caseId, load, selectedId, variantKey, loadAnalysis])

  const selected = ped?.members.find((m) => m.member_id === selectedId) || null
  const variantStates = useMemo(() => {
    if (!ped || !variantKey) return null
    if (analysis && analysis.variant_key === variantKey) return Object.fromEntries(analysis.members.map((m) => [m.member_id, m.state]))
    const meta = ped.variants.find((v) => v.variant_key === variantKey)
    return Object.fromEntries(ped.members.map((m) => [m.member_id, localState(m.genotypes[variantKey]?.genotype, m.sex, meta?.chrom)]))
  }, [ped, variantKey, analysis])

  const onMove = async (id, x, y) => {
    try {
      if (id === null) await Promise.all(ped.members.filter((m) => m.layout_x != null).map((m) => api.pedigreePatchMember(caseId, m.member_id, { clear_layout: true })))
      else await api.pedigreePatchMember(caseId, id, { layout_x: x, layout_y: y })
      await load(caseId)
    } catch (ex) { setError(ex.message) }
  }
  const runDemo = async () => {
    setDemoBusy(true); setError(null)
    try { await api.pedigreeDemoFamily(caseId); await load(caseId) } catch (ex) { setError(ex.message) } finally { setDemoBusy(false) }
  }
  const runRepro = async () => {
    setRepro({ data: null, error: null, busy: true })
    try { setRepro({ data: await api.pedigreeReproductive(caseId), error: null, busy: false }) } catch (ex) { setRepro({ data: null, error: ex.message, busy: false }) }
  }
  const pickVariant = (k) => { setVariantKey(k); if (k) setTab('inheritance') }
  const errors = ped?.validation.filter((i) => i.severity === 'error') || []

  return (
    <div className="space-y-5">
      <PageHeader title="Pedigree & Inheritance"
        subtitle="Record the family, assign phenotypes and genotypes, and analyse inheritance, segregation, de novo status and phase from the recorded data only."
        badge={{ label: 'Genetics decision support', color: 'warning', icon: GitBranch }} />

      <div className="rounded-xl border border-outline-variant/40 bg-white p-4 flex flex-wrap items-end gap-4">
        <label className="text-xs space-y-1"><span className="font-semibold text-on-surface">Patient / case</span>
          <select aria-label="Case" className="block min-w-[240px] text-xs rounded-lg border border-outline-variant bg-white px-2.5 py-2" value={caseId} onChange={(e) => setCaseId(e.target.value)}>
            <option value="">Select a case…</option>
            {patients.map((p) => <option key={p.patient_id} value={p.patient_id}>{p.patient_id} · {p.age_years ?? '?'}y {p.sex || ''} · {p.state || 'state n/a'}</option>)}
          </select></label>
        {ped && (
          <>
            <div className="text-xs"><span className="font-semibold text-on-surface block mb-1">Proband</span>
              <span data-testid="proband-name" className="inline-block px-2.5 py-2 rounded-lg bg-surface-container-low">{ped.members.find((m) => m.is_proband)?.label || 'not designated'}</span></div>
            <label className="text-xs space-y-1"><span className="font-semibold text-on-surface">Analyze variant in family</span>
              <select aria-label="Selected variant" className="block min-w-[240px] text-xs rounded-lg border border-outline-variant bg-white px-2.5 py-2" value={variantKey} onChange={(e) => pickVariant(e.target.value)}>
                <option value="">None (structure view)</option>
                {ped.variants.map((v) => <option key={v.variant_key} value={v.variant_key}>{v.gene} {v.hgvs || v.variant_key} — {v.classification}</option>)}
              </select></label>
            {variantKey && <button onClick={() => setVariantKey('')} className="inline-flex items-center gap-1 px-2.5 py-2 rounded-lg border border-outline-variant text-xs font-semibold"><X size={12} /> Clear variant</button>}
            <button data-testid="add-member" onClick={() => setShowAdd((v) => !v)} className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-primary text-white text-xs font-semibold"><UserPlus size={13} /> Add member</button>
          </>
        )}
      </div>

      {error && <div role="alert" className="text-xs rounded-lg border border-red-200 bg-red-50 text-red-800 px-3 py-2">{error}</div>}
      {!caseId && <div className="text-xs rounded-lg border border-outline-variant/40 bg-surface-container-low px-3 py-2">Select a case to open its pedigree.</div>}
      {loading && !ped && <div className="text-xs text-outline">Loading pedigree…</div>}

      {ped && (
        <>
          {ped.synthetic_banner && (
            <div role="status" data-testid="synthetic-banner" className="flex items-center gap-2 text-xs font-semibold rounded-lg border border-amber-300 bg-amber-50 text-amber-900 px-3 py-2">
              <FlaskConical size={14} /> {ped.synthetic_banner}
            </div>
          )}
          {ped.members.length === 0 && (
            <div className="rounded-xl border border-outline-variant/40 bg-white p-4 text-xs space-y-2" data-testid="empty-pedigree">
              <p>This case has no pedigree yet. Add the proband and relatives, or load the verified trio as a sample family.</p>
              <button onClick={runDemo} disabled={demoBusy} data-testid="demo-family" className="px-3 py-1.5 rounded-lg border border-primary text-primary font-semibold disabled:opacity-60">
                {demoBusy ? 'Creating…' : 'Create sample family (verified trio VCF)'}</button>
            </div>
          )}

          <div className="grid xl:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)] gap-4">
            <section className="space-y-3 min-w-0" aria-label="Pedigree">
              <PedigreeCanvas members={ped.members} selectedId={selectedId} onSelect={setSelectedId} onMove={onMove} variantStates={variantStates} />
              <PedigreeLegend variantMode={!!variantStates} />
              {variantKey && ped.variants.find((v) => v.variant_key === variantKey) && (
                <div className="text-xs rounded-lg border border-primary/30 bg-primary/5 px-3 py-2" data-testid="variant-mode-banner">
                  Variant mode: <b>{ped.variants.find((v) => v.variant_key === variantKey).gene} {ped.variants.find((v) => v.variant_key === variantKey).hgvs}</b> — filled = homozygous/hemizygous, half-filled = heterozygous carrier, open = no variant, dashed/muted = genotype unavailable.
                </div>
              )}
              {ped.validation.length > 0 && (
                <div className="space-y-1" data-testid="validation" aria-label="Pedigree validation">
                  {ped.validation.map((i, k) => (
                    <div key={k} className={`flex items-start gap-1.5 text-xs rounded-lg border px-3 py-1.5 ${SEV[i.severity]}`} data-severity={i.severity}>
                      <AlertTriangle size={13} className="mt-0.5 shrink-0" /><span><b className="uppercase text-[10px] mr-1">{i.severity}</b>{i.message}</span>
                    </div>
                  ))}
                </div>
              )}
              {showAdd && <AddMemberForm caseId={caseId} ped={ped} selectedId={selectedId} onChanged={changed} onCancel={() => setShowAdd(false)} />}
            </section>

            <aside className="rounded-xl border border-outline-variant/40 bg-white p-4 min-w-0" aria-label="Member inspector">
              <MemberInspector caseId={caseId} ped={ped} member={selected} nav={nav} onChanged={changed} selectedVariant={variantKey}
                onSelectVariant={pickVariant} />
            </aside>
          </div>

          <section className="rounded-xl border border-outline-variant/40 bg-white p-4 space-y-3" aria-label="Inheritance analysis" data-testid="analysis-section">
            <div className="flex flex-wrap items-center gap-2 justify-between">
              <h3 className="text-sm font-bold text-on-surface">Inheritance analysis{analysis?.variant ? ` — ${analysis.variant.gene} ${analysis.variant.hgvs || ''}` : ''}</h3>
              {analysis?.variant && (
                <div className="flex gap-2 text-xs">
                  <button onClick={() => nav('variants', { patient_id: caseId, analysis_id: analysis.variant.analysis_id, variant_id: analysis.variant_key })} className="px-2.5 py-1.5 rounded-lg border border-primary text-primary font-semibold">Open Variant Intelligence</button>
                  <button onClick={() => nav('kg', { disease_id: analysis.variant.disease_id, genes: [analysis.variant.gene], variant_ids: [analysis.variant_key] })} className="px-2.5 py-1.5 rounded-lg border border-outline-variant font-semibold">Open Knowledge Graph</button>
                  <button onClick={() => nav('diagnosis', { patient_id: caseId })} className="px-2.5 py-1.5 rounded-lg border border-outline-variant font-semibold">Open Diagnosis</button>
                </div>
              )}
            </div>
            <div role="tablist" className="flex flex-wrap gap-1">
              {TABS.map(([id, label]) => (
                <button key={id} role="tab" aria-selected={tab === id} data-testid={`tab-${id}`} onClick={() => setTab(id)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-semibold ${tab === id ? 'bg-primary text-white' : 'bg-surface-container-low text-on-surface-variant hover:text-on-surface'}`}>{label}</button>
              ))}
            </div>
            {analysisErr && <div role="alert" className="text-xs text-red-800">{analysisErr}</div>}
            {tab === 'prioritisation' && <PrioritisationTab data={prio} />}
            {tab === 'repro' && <ReproTab data={repro.data} error={repro.error} busy={repro.busy} onRun={runRepro} />}
            {(tab === 'inheritance' || tab === 'segregation' || tab === 'evidence') && (
              !variantKey ? (
                <p className="text-xs text-on-surface-variant" data-testid="no-variant-hint">
                  Select a variant above (or in a member's genotype list) to analyse it in this family.
                  {ped.variants.length === 0 && ' No variants are registered yet: import a VCF sample or assign a genotype to a member first.'}
                </p>
              ) : !analysis ? (
                !analysisErr && <p className="text-xs text-outline">Analysing…</p>
              ) : !analysis.available ? (
                <p className="text-xs text-amber-800">{analysis.uncertainty.join(' ')}</p>
              ) : (
                <>
                  {tab === 'inheritance' && <InheritanceTab a={analysis} />}
                  {tab === 'segregation' && <SegregationTab a={analysis} />}
                  {tab === 'evidence' && <EvidenceTab a={analysis} />}
                </>
              )
            )}
          </section>

          <PedigreeAssistantPanel caseId={caseId} variantKey={variantKey} />

          <p className="text-[11px] text-outline">
            Decision support only. Results come from the genotypes, affected statuses and parent-child links recorded for this case; missing data stays missing and is
            listed as uncertainty. Parentage and sequencing quality are not verified here.
          </p>
        </>
      )}
    </div>
  )
}
