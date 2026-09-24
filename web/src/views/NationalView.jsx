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
          <h3>Cases by state (month: {nat?.month ?? '—'})</h3>
          <table>
            <thead><tr><th>State</th><th>Cases</th><th>Detail</th></tr></thead>
            <tbody>
              {rows.slice(0, 15).map(r => (
                <tr key={r.state}>
                  <td><b>{r.state}</b></td>
                  <td>{typeof r.cases === 'number' ? r.cases.toLocaleString('en-IN') : r.cases}</td>
                  <td className="note">{r.top}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {nat?.totals && <p className="note">Total {nat.totals.cases?.toLocaleString?.('en-IN') ?? nat.totals.cases} cases across {nat.totals.states_reporting} states.</p>}
        </div>
      )}

      {brief && (
        <div className="panel">
          <h3>Policy brief{brief.month ? ` — ${brief.month}` : ''}</h3>
          {typeof brief.markdown === 'string'
            ? <div style={{ whiteSpace: 'pre-wrap', fontSize: 13.5, lineHeight: 1.5 }}>{brief.markdown}</div>
            : typeof brief.brief === 'string'
              ? <div style={{ whiteSpace: 'pre-wrap', fontSize: 13.5 }}>{brief.brief}</div>
              : <pre style={{ whiteSpace: 'pre-wrap', fontSize: 13 }}>{JSON.stringify(brief, null, 2)}</pre>}
          {brief.data_note && <p className="note">{brief.data_note}</p>}
        </div>
      )}
    </>
  )
}

// Real payload shape: { month, states: [{state, cases, confirmed, red_flagged,
// access_gap_score, gap_label, consanguinity_rate}], totals, data_note }.
function extractRows(nat) {
  if (!nat) return []
  const list = nat.states || nat.rows || []
  return (Array.isArray(list) ? list : []).map(x => ({
    state: x.state || x.name || '—',
    cases: x.cases ?? x.estimated_cases ?? x.total ?? '—',
    top: [x.gap_label, x.confirmed != null ? `${x.confirmed} confirmed` : null,
          x.red_flagged != null ? `${x.red_flagged} red-flagged` : null,
          x.consanguinity_rate != null ? `consanguinity ${x.consanguinity_rate}%` : null]
      .filter(Boolean).join(' · '),
  }))
}
