import React, { useCallback, useEffect, useState } from 'react'
import { api, setNavContext } from '../api.js'
import { PageHeader } from '../components/ui/PageHeader.jsx'

const AI_PROMPT = 'Explain the primary finding in this case.'

export default function DemoView({ onNavigate, onDemoActive, presentation, onPresentation }) {
  const [state, setState] = useState({ phase: 'loading' })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [confirmReset, setConfirmReset] = useState(false)

  const load = useCallback(async () => {
    try {
      setState({ phase: 'ready', data: await api.demoStatus() })
      setError(null)
    } catch (e) {
      setState({ phase: 'error' })
      setError(e.message)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const run = async (fn, after) => {
    setBusy(true)
    setError(null)
    try {
      await fn()
      if (after) after()
      await load()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  const data = state.data
  const open = (step) => {
    onDemoActive?.(true)
    setNavContext(step.route, { patient_id: data.case_id })
    onNavigate?.(step.route)
  }
  const askAi = () => {
    onDemoActive?.(true)
    setNavContext('ai-assistant', { prompt: AI_PROMPT, patient_id: data.case_id, include_diagnosis_intel: true })
    onNavigate?.('ai-assistant')
  }
  const done = data?.steps?.filter((s) => s.done).length || 0

  return (
    <div className="space-y-5">
      <PageHeader
        title="Guided Case"
        subtitle="A sample patient built with the live Genomera modules. Every step opens the real application on this case."
        
        actions={data?.exists ? (
          <button type="button" onClick={() => onPresentation?.(!presentation)} aria-pressed={!!presentation}
            className="px-3 py-1.5 rounded-lg border border-outline text-xs font-semibold text-primary hover:bg-surface-container-low">
            {presentation ? 'Exit presentation mode' : 'Presentation mode'}
          </button>
        ) : null}
      />

      <div role="note" className="rounded-xl border border-amber-300 bg-amber-50 text-amber-900 text-xs p-3">
        {data?.notice || 'Sample cases are fictional, clearly marked as sample records, and can be removed at any time.'}
      </div>

      {error && <div role="alert" className="rounded-lg border border-red-200 bg-red-50 text-red-800 text-xs px-3 py-2">{error}</div>}

      {state.phase === 'loading' && <div role="status" className="text-xs text-outline">Loading...</div>}

      {state.phase === 'ready' && !data.exists && (
        <div className="rounded-xl bg-white border border-outline-variant/40 p-6 space-y-3">
          <h2 className="text-sm font-bold text-on-surface">No guided case yet</h2>
          <p className="text-xs text-on-surface-variant">
            Creating the guided case records an 11-year-old sample patient with hepatic and neurological findings, analyses a
            reference trio VCF, and builds the family pedigree. Diagnosis, pharmacogenomics, reproductive risk, the Digital Twin and
            the report are then computed from those records by the normal modules.
          </p>
          <button type="button" disabled={busy} onClick={() => run(api.demoSeed, () => onDemoActive?.(true))}
            className="px-4 py-2 rounded-lg bg-primary text-white text-xs font-semibold disabled:opacity-60">
            {busy ? 'Building demo case...' : 'Create guided case'}
          </button>
        </div>
      )}

      {state.phase === 'ready' && data.exists && (
        <>
          <div className="rounded-xl bg-white border border-outline-variant/40 p-4 flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="text-xs text-outline">Case</div>
              <div className="font-mono font-semibold text-primary" data-testid="demo-case-id">{data.case_id}</div>
            </div>
            <div className="text-xs text-on-surface-variant" aria-live="polite">{done} of {data.steps.length} steps have data</div>
            <div className="flex flex-wrap gap-2">
              <button type="button" onClick={askAi} className="px-3 py-1.5 rounded-lg border border-primary text-primary text-xs font-semibold hover:bg-surface-container-low">
                Ask AI Assistant about this case
              </button>
              {!confirmReset ? (
                <button type="button" onClick={() => setConfirmReset(true)} className="px-3 py-1.5 rounded-lg border border-outline text-xs font-semibold text-on-surface-variant hover:bg-surface-container-low">
                  Reset guided case
                </button>
              ) : (
                <span className="inline-flex items-center gap-2 text-xs">
                  <span>Removes only your guided case.</span>
                  <button type="button" disabled={busy} onClick={() => run(api.demoReset, () => { setConfirmReset(false); onDemoActive?.(false); onPresentation?.(false) })}
                    className="px-3 py-1.5 rounded-lg bg-red-700 text-white font-semibold">Confirm reset</button>
                  <button type="button" onClick={() => setConfirmReset(false)} className="px-2 py-1.5 rounded-lg border border-outline">Cancel</button>
                </span>
              )}
            </div>
          </div>

          <ol className="space-y-2" aria-label="Guided demonstration steps">
            {data.steps.map((s, i) => (
              <li key={s.id} className="rounded-xl bg-white border border-outline-variant/40 p-3 flex items-center gap-3">
                <span className="w-7 h-7 shrink-0 rounded-full bg-primary-container/30 text-primary text-xs font-bold flex items-center justify-center" aria-hidden="true">{i + 1}</span>
                <div className="flex-1 min-w-0">
                  <div className="text-xs font-semibold text-on-surface">{s.label}</div>
                  <div className="text-[11px] text-on-surface-variant">{s.detail}</div>
                </div>
                <span className={`text-[10px] font-semibold uppercase px-2 py-0.5 rounded border ${s.done ? 'border-emerald-300 bg-emerald-50 text-emerald-800' : 'border-outline bg-surface-container-low text-on-surface-variant'}`}>
                  {s.done ? 'Data present' : 'No data yet'}
                </span>
                <button type="button" onClick={() => open(s)} className="px-3 py-1.5 rounded-lg bg-primary text-white text-xs font-semibold">Open</button>
              </li>
            ))}
          </ol>
        </>
      )}
    </div>
  )
}
