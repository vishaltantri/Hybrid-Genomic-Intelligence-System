import React, { useState } from 'react'
import { api } from '../api.js'

export default function PgxView() {
  const [genes, setGenes] = useState('CYP2C19 *2/*2; G6PD deficient')
  const [drugs, setDrugs] = useState('clopidogrel, primaquine')
  const [res, setRes] = useState(null)
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)

  async function run() {
    setBusy(true); setErr(null); setRes(null)
    try {
      setRes(await api.pgx({ genes, drugs, population: 'Indian' }))
    } catch (ex) { setErr(ex.message) } finally { setBusy(false) }
  }

  return (
    <>
      <h2>Drug Safety (Pharmacogenomics)</h2>
      <p className="lede">Check medications against the patient's gene variants, using Indian population frequencies.</p>

      <div className="panel">
        <label>Gene variants / findings</label>
        <textarea value={genes} onChange={e => setGenes(e.target.value)} />
        <label style={{ marginTop: 10 }}>Medications to check</label>
        <input value={drugs} onChange={e => setDrugs(e.target.value)} />
        <div style={{ marginTop: 14 }}>
          <button className="primary" onClick={run} disabled={busy}>{busy ? 'Checking…' : 'Assess risk'}</button>
        </div>
      </div>

      {err && <div className="alert error">{err}</div>}

      {res && (
        <div className="panel">
          <h3>Results</h3>
          <pre style={{ whiteSpace: 'pre-wrap', fontSize: 13, background: 'var(--bg)', padding: 14, borderRadius: 8 }}>
{JSON.stringify(res, null, 2)}
          </pre>
          <p className="note">Structured output shown raw — the counseling report views render the formatted version per language.</p>
        </div>
      )}
    </>
  )
}
