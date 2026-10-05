import React, { useCallback, useEffect, useRef, useState } from 'react'
import { Save, FileText, RefreshCw, ShieldAlert, RotateCcw, Cpu } from 'lucide-react'
import { api, consumeNavContext, setNavContext } from '../api.js'
import { PageHeader } from '../components/ui/PageHeader.jsx'
import TwinStateGraph, { TWIN_SECTIONS, sectionSummary } from '../components/twin/TwinStateGraph.jsx'
import {
  PhenotypePanel, GenomicPanel, DiagnosisPanel, PgxPanel, FamilyPanel, TimelinePanel, ProvenancePanel,
  Stat, Note, pct,
} from '../components/twin/TwinSections.jsx'
import ScenarioWorkspace from '../components/twin/ScenarioWorkspace.jsx'
import TwinAssistantPanel from '../components/twin/TwinAssistantPanel.jsx'
import TwinStage, { MODES } from '../components/twin3d/TwinStage.jsx'
import EntityPanel from '../components/twin3d/EntityPanel.jsx'
import TwinTimeline from '../components/twin3d/TwinTimeline.jsx'
import ScenarioCompare, { StagePlayer } from '../components/twin3d/ScenarioCompare.jsx'
import { CAMERA_VIEWS } from '../components/twin3d/webgl.js'
import { chromOfVariant } from '../components/twin3d/selection.js'

const SECTION_LABEL = Object.fromEntries(TWIN_SECTIONS.map((s) => [s.id, s.label]))
const VIEW_BUTTONS = [['front', 'Front'], ['back', 'Back'], ['left', 'Left'], ['right', 'Right']]

export default function DigitalTwinView({ onNavigate, forceFallback = false }) {
  const [patients, setPatients] = useState([])
  const [patientId, setPatientId] = useState('')
  const [analysisId, setAnalysisId] = useState('')
  const [twin, setTwin] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [active, setActive] = useState('phenotype')
  const [mode, setMode] = useState('anatomy')
  const [goal, setGoal] = useState({ ...CAMERA_VIEWS.front, key: 0 })
  const [view, setView] = useState('front')
  const [selection, setSelection] = useState(null)
  const [selectedChrom, setSelectedChrom] = useState(null)
  const [lastScenario, setLastScenario] = useState(null)
  const [computing, setComputing] = useState(false)
  const [askPrefill, setAskPrefill] = useState(null)
  const [askVariant, setAskVariant] = useState(null)
  const [snapshotMsg, setSnapshotMsg] = useState(null)
  const [reportState, setReportState] = useState({ busy: false, message: null })
  const seq = useRef(0)

  const nav = useCallback((route, ctx) => {
    setNavContext(route, ctx)
    onNavigate?.(route)
  }, [onNavigate])

  useEffect(() => {
    const ctx = consumeNavContext('digital-twin')
    api.listPatients().then((list) => {
      setPatients(list || [])
      if (ctx?.patient_id) setPatientId(ctx.patient_id)
    }).catch((ex) => setError(ex.message))
  }, [])

  const loadTwin = useCallback(async (pid, aid) => {
    const mine = ++seq.current
    setTwin(null)
    setError(null)
    setSnapshotMsg(null)
    setReportState({ busy: false, message: null })
    if (!pid) return
    setLoading(true)
    try {
      const t = await api.twin(pid, aid || undefined)
      if (mine === seq.current) setTwin(t)
    } catch (ex) {
      if (mine === seq.current) setError(ex.message)
    } finally {
      if (mine === seq.current) setLoading(false)
    }
  }, [])

  // A different patient rebuilds everything: Twin, selection, scenario and camera.
  useEffect(() => {
    setAnalysisId('')
    setLastScenario(null)
    setComputing(false)
    setAskPrefill(null)
    setAskVariant(null)
    setSelection(null)
    setSelectedChrom(null)
    setMode('anatomy')
    setView('front')
    loadTwin(patientId, '')
  }, [patientId, loadTwin])

  const changeAnalysis = (aid) => {
    setAnalysisId(aid)
    setLastScenario(null)
    setSelection(null)
    loadTwin(patientId, aid)
  }

  const flyTo = (name) => {
    setView(name)
    setGoal({ ...CAMERA_VIEWS[name], key: Date.now() })
  }
  const switchMode = (m) => {
    setMode(m)
    if (m === 'dna') flyTo('dna')
    else if (m === 'anatomy' || m === 'systems') flyTo(view === 'dna' ? 'front' : view)
  }
  const resetView = () => {
    setSelectedChrom(null)
    flyTo(mode === 'dna' ? 'dna' : 'front')
  }

  const selectVariant = (id) => {
    setSelection({ kind: 'variant', id })
    setAskVariant(id)
    setSelectedChrom(chromOfVariant(twin, id))
  }
  const selectSystem = (id) => setSelection({ kind: 'system', id })
  const onSelect = (sel) => {
    setSelection(sel)
    if (sel.kind === 'variant') {
      setAskVariant(sel.id)
      setSelectedChrom(chromOfVariant(twin, sel.id))
    }
  }
  const scrollToAssistant = () => {
    const el = document.getElementById('twin-assistant-anchor')
    if (el && el.scrollIntoView) el.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }
  const ask = (text, variantId) => {
    setAskPrefill({ text, n: Date.now() })
    if (variantId) setAskVariant(variantId)
    scrollToAssistant()
  }

  const saveSnapshot = async () => {
    try {
      const s = await api.twinSaveSnapshot(patientId, analysisId || undefined)
      setSnapshotMsg(`Saved snapshot #${s.sequence} (${s.snapshot_version})${s.changed_since_previous ? '' : ' - unchanged since your previous snapshot'}.`)
    } catch (ex) {
      setSnapshotMsg(`Could not save snapshot: ${ex.message}`)
    }
  }
  const addToReport = async (scenario) => {
    const source = scenario ? 'scenario' : 'snapshot'
    setReportState({ busy: true, message: null, source })
    try {
      const b = await api.twinReportHandoff(patientId, { scenario_ids: scenario ? [scenario.scenario_id] : [], analysis_id: analysisId || null })
      setReportState({ busy: false, source, message: `Added to the clinical record as ${b.event_id}: snapshot ${b.snapshot_version}${b.scenarios.length ? ` with ${b.scenarios.length} scenario(s)` : ''}.` })
    } catch (ex) {
      setReportState({ busy: false, source, message: `Could not add to report: ${ex.message}` })
    }
  }

  const snap = twin?.snapshot
  const top = twin?.diagnosis?.top_diagnosis
  const panels = twin && {
    phenotype: <PhenotypePanel twin={twin} />,
    genomic: <GenomicPanel twin={twin} patientId={patientId} nav={nav} />,
    diagnosis: <DiagnosisPanel twin={twin} patientId={patientId} nav={nav} />,
    pgx: <PgxPanel twin={twin} nav={nav} />,
    family: <FamilyPanel twin={twin} />,
    timeline: <TimelinePanel twin={twin} />,
    provenance: <ProvenancePanel twin={twin} />,
  }
  const btn = 'px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors'
  const chromVariants = twin && selectedChrom ? (twin.anatomy.chromosomes.find((c) => c.chrom === selectedChrom)?.variants || []) : []

  return (
    <div className="space-y-5">
      <PageHeader
        title="Digital Twin"
        subtitle="An interactive computational representation of one patient: body systems, genome and clinical state, derived only from stored phenotypes, variant analysis, the diagnosis engine and PGx rules."
        badge={{ label: 'Computational decision support', color: 'warning', icon: ShieldAlert }}
      />

      <div className="rounded-xl border border-outline-variant/40 bg-white p-4 flex flex-wrap items-end gap-4">
        <label className="text-xs space-y-1">
          <span className="font-semibold text-on-surface">Patient / case</span>
          <select aria-label="Patient" className="block min-w-[260px] text-xs rounded-lg border border-outline-variant bg-white px-2.5 py-2" value={patientId} onChange={(e) => setPatientId(e.target.value)}>
            <option value="">Select a patient…</option>
            {patients.map((p) => (
              <option key={p.patient_id} value={p.patient_id}>{p.patient_id} · {p.age_years ?? '?'}y {p.sex || ''} · {p.state || 'state n/a'}</option>
            ))}
          </select>
        </label>
        {twin && twin.genomic.analyses.length > 1 && (
          <label className="text-xs space-y-1">
            <span className="font-semibold text-on-surface">Variant analysis</span>
            <select aria-label="Variant analysis" className="block text-xs rounded-lg border border-outline-variant bg-white px-2.5 py-2" value={analysisId || twin.genomic.analysis_id} onChange={(e) => changeAnalysis(e.target.value)}>
              {twin.genomic.analyses.map((a) => <option key={a.analysis_id} value={a.analysis_id}>{a.analysis_id} · {a.filename} · {a.total_variants} variants</option>)}
            </select>
          </label>
        )}
        {patientId && (
          <button onClick={() => loadTwin(patientId, analysisId)} className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border border-outline-variant text-xs font-semibold hover:bg-surface-container-low">
            <RefreshCw size={13} className={loading ? 'animate-spin' : ''} /> Rebuild
          </button>
        )}
      </div>

      {error && <div role="alert" className="text-xs rounded-lg border border-red-200 bg-red-50 text-red-800 px-3 py-2">{error}</div>}
      {!patientId && !error && <Note>Select a patient to build their Digital Twin. Patients are registered in the Patient Registry.</Note>}
      {loading && <div className="text-xs text-outline" data-testid="twin-loading">Building Twin from stored case data…</div>}

      {twin && (
        <>
          <div className="grid xl:grid-cols-[minmax(0,1.45fr)_minmax(0,1fr)] gap-4">
            {/* PRIMARY: body / genome / DNA stage */}
            <section className="space-y-3 min-w-0" aria-label="Interactive Twin">
              <div className="flex flex-wrap items-center gap-2" data-testid="control-bar">
                <div role="tablist" aria-label="Twin view" className="flex gap-1 p-1 rounded-xl bg-surface-container-low border border-outline-variant/40">
                  {MODES.map((m) => (
                    <button key={m.id} role="tab" aria-selected={mode === m.id} data-testid={`mode-${m.id}`} onClick={() => switchMode(m.id)}
                      className={`${btn} ${mode === m.id ? 'bg-white text-primary shadow-xs' : 'text-on-surface-variant hover:text-on-surface'}`}>{m.label}</button>
                  ))}
                </div>
                <div className="flex gap-1" role="group" aria-label="Camera">
                  {VIEW_BUTTONS.map(([id, label]) => (
                    <button key={id} data-testid={`view-${id}`} aria-pressed={view === id} disabled={mode === 'genome' || mode === 'timeline' || mode === 'dna'} onClick={() => flyTo(id)}
                      className={`${btn} border ${view === id && mode !== 'dna' ? 'border-primary text-primary bg-primary/5' : 'border-outline-variant text-on-surface-variant'} disabled:opacity-40`}>{label}</button>
                  ))}
                  <button data-testid="reset-view" onClick={resetView} className={`${btn} border border-outline-variant text-on-surface inline-flex items-center gap-1`}>
                    <RotateCcw size={12} /> Reset view
                  </button>
                </div>
              </div>
              {mode === 'systems' && (
                <div className="flex flex-wrap gap-1.5" data-testid="systems-rail" aria-label="Body systems">
                  {twin.anatomy.systems.map((s) => (
                    <button key={s.id} onClick={() => selectSystem(s.id)} aria-pressed={selection?.kind === 'system' && selection.id === s.id}
                      className={`px-2.5 py-1 rounded-full text-[11px] border ${selection?.kind === 'system' && selection.id === s.id ? 'border-secondary bg-secondary/10 font-semibold' : s.has_case_data ? 'border-primary/50 bg-primary/5' : 'border-outline-variant text-on-surface-variant'}`}>
                      {s.label}{s.has_case_data ? ' ●' : ''}
                    </button>
                  ))}
                </div>
              )}
              <div className="h-[560px] sm:h-[680px]">
                <TwinStage twin={twin} mode={mode} goal={goal} selection={selection} selectedChrom={selectedChrom}
                  onSelectSystem={selectSystem} onSelectVariant={selectVariant} onSelectChrom={setSelectedChrom} forceFallback={forceFallback} />
              </div>
              <div className="rounded-xl border border-outline-variant/40 bg-white p-4" aria-live="polite">
                <h3 className="text-xs font-bold text-on-surface mb-2">Clinical evidence</h3>
                <EntityPanel twin={twin} selection={selection} patientId={patientId} nav={nav} onSelect={onSelect} onAsk={ask} />
                {mode === 'genome' && selectedChrom && (
                  <div className="mt-3 border-t border-outline-variant/30 pt-2 text-xs" data-testid="chrom-drill">
                    <b>{selectedChrom}</b> →{' '}
                    {chromVariants.map((v) => (
                      <button key={v.variant_id} className="mr-2 text-primary font-semibold hover:underline" onClick={() => selectVariant(v.variant_id)}>{v.gene} {v.hgvs}</button>
                    ))}
                    {!chromVariants.length && 'no analysed variants'}
                  </div>
                )}
              </div>
            </section>

            {/* SECONDARY: clinical intelligence */}
            <aside className="space-y-3 min-w-0" aria-label="Clinical intelligence">
              <div className="rounded-xl border border-outline-variant/40 bg-white p-4 space-y-3" data-testid="twin-snapshot">
                <div className="text-[11px] text-outline font-mono">Patient {snap.patient_id} · Snapshot {snap.snapshot_version} · Last source update {snap.last_updated_utc || 'n/a'}</div>
                <div className="grid grid-cols-3 gap-2">
                  <Stat label="Phenotypes" value={snap.phenotypes} />
                  <Stat label="Variants" value={snap.variants} />
                  <Stat label="Pathogenic" value={snap.pathogenic} />
                  <Stat label="VUS" value={snap.vus} />
                  <Stat label="PGx findings" value={snap.pgx_findings.length} />
                  <Stat label="Top diagnosis" value={top ? top.disease_name : 'Insufficient data'} />
                </div>
                {top && (
                  <button onClick={() => setSelection({ kind: 'diagnosis', id: top.disease_id })} data-testid="select-diagnosis"
                    className="w-full text-left rounded-lg border border-primary/40 bg-primary/5 p-2.5 text-xs hover:bg-primary/10">
                    <span className="text-[10px] uppercase text-outline font-semibold">Current leading diagnosis</span>
                    <span className="block font-bold text-on-surface">{top.disease_name} · {pct(top.probability)}</span>
                  </button>
                )}
                <div className="flex flex-wrap items-center gap-2">
                  <button onClick={saveSnapshot} className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-primary text-primary text-xs font-semibold hover:bg-primary/5"><Save size={13} /> Save snapshot</button>
                  <button onClick={() => addToReport(null)} disabled={reportState.busy} data-testid="add-snapshot-to-report" className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-primary text-white text-xs font-semibold hover:bg-primary-container disabled:opacity-60"><FileText size={13} /> Add Twin Snapshot to Report</button>
                </div>
                {snapshotMsg && <p className="text-xs text-on-surface-variant">{snapshotMsg}</p>}
                {reportState.message && reportState.source === 'snapshot' && <Note>{reportState.message}</Note>}
              </div>

              <div className="rounded-xl border border-outline-variant/40 bg-white p-4" aria-label="Body systems (text)">
                <h3 className="text-xs font-bold text-on-surface mb-2">Body systems</h3>
                <ul className="grid grid-cols-2 gap-1" data-testid="system-list">
                  {twin.anatomy.systems.map((s) => (
                    <li key={s.id}>
                      <button onClick={() => selectSystem(s.id)} className={`w-full text-left px-2 py-1 rounded-md text-[11px] border ${selection?.kind === 'system' && selection.id === s.id ? 'border-secondary bg-secondary/10' : 'border-transparent hover:bg-surface-container-low'}`}>
                        {s.label} <span className="text-outline">{s.has_case_data ? `· ${s.phenotypes.length} phen · ${s.variant_ids.length} var` : '· no case data'}</span>
                      </button>
                    </li>
                  ))}
                </ul>
                {twin.anatomy.notes.map((n) => <p key={n} className="text-[10px] text-outline mt-1.5 leading-snug">{n}</p>)}
              </div>

              <div className="rounded-xl border border-outline-variant/40 bg-white p-4" data-testid="state-inspector">
                <div className="flex flex-wrap gap-1 mb-3" role="tablist" aria-label="Clinical data">
                  {[...TWIN_SECTIONS.map((s) => s.id), 'provenance'].map((id) => (
                    <button key={id} role="tab" aria-selected={active === id} onClick={() => setActive(id)}
                      className={`px-2.5 py-1 rounded-lg text-[11px] font-semibold ${active === id ? 'bg-primary text-white' : 'bg-surface-container-low text-on-surface-variant hover:text-on-surface'}`}>
                      {id === 'provenance' ? 'Provenance' : SECTION_LABEL[id]}
                      {id !== 'provenance' && !sectionSummary(twin, id).available && <span className="ml-1 opacity-60">·</span>}
                    </button>
                  ))}
                </div>
                {panels[active]}
                <details className="mt-3">
                  <summary className="text-[11px] font-semibold text-primary cursor-pointer inline-flex items-center gap-1"><Cpu size={12} /> Data explorer (state map)</summary>
                  <div className="mt-2 max-w-md"><TwinStateGraph twin={twin} active={active} onSelect={setActive} /></div>
                </details>
              </div>
            </aside>
          </div>

          <section className="rounded-xl border border-outline-variant/40 bg-white" aria-label="Twin timeline">
            <h3 className="text-xs font-bold text-on-surface px-4 pt-3">Timeline (stored events only)</h3>
            <TwinTimeline timeline={twin.timeline} />
          </section>

          <section className="space-y-3" aria-label="What-if simulation">
            <h3 className="text-sm font-bold text-on-surface">What-if simulation</h3>
            <ScenarioWorkspace
              twin={twin} patientId={patientId} analysisId={analysisId || twin.genomic.analysis_id}
              reportState={reportState.source === 'scenario' ? reportState : { busy: false, message: null }}
              onReport={addToReport}
              onAsk={(res) => { setLastScenario(res); setAskPrefill({ text: 'What changed between baseline and this scenario?', n: Date.now() }); scrollToAssistant() }}
              onRunStart={() => { setComputing(true); setLastScenario(null) }}
              onResult={(res) => { setComputing(false); setLastScenario(res) }}
              onHistoryChange={() => {}}
            />
            {(computing || lastScenario) && (
              <div className="grid lg:grid-cols-[280px_minmax(0,1fr)] gap-4 rounded-xl border border-outline-variant/40 bg-white p-4" data-testid="simulation-visual">
                <StagePlayer computing={computing} result={lastScenario} />
                {lastScenario ? <ScenarioCompare twin={twin} result={lastScenario} /> : <p className="text-xs text-on-surface-variant">Computing on the server…</p>}
              </div>
            )}
          </section>

          <TwinAssistantPanel patientId={patientId} analysisId={analysisId || twin.genomic.analysis_id} scenario={lastScenario} prefill={askPrefill} selectedVariantId={askVariant} />

          <div className="rounded-lg border border-amber-200 bg-amber-50 text-amber-900 text-xs px-3 py-2 leading-relaxed" data-testid="twin-limitations">
            <b>{twin.disclaimer}</b>
            <ul className="list-disc ml-5 mt-1">{twin.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
            <div className="mt-1">Not available from the current clinical data/model: {twin.unsupported_simulations.map((u) => u.label).join('; ')}.</div>
          </div>
        </>
      )}
    </div>
  )
}
