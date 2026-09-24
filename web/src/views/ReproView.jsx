import React, { useState } from 'react'
import { api } from '../api.js'

export default function ReproView() {
  const [aCommunity, setACommunity] = useState('Sindhi')
  const [bCommunity, setBCommunity] = useState('Punjabi Khatri')
  const [state, setState] = useState('')
  const [relation, setRelation] = useState('')
  const [lang, setLang] = useState('en')
  const [res, setRes] = useState(null)
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)

  async function run() {
    setBusy(true); setErr(null); setRes(null)
    try {
      const mk = (community) => {
        const p = { community, sex: 'F' }
        if (state.trim()) p.state = state.trim()
        if (relation) p.relationship = relation
        return p
      }
      setRes(await api.counsel({
        partner_a: mk(aCommunity),
        partner_b: { ...mk(bCommunity), sex: 'M' },
        lang,
      }))
    } catch (ex) { setErr(ex.message) } finally { setBusy(false) }
  }

  return (
    <>
      <h2>Family Planning Counselor</h2>
      <p className="lede">Couple carrier risk across recessive conditions, with a printable report in the family's language.</p>

      <div className="panel">
        <div className="row">
          <div><label>Partner A — community</label><input value={aCommunity} onChange={e => setACommunity(e.target.value)} /></div>
          <div><label>Partner B — community</label><input value={bCommunity} onChange={e => setBCommunity(e.target.value)} /></div>
          <div><label>State (optional)</label><input value={state} onChange={e => setState(e.target.value)} /></div>
          <div><label>Relation (if consanguineous)</label>
            <select value={relation} onChange={e => setRelation(e.target.value)}>
              <option value="">Not related</option>
              <option value="first_cousins">First cousins</option>
              <option value="uncle_niece">Uncle–niece</option>
            </select></div>
          <div><label>Report language</label>
            <select value={lang} onChange={e => setLang(e.target.value)}>
              <option value="en">English</option><option value="hi">हिंदी</option><option value="ta">தமிழ்</option>
            </select></div>
        </div>
        <div style={{ marginTop: 14 }}>
          <button className="primary" onClick={run} disabled={busy}>
            {busy ? 'Computing…' : 'Generate counseling report'}
          </button>
        </div>
      </div>

      {err && <div className="alert error">{err}</div>}

      {res && (
        <>
          <div className="panel">
            <h3>Risk band: <span className="pill tag">{res.risk_band ?? '—'}</span>
              {res.inbreeding_coefficient != null && <span className="note" style={{ marginLeft: 12 }}>inbreeding coefficient {res.inbreeding_coefficient}</span>}
              {res.regional_consanguinity_flag && <span className="pill amber" style={{ marginLeft: 12 }}>high-consanguinity region</span>}
            </h3>
            <table>
              <thead><tr><th>Condition</th><th>Partner A</th><th>Partner B</th><th>Both carriers</th><th>Child affected</th></tr></thead>
              <tbody>
                {(res.top_risks || []).slice(0, 10).map(r => (
                  <tr key={r.disease_id}>
                    <td>
                      <b>{r.disease_name}</b>
                      <div className="note">{r.inheritance}{r.gene ? ` · ${r.gene}` : ''} · {r.one_in_n_children}</div>
                    </td>
                    <td>{fmtPct(prob(r.carrier_probability_partner_a))}</td>
                    <td>{fmtPct(prob(r.carrier_probability_partner_b))}</td>
                    <td>{fmtPct(prob(r.both_carriers_probability))}</td>
                    <td><b>{fmtPct(prob(r.child_affected_probability))}</b></td>
                  </tr>
                ))}
              </tbody>
            </table>
            {res.high_risk_conditions?.length > 0 && (
              <p className="note">High-risk: {res.high_risk_conditions.join(', ')}</p>
            )}
          </div>
          <div className="row">
            {res.recommended_screening?.length > 0 && (
              <div className="panel">
                <h3>Recommended screening</h3>
                <ul className="kv">{res.recommended_screening.map((s, i) => <li key={i}><b>{s.condition}</b> — {s.test} ({s.timing})</li>)}</ul>
              </div>
            )}
            {res.government_schemes?.length > 0 && (
              <div className="panel">
                <h3>Government support</h3>
                <ul className="kv">{res.government_schemes.slice(0, 4).map((s, i) => <li key={i}><b>{s.name}</b> — {s.benefit}</li>)}</ul>
              </div>
            )}
          </div>
          <div className="panel">
            <h3>Report</h3>
            {typeof res.report === 'string'
              ? <div style={{ whiteSpace: 'pre-wrap', fontSize: 14, lineHeight: 1.55 }}>{res.report}</div>
              : <pre style={{ whiteSpace: 'pre-wrap', fontSize: 13, background: 'var(--bg)', padding: 14, borderRadius: 8 }}>{res.report?.markdown || JSON.stringify(res, (k, v) => (k === 'report' ? undefined : v), 2)}</pre>}
            <p className="note">{res.disclaimer}</p>
          </div>
        </>
      )}
    </>
  )
}

function fmtPct(x) {
  if (x == null) return '—'
  const n = Number(x)
  if (Number.isNaN(n)) return String(x)
  return n <= 1 ? `${(n * 100).toFixed(2)}%` : `${n.toFixed(2)}%`
}

// carrier probabilities arrive either as numbers or as {probability, method, note}
function prob(v) {
  if (v && typeof v === 'object') return v.probability
  return v
}
