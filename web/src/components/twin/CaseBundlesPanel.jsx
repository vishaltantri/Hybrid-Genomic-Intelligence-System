import React, { useEffect, useState } from 'react'
import { FileCheck } from 'lucide-react'
import { api } from '../../api.js'

/**
 * Lists report bundles already added to a patient's clinical record (Variant Intelligence and
 * Digital Twin hand-offs), read from the patient's stored events - not from local UI state.
 */
export default function CaseBundlesPanel() {
  const [patients, setPatients] = useState([])
  const [pid, setPid] = useState('')
  const [bundles, setBundles] = useState([])
  const [error, setError] = useState(null)

  useEffect(() => {
    api.listPatients().then((p) => setPatients(p || [])).catch(() => {})
  }, [])

  useEffect(() => {
    setBundles([])
    setError(null)
    if (!pid) return
    let live = true
    api
      .getPatient(pid)
      .then((r) => live && setBundles((r.events || []).filter((e) => e.kind === 'twin_report_bundle' || e.kind === 'variant_report_bundle')))
      .catch((ex) => live && setError(ex.message))
    return () => {
      live = false
    }
  }, [pid])

  return (
    <div className="panel" data-testid="case-bundles">
      <div className="flex items-center gap-2 text-xs font-bold text-on-surface pb-3 mb-3 border-b border-outline-variant/30">
        <FileCheck size={18} className="text-primary" />
        <span>CASE REPORT BUNDLES (Variant Intelligence + Digital Twin hand-offs)</span>
      </div>
      <select aria-label="Report patient" value={pid} onChange={(e) => setPid(e.target.value)} className="text-xs rounded-lg border border-outline-variant px-2.5 py-2 mb-3">
        <option value="">Select a patient…</option>
        {patients.map((p) => <option key={p.patient_id} value={p.patient_id}>{p.patient_id}</option>)}
      </select>
      {error && <div role="alert" className="text-xs text-red-700">{error}</div>}
      {pid && !error && bundles.length === 0 && <p className="text-xs text-outline">No report bundles recorded for this patient.</p>}
      <div className="space-y-3">
        {bundles.map((b) => (
          <div key={b.event_id} className="rounded-lg border border-outline-variant/40 p-3 text-xs space-y-1">
            <div className="font-semibold">
              {b.kind === 'twin_report_bundle' ? `Digital Twin snapshot ${b.payload.snapshot_version}` : `Variant findings ${b.payload.analysis_id}`}
              <span className="font-mono text-outline ml-2">{b.event_id} · {b.created_utc}</span>
            </div>
            {b.kind === 'twin_report_bundle' && (
              <>
                <div>
                  {b.payload.snapshot.phenotypes} phenotypes · {b.payload.snapshot.variants} variants · top diagnosis{' '}
                  {b.payload.snapshot.top_diagnosis?.disease_name || 'Insufficient data'}
                </div>
                {b.payload.scenarios.map((s) => (
                  <div key={s.scenario_id} className="text-on-surface-variant">Scenario: {s.name} — {s.explanation[0]}</div>
                ))}
                <div className="text-[11px] text-amber-800">{b.payload.disclaimer}</div>
              </>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
