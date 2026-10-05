import React, { useEffect, useState } from 'react'
import { Play, RotateCcw, Trash2, FileText, Bot } from 'lucide-react'
import { api } from '../../api.js'
import { Note, ClassBadge, fmt } from './TwinSections.jsx'

const TYPES = [
  { id: 'variant_exclusion', label: 'Exclude a variant' },
  { id: 'variant_reclassification', label: 'Reclassify a variant (hypothetical)' },
  { id: 'phenotype_remove', label: 'Remove a phenotype' },
  { id: 'phenotype_add', label: 'Add a phenotype' },
  { id: 'diagnosis_focus', label: 'Compare a different working diagnosis' },
  { id: 'medication', label: 'Introduce a medication (PGx rules)' },
]
const ACMG = ['Pathogenic', 'Likely pathogenic', 'Uncertain significance', 'Likely benign', 'Benign']

function ComparisonTable({ rows }) {
  return (
    <table className="w-full text-xs" data-testid="comparison-table">
      <thead className="text-[10px] uppercase text-outline">
        <tr>
          <th className="text-left py-1 pr-3">Measure</th>
          <th className="text-left py-1 pr-3">Baseline</th>
          <th className="text-left py-1">Scenario</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => {
          const changed = fmt(r.baseline) !== fmt(r.scenario)
          return (
            <tr key={r.label} className="border-t border-outline-variant/30">
              <td className="py-1.5 pr-3 text-on-surface-variant">{r.label}</td>
              <td className="py-1.5 pr-3 font-mono">{fmt(r.baseline)}</td>
              <td className={`py-1.5 font-mono ${changed ? 'font-bold text-primary' : ''}`}>{fmt(r.scenario)}</td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

function Ranking({ title, side }) {
  if (!side?.differential?.length) return null
  return (
    <div>
      <div className="text-[10px] uppercase text-outline font-semibold mb-1">{title}</div>
      <ol className="text-xs space-y-0.5">
        {side.differential.slice(0, 5).map((d) => (
          <li key={d.disease_id} className="flex justify-between gap-2">
            <span>{d.rank}. {d.disease_name}</span>
            <span className="font-mono text-outline">
              {(d.probability * 100).toFixed(1)}% · P/LP {d.pathogenic_or_likely_variants}
            </span>
          </li>
        ))}
      </ol>
    </div>
  )
}

export function ScenarioResult({ result, onReport, onAsk, reportState }) {
  if (!result) return null
  return (
    <div className="rounded-xl border border-primary/30 bg-white p-4 space-y-4" data-testid="scenario-result">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="text-sm font-bold text-on-surface">{result.name}</div>
          <div className="text-[11px] text-outline font-mono">
            {result.scenario_id} · {result.type_label}
          </div>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => onAsk(result)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-primary text-primary text-xs font-semibold hover:bg-primary/5"
          >
            <Bot size={13} /> Ask AI about this scenario
          </button>
          <button
            onClick={() => onReport(result)}
            disabled={reportState?.busy}
            data-testid="add-scenario-to-report"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-primary text-white text-xs font-semibold hover:bg-primary-container disabled:opacity-60"
          >
            <FileText size={13} /> {reportState?.busy ? 'Adding…' : 'Add to Report'}
          </button>
        </div>
      </div>
      {reportState?.message && <Note>{reportState.message}</Note>}
      <ComparisonTable rows={result.comparison} />
      {result.baseline?.differential && (
        <div className="grid sm:grid-cols-2 gap-4">
          <Ranking title="Baseline differential" side={result.baseline} />
          <Ranking title="Scenario differential" side={result.scenario} />
        </div>
      )}
      {result.scenario?.findings?.length > 0 && (
        <div className="text-xs space-y-1" data-testid="medication-findings">
          {result.scenario.findings.map((f) => (
            <div key={`${f.drug}-${f.gene}`} className="rounded border border-outline-variant/40 px-3 py-1.5">
              <b>{f.drug}</b> / {f.gene} — {f.severity} ({f.inferred_status}) · {f.recommendation || 'no guideline text'}
            </div>
          ))}
        </div>
      )}
      {result.diff?.variant_changes?.length > 0 && (
        <div>
          <div className="text-[10px] uppercase text-outline font-semibold mb-1">Variant changes</div>
          <ul className="text-xs space-y-0.5">
            {result.diff.variant_changes.map((v) => (
              <li key={v.variant_id}>
                {v.gene}: {v.change === 'excluded'
                  ? `excluded (was rank ${v.rank_before})`
                  : `rank ${v.rank_before} → ${v.rank_after}, priority ${v.score_before} → ${v.score_after}`}
                {v.class_before && v.class_before !== v.class_after && (
                  <> · <ClassBadge value={v.class_before} /> → <ClassBadge value={v.class_after} /></>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
      <div>
        <div className="text-xs font-bold text-on-surface mb-1">Why did the state change?</div>
        <ol className="list-decimal ml-5 text-xs space-y-1 text-on-surface" data-testid="explanation">
          {result.explanation.map((e, i) => (
            <li key={i}>{e}</li>
          ))}
        </ol>
      </div>
      <div className="space-y-1">
        {result.limitations.map((l, i) => (
          <Note key={i}>{l}</Note>
        ))}
        <Note tone="warn">{result.disclaimer}</Note>
      </div>
    </div>
  )
}

export default function ScenarioWorkspace({ twin, patientId, analysisId, onAsk, onReport, reportState, onHistoryChange, onRunStart, onResult }) {
  const [type, setType] = useState('variant_exclusion')
  const [name, setName] = useState('')
  const [variantId, setVariantId] = useState('')
  const [newClass, setNewClass] = useState('Uncertain significance')
  const [hpoId, setHpoId] = useState('')
  const [diseaseId, setDiseaseId] = useState('')
  const [drugs, setDrugs] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [result, setResult] = useState(null)
  const [history, setHistory] = useState([])

  const variants = twin.genomic.available ? twin.genomic.variants : []
  const observed = twin.phenotype.observed.filter((o) => o.in_knowledge_graph)
  const alternatives = twin.diagnosis.available ? twin.diagnosis.differential.slice(1) : []
  const undocumented = twin.phenotype.expected_but_undocumented || []

  const loadHistory = () =>
    api
      .twinScenarios(patientId)
      .then((h) => {
        setHistory(h)
        onHistoryChange?.(h)
      })
      .catch(() => setHistory([]))

  // New patient => fresh workspace and that patient's own history only.
  useEffect(() => {
    setResult(null)
    onResult?.(null)
    setError(null)
    setVariantId('')
    setHpoId('')
    setDiseaseId('')
    setDrugs('')
    setName('')
    setHistory([])
    let live = true
    api
      .twinScenarios(patientId)
      .then((h) => live && (setHistory(h), onHistoryChange?.(h)))
      .catch(() => live && setHistory([]))
    return () => {
      live = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [patientId])

  const buildParams = () => {
    switch (type) {
      case 'variant_exclusion':
        return variantId ? { variant_ids: [variantId] } : null
      case 'variant_reclassification':
        return variantId ? { variant_id: variantId, new_classification: newClass } : null
      case 'phenotype_remove':
        return hpoId ? { hpo_ids: [hpoId] } : null
      case 'phenotype_add':
        return hpoId.trim() ? { hpo_ids: [hpoId.trim().toUpperCase()] } : null
      case 'diagnosis_focus':
        return diseaseId ? { disease_id: diseaseId } : null
      case 'medication': {
        const list = drugs.split(',').map((d) => d.trim()).filter(Boolean)
        return list.length ? { drugs: list } : null
      }
      default:
        return null
    }
  }

  const run = async () => {
    const params = buildParams()
    if (!params) {
      setError('Complete the scenario inputs before running.')
      return
    }
    setBusy(true)
    setError(null)
    onRunStart?.()
    try {
      const res = await api.twinCreateScenario(patientId, { type, name: name || null, params, analysis_id: analysisId || null })
      setResult(res)
      onResult?.(res)
      loadHistory()
    } catch (ex) {
      setResult(null)
      onResult?.(null)
      setError(ex.message)
    } finally {
      setBusy(false)
    }
  }

  const reset = () => {
    setResult(null)
    onResult?.(null)
    setError(null)
    setVariantId('')
    setHpoId('')
    setDiseaseId('')
    setDrugs('')
    setName('')
  }

  const openHistory = async (sid) => {
    setError(null)
    try {
      const old = await api.twinScenario(patientId, sid)
      setResult(old)
      onResult?.(old)
    } catch (ex) {
      setError(ex.message)
    }
  }

  const remove = async (sid) => {
    try {
      await api.twinDeleteScenario(patientId, sid)
      if (result?.scenario_id === sid) setResult(null)
      loadHistory()
    } catch (ex) {
      setError(ex.message)
    }
  }

  const sel = 'w-full text-xs rounded-lg border border-outline-variant bg-white px-2.5 py-2'

  return (
    <div className="space-y-4" data-testid="scenario-workspace">
      <div className="rounded-xl border border-outline-variant/40 bg-white p-4 space-y-3">
        <div className="grid sm:grid-cols-2 gap-3">
          <label className="text-xs space-y-1">
            <span className="font-semibold text-on-surface">Scenario type</span>
            <select aria-label="Scenario type" className={sel} value={type} onChange={(e) => { setType(e.target.value); setError(null) }}>
              {TYPES.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
            </select>
          </label>
          <label className="text-xs space-y-1">
            <span className="font-semibold text-on-surface">Scenario name (optional)</span>
            <input aria-label="Scenario name" className={sel} value={name} maxLength={120} onChange={(e) => setName(e.target.value)} placeholder="e.g. Exclude ATP7B variant" />
          </label>
        </div>

        {(type === 'variant_exclusion' || type === 'variant_reclassification') && (
          variants.length === 0 ? (
            <Note tone="warn">Insufficient data: no Variant Intelligence analysis is linked to this patient.</Note>
          ) : (
            <div className="grid sm:grid-cols-2 gap-3">
              <label className="text-xs space-y-1">
                <span className="font-semibold">Variant</span>
                <select aria-label="Variant" className={sel} value={variantId} onChange={(e) => setVariantId(e.target.value)}>
                  <option value="">Select a variant…</option>
                  {variants.map((v) => (
                    <option key={v.variant_id} value={v.variant_id}>
                      {v.gene_symbol || '?'} {v.cdna || v.hgvs} — {v.acmg_classification}
                    </option>
                  ))}
                </select>
              </label>
              {type === 'variant_reclassification' && (
                <label className="text-xs space-y-1">
                  <span className="font-semibold">Hypothetical class</span>
                  <select aria-label="New classification" className={sel} value={newClass} onChange={(e) => setNewClass(e.target.value)}>
                    {ACMG.map((c) => <option key={c} value={c}>{c}</option>)}
                  </select>
                </label>
              )}
            </div>
          )
        )}

        {type === 'phenotype_remove' && (
          observed.length === 0 ? (
            <Note tone="warn">Insufficient data: no phenotypes are documented.</Note>
          ) : (
            <label className="text-xs space-y-1 block">
              <span className="font-semibold">Phenotype to remove</span>
              <select aria-label="Phenotype" className={sel} value={hpoId} onChange={(e) => setHpoId(e.target.value)}>
                <option value="">Select a phenotype…</option>
                {observed.map((o) => <option key={o.hpo_id} value={o.hpo_id}>{o.name} ({o.hpo_id})</option>)}
              </select>
            </label>
          )
        )}

        {type === 'phenotype_add' && (
          <div className="space-y-2">
            <label className="text-xs space-y-1 block">
              <span className="font-semibold">HPO term to add</span>
              <input aria-label="HPO id" className={sel} value={hpoId} onChange={(e) => setHpoId(e.target.value)} placeholder="HP:0000616" />
            </label>
            {undocumented.length > 0 && (
              <div className="text-[11px] text-on-surface-variant">
                Suggestions (expected for {twin.phenotype.expected_for}, not documented):{' '}
                {undocumented.map((m) => (
                  <button key={m.hpo_id} onClick={() => setHpoId(m.hpo_id)} className="mr-1.5 px-2 py-0.5 rounded-full bg-surface-container hover:bg-primary/10">
                    {m.hpo_name} ({m.hpo_id})
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {type === 'diagnosis_focus' && (
          alternatives.length === 0 ? (
            <Note tone="warn">Insufficient data: a ranked differential is required.</Note>
          ) : (
            <label className="text-xs space-y-1 block">
              <span className="font-semibold">Working diagnosis to compare with the current top</span>
              <select aria-label="Working diagnosis" className={sel} value={diseaseId} onChange={(e) => setDiseaseId(e.target.value)}>
                <option value="">Select a diagnosis…</option>
                {alternatives.map((d) => <option key={d.disease_id} value={d.disease_id}>#{d.rank} {d.disease_name}</option>)}
              </select>
            </label>
          )
        )}

        {type === 'medication' && (
          <div className="space-y-1">
            <label className="text-xs space-y-1 block">
              <span className="font-semibold">Drug(s), comma separated</span>
              <input aria-label="Drugs" className={sel} value={drugs} onChange={(e) => setDrugs(e.target.value)} placeholder="clopidogrel" />
            </label>
            <Note>Rule-based drug-gene screening only. Clinical outcome and treatment response are not modelled.</Note>
          </div>
        )}

        {error && <div role="alert" className="text-xs rounded-lg border border-red-200 bg-red-50 text-red-800 px-3 py-2">{error}</div>}

        <div className="flex gap-2">
          <button onClick={run} disabled={busy} data-testid="run-scenario" className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-primary text-white text-xs font-semibold hover:bg-primary-container disabled:opacity-60">
            <Play size={13} /> {busy ? 'Computing…' : 'Run simulation'}
          </button>
          <button onClick={reset} data-testid="reset-scenario" className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg border border-outline-variant text-xs font-semibold text-on-surface hover:bg-surface-container-low">
            <RotateCcw size={13} /> Reset
          </button>
        </div>
      </div>

      <ScenarioResult result={result} onReport={onReport} onAsk={onAsk} reportState={reportState} />

      <div className="rounded-xl border border-outline-variant/40 bg-white p-4">
        <h4 className="text-xs font-bold text-on-surface mb-2">Recent scenarios (yours only)</h4>
        {history.length === 0 ? (
          <p className="text-xs text-on-surface-variant">No scenarios run for this patient yet.</p>
        ) : (
          <ul className="divide-y divide-outline-variant/30" data-testid="scenario-history">
            {history.map((h) => (
              <li key={h.scenario_id} className="py-1.5 flex items-center justify-between gap-2 text-xs">
                <button className="text-left hover:underline text-primary font-semibold" onClick={() => openHistory(h.scenario_id)}>
                  {h.name}
                </button>
                <span className="text-outline font-mono">{h.type_label} · {h.created_utc?.slice(0, 16).replace('T', ' ')}</span>
                <button aria-label={`Delete ${h.name}`} onClick={() => remove(h.scenario_id)} className="text-outline hover:text-red-700">
                  <Trash2 size={13} />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
