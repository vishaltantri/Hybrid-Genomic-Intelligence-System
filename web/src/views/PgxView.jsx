import React, { useEffect, useState } from 'react'
import { api } from '../api.js'

export default function PgxView() {
  const [drugs, setDrugs] = useState('clopidogrel, primaquine')
  const [state, setState] = useState('')
  const [ethnicity, setEthnicity] = useState('')
  const [genotypes, setGenotypes] = useState('CYP2C19: *2/*2, G6PD: deficient')
  const [coverage, setCoverage] = useState(null)
  const [res, setRes] = useState(null)
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => { api.pgxCoverage().then(setCoverage).catch(() => {}) }, [])

  async function run() {
    setBusy(true); setErr(null); setRes(null)
    try {
      const known = {}
      genotypes.split(',').forEach(pair => {
        const [gene, gt] = pair.split(':')
        if (gene?.trim() && gt?.trim()) known[gene.trim()] = gt.trim()
      })
      const body = { drugs: drugs.split(',').map(d => d.trim()).filter(Boolean), lang: 'en' }
      if (state.trim()) body.state = state.trim()
      if (ethnicity.trim()) body.ethnicity = ethnicity.trim()
      if (Object.keys(known).length) body.known_genotypes = known
      setRes(await api.pgxCheck(body))
    } catch (ex) { setErr(ex.message) } finally { setBusy(false) }
  }

  return (
    <>
      <h2>Drug Safety (Pharmacogenomics)</h2>
      <p className="lede">Screen a prescription against drug–gene risk rules, using Indian population allele frequencies.</p>

      <div className="panel">
        <label>Medications to check</label>
        <input value={drugs} onChange={e => setDrugs(e.target.value)} />
        <div className="row" style={{ marginTop: 12 }}>
          <div><label>Patient state (optional)</label>
            <input value={state} onChange={e => setState(e.target.value)} placeholder="e.g. Gujarat" /></div>
          <div><label>Community (optional)</label>
            <input value={ethnicity} onChange={e => setEthnicity(e.target.value)} placeholder="e.g. Sindhi" /></div>
        </div>
        <label style={{ marginTop: 12 }}>Known gene variants (gene: genotype, comma-separated)</label>
        <input value={genotypes} onChange={e => setGenotypes(e.target.value)} />
        <div style={{ marginTop: 14 }}>
          <button className="primary" onClick={run} disabled={busy || !drugs.trim()}>
            {busy ? 'Checking…' : 'Assess risk'}
          </button>
        </div>
      </div>

      {err && <div className="alert error">{err}</div>}

      {res && (
        <div className="panel">
          <h3>Prescription check</h3>
          {typeof res.report === 'string' && res.report
            ? <div style={{ whiteSpace: 'pre-wrap', fontSize: 14, lineHeight: 1.55 }}>{res.report}</div>
            : null}
          <pre style={{ whiteSpace: 'pre-wrap', fontSize: 12.5, background: 'var(--bg)', padding: 14, borderRadius: 8, marginTop: 12 }}>
{JSON.stringify(res, (k, v) => (k === 'report' ? undefined : v), 2)}
          </pre>
        </div>
      )}

      {coverage && (
        <div className="panel">
          <h3>Coverage: {coverage.n_pairs} drug–gene pairs ({coverage.n_critical} critical)</h3>
          <table>
            <thead><tr>{Object.keys(coverage.rows[0] || {}).slice(0, 5).map(h => <th key={h}>{h}</th>)}</tr></thead>
            <tbody>
              {coverage.rows.slice(0, 12).map((r, i) => (
                <tr key={i}>{Object.keys(coverage.rows[0] || {}).slice(0, 5).map(h => <td key={h}>{String(r[h])}</td>)}</tr>
              ))}
            </tbody>
          </table>
          <p className="note">Sources: PharmGKB / CPIC pairs × Indian allele frequencies (IndiGenomes).</p>
        </div>
      )}
    </>
  )
}
