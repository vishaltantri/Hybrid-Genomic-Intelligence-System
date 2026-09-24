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
            <h3>Risk band: <span className="pill tag">{res.risk_band ?? '—'}</span></h3>
            <table>
              <thead><tr><th>Condition</th><th>Carrier risk</th><th>Child risk</th></tr></thead>
              <tbody>
                {(res.assessments || res.results || res.top || []).slice(0, 10).map((r, i) => (
                  <tr key={i}>
                    <td>{r.disease_name || r.condition || r.name || '—'}</td>
                    <td>{fmtPct(r.carrier_risk_a ?? r.partner_a_carrier ?? r.carrier_risk)}</td>
                    <td>{fmtPct(r.child_risk ?? r.affected_child_risk)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="panel">
            <h3>Report</h3>
            {typeof res.report === 'string'
              ? <div style={{ whiteSpace: 'pre-wrap', fontSize: 14, lineHeight: 1.55 }}>{res.report}</div>
              : <pre style={{ whiteSpace: 'pre-wrap', fontSize: 13, background: 'var(--bg)', padding: 14, borderRadius: 8 }}>{JSON.stringify(res, (k, v) => (k === 'report' ? undefined : v), 2)}</pre>}
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
