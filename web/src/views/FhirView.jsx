import React, { useEffect, useState } from 'react'
import { api } from '../api.js'

function Issues({ v }) {
  return (
    <div data-testid="fhir-validation" className="text-xs space-y-1">
      <div className={v.valid ? 'text-primary font-semibold' : 'text-red-700 font-semibold'}>
        {v.valid ? 'Structurally valid' : 'Structural errors found'} — {v.errors} errors, {v.warnings} warnings
      </div>
      <div className="text-outline">{v.scope}</div>
      <div>{Object.entries(v.counts || {}).map(([k, n]) => `${k}: ${n}`).join(' · ')}</div>
      <ul className="list-disc pl-4">{v.issues.map((i, n) => <li key={n}>{i.severity}: {i.where} — {i.message}</li>)}</ul>
    </div>
  )
}

export default function FhirView() {
  const [metadata, setMetadata] = useState(null)
  const [abdm, setAbdm] = useState(null)
  const [patients, setPatients] = useState([])
  const [pid, setPid] = useState('')
  const [exported, setExported] = useState(null)
  const [pasted, setPasted] = useState('')
  const [preview, setPreview] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api.fhirMetadata().then(setMetadata).catch((e) => setError(e.message))
    api.abdmStatus().then(setAbdm).catch((e) => setError(e.message))
    api.listPatients().then((p) => setPatients(Array.isArray(p) ? p : p?.patients || [])).catch(() => {})
  }, [])

  const guard = async (fn) => { setError(null); setBusy(true); try { await fn() } catch (e) { setError(e.message) } finally { setBusy(false) } }
  const doExport = (id) => guard(async () => { setPid(id); setExported(null); if (id) setExported(await api.fhirCaseExport(id)) })
  const download = () => {
    const blob = new Blob([JSON.stringify(exported.bundle, null, 2)], { type: 'application/fhir+json' })
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = `${pid}-fhir-bundle.json`; a.click()
  }
  const doPreview = () => guard(async () => {
    setPreview(null)
    let obj
    try { obj = JSON.parse(pasted) } catch { throw new Error('The pasted text is not valid JSON.') }
    setPreview(await api.fhirImportPreview(obj))
  })

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-on-surface">FHIR interoperability</h2>
        <p className="text-xs text-on-surface-variant mt-0.5">Export case data as a FHIR R4 Bundle and preview inbound Bundles. Validation is structural only.</p>
      </div>
      {error && <div role="alert" className="p-3 rounded-lg bg-red-50 border border-red-200 text-red-700 text-xs">{error}</div>}

      {abdm && (
        <section className="panel p-4 text-xs space-y-1" data-testid="abdm-status">
          <h3 className="text-base font-bold">ABDM</h3>
          <div className="font-semibold">{abdm.connected ? 'Connected' : 'Not connected'}</div>
          <p className="text-on-surface-variant">{abdm.note}</p>
        </section>
      )}

      <section className="panel p-4 space-y-3" data-testid="fhir-export">
        <h3 className="text-base font-bold">Export a case</h3>
        <select aria-label="FHIR case" value={pid} onChange={(e) => doExport(e.target.value)} className="block w-full max-w-sm rounded-lg border border-outline-variant p-2 text-sm">
          <option value="">No case selected</option>
          {patients.map((p) => <option key={p.patient_id} value={p.patient_id}>{p.patient_id}{p.name ? ` — ${p.name}` : ''}</option>)}
        </select>
        {exported && (
          <div className="space-y-2">
            <Issues v={exported.validation} />
            {exported.notes.map((n) => <p key={n} className="text-xs text-outline">{n}</p>)}
            <button onClick={download} className="px-3 py-1.5 rounded-lg bg-primary text-white text-xs font-semibold">Download Bundle JSON</button>
            <pre className="p-3 rounded-lg bg-surface-container-low text-xs font-mono overflow-x-auto max-h-64">{JSON.stringify(exported.bundle, null, 2)}</pre>
          </div>
        )}
      </section>

      <section className="panel p-4 space-y-3" data-testid="fhir-import">
        <h3 className="text-base font-bold">Import preview</h3>
        <textarea aria-label="FHIR Bundle JSON" value={pasted} onChange={(e) => setPasted(e.target.value)} rows={6} className="w-full rounded-lg border border-outline-variant p-2 text-xs font-mono" placeholder="Paste a FHIR Bundle as JSON" />
        <button onClick={doPreview} disabled={busy || !pasted.trim()} className="px-3 py-1.5 rounded-lg bg-primary text-white text-xs font-semibold disabled:opacity-50">Validate and preview</button>
        {preview && (
          <div className="space-y-2">
            <Issues v={preview.validation} />
            <p className="text-xs">Phenotype codes found: {preview.mapped.phenotype_codes.join(', ') || 'No matching result'}</p>
            <p className="text-xs text-outline">{preview.note}</p>
          </div>
        )}
      </section>

      <section className="panel">
        <h3>CapabilityStatement</h3>
        <pre className="p-4 rounded-lg bg-surface-container-low text-xs font-mono overflow-x-auto max-h-72">{metadata ? JSON.stringify(metadata, null, 2) : 'Loading...'}</pre>
      </section>
    </div>
  )
}
