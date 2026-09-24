import React, { useEffect, useState } from 'react'
import { api } from '../api.js'

export default function NationalView() {
  const [nat, setNat] = useState(null)
  const [brief, setBrief] = useState(null)
  const [err, setErr] = useState(null)

  useEffect(() => {
    Promise.all([api.national(), api.policyBrief().catch(() => null)])
      .then(([n, b]) => { setNat(n); setBrief(b) })
      .catch(ex => setErr(ex.message))
  }, [])

  const rows = extractRows(nat)

  return (
    <>
      <h2>National Rare Disease View</h2>
      <p className="lede">State-wise burden and screening gaps.</p>
      <div className="alert info">Simulated data — generated from knowledge-graph prevalence; India's official registry (ICMR NRROID) is not publicly downloadable.</div>
      {err && <div className="alert error">{err}</div>}

      {rows.length > 0 && (
        <div className="panel">
          <h3>Estimated cases by state</h3>
          <table>
            <thead><tr><th>State</th><th>Cases</th><th>Top disease groups</th></tr></thead>
            <tbody>
              {rows.slice(0, 15).map(r => (
                <tr key={r.state}>
                  <td><b>{r.state}</b></td>
                  <td>{typeof r.cases === 'number' ? r.cases.toLocaleString('en-IN') : r.cases}</td>
                  <td className="note">{r.top || ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {brief && (
        <div className="panel">
          <h3>Policy brief</h3>
          {typeof brief.brief === 'string'
            ? <div style={{ whiteSpace: 'pre-wrap', fontSize: 14 }}>{brief.brief}</div>
            : <pre style={{ whiteSpace: 'pre-wrap', fontSize: 13 }}>{JSON.stringify(brief, null, 2)}</pre>}
        </div>
      )}
    </>
  )
}

// The national payload shape varies (states list / dict); normalize defensively.
function extractRows(nat) {
  if (!nat) return []
  const list = nat.states || nat.rows || nat.data || (typeof nat === 'object' ? null : null)
  if (Array.isArray(list)) {
    return list.map(x => ({
      state: x.state || x.name || x.state_name || '—',
      cases: x.cases ?? x.estimated_cases ?? x.total ?? '—',
      top: x.top_diseases?.join?.(', ') || x.top_group || '',
    }))
  }
  if (typeof nat === 'object') {
    return Object.entries(nat).filter(([, v]) => typeof v === 'object').map(([k, v]) => ({
      state: k, cases: v.cases ?? v.estimated_cases ?? v.total ?? '—', top: v.top_diseases?.join?.(', ') || '',
    }))
  }
  return []
}
