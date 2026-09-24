import React, { useState } from 'react'
import { api } from '../api.js'

export default function DiagnosisView() {
  const [text, setText] = useState('6 mahine se pet kharab, aankhon mein brown ring, chalna mushkil ho gaya')
  const [state, setState] = useState('Andhra Pradesh')
  const [community, setCommunity] = useState('')
  const [sex, setSex] = useState('')
  const [res, setRes] = useState(null)
  const [detail, setDetail] = useState(null)
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)

  async function run() {
    setBusy(true); setErr(null); setRes(null); setDetail(null)
    try {
      const body = { text, state, community, sex, top_k: 10, explain: true }
      const r = await api.diagnose(body)
      setRes(r)
      if (r.results?.length) setDetail(await api.explain(body))
    } catch (ex) { setErr(ex.message) } finally { setBusy(false) }
  }

  async function openDisease(id) {
    try { setDetail(await api.diseaseDetail(id)) } catch (ex) { setErr(ex.message) }
  }

  return (
    <>
      <h2>Differential Diagnosis</h2>
      <p className="lede">Enter the patient's findings in English, Hindi, or Hinglish. India-specific context re-ranks the results.</p>

      <div className="panel">
        <label>Clinical note / symptoms</label>
        <textarea value={text} onChange={e => setText(e.target.value)} />
        <div className="row" style={{ marginTop: 12 }}>
          <div><label>Patient state</label>
            <input value={state} onChange={e => setState(e.target.value)} placeholder="e.g. Andhra Pradesh" /></div>
          <div><label>Community (optional)</label>
            <input value={community} onChange={e => setCommunity(e.target.value)} placeholder="e.g. Gond" /></div>
          <div><label>Sex</label>
            <select value={sex} onChange={e => setSex(e.target.value)}>
              <option value="">Not stated</option><option>M</option><option>F</option>
            </select></div>
          <div style={{ flex: 0 }}>
            <label>&nbsp;</label>
            <button className="primary" onClick={run} disabled={busy || !text.trim()}>
              {busy ? 'Analyzing…' : 'Diagnose'}
            </button>
          </div>
        </div>
      </div>

      {err && <div className="alert error">{err}</div>}
      {res && res.engine && (
        <div className="alert info">
          Engine: {res.engine} · {res.results?.length || 0} candidates ranked by phenotype evidence + Indian population prior
        </div>
      )}

      {res?.results?.length > 0 && (
        <div className="panel">
          <h3>Ranked differential</h3>
          <table>
            <thead><tr><th>#</th><th>Disease</th><th>Probability</th><th>Inheritance</th><th>India context</th><th>Confirmatory tests</th></tr></thead>
            <tbody>
              {res.results.map((r, i) => (
                <tr key={r.disease_id}>
                  <td>{i + 1}</td>
                  <td>
                    <a href="#" onClick={e => { e.preventDefault(); openDisease(r.disease_id) }}><b>{r.disease_name}</b></a>
                    <div className="note">{r.disease_id}</div>
                  </td>
                  <td style={{ minWidth: 130 }}>
                    {(r.probability * 100).toFixed(1)}%
                    <div className="bar"><div style={{ width: `${Math.min(100, r.probability * 100)}%` }} /></div>
                    <div className="note">CI {fmt(r.probability_ci?.[0])}–{fmt(r.probability_ci?.[1])}</div>
                  </td>
                  <td>{r.inheritance || '—'}</td>
                  <td className="kv">
                    {r.population_prior?.consanguinity_multiplier !== 1 && <div><b>consanguinity</b> ×{r.population_prior?.consanguinity_multiplier}</div>}
                    {r.population_prior?.founder_multiplier !== 1 && <div><b>founder</b> ×{r.population_prior?.founder_multiplier}</div>}
                    {r.population_prior?.india_notes?.map((n, j) => <div key={j} className="note">{n}</div>)}
                  </td>
                  <td style={{ fontSize: 13 }}>{r.confirmatory_tests?.first_line?.join(', ') || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {detail?.driving_symptoms && (
        <div className="panel">
          <h3>Why this ranking? (XAI)</h3>
          <table>
            <thead><tr><th>Finding</th><th>Weight</th></tr></thead>
            <tbody>
              {detail.driving_symptoms.map(d => (
                <tr key={d.patient_term || d.hpo_id}>
                  <td>{d.name || d.patient_term || d.hpo_id}</td>
                  <td style={{ minWidth: 160 }}>
                    {d.weight_pct ?? '—'}%
                    <div className="bar"><div style={{ width: `${d.weight_pct || 0}%` }} /></div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {detail.missing_findings?.length > 0 && (
            <>
              <h3 style={{ marginTop: 16 }}>Findings that would raise certainty</h3>
              <ul className="kv">{detail.missing_findings.map(m => <li key={m.hpo_id}>{m.hpo_name} — {m.would_increase}</li>)}</ul>
            </>
          )}
        </div>
      )}

      {detail?.disease && (
        <div className="panel">
          <h3>{detail.disease.name}</h3>
          <div className="kv">
            <div><b>Prevalence</b> {detail.disease.prevalence_per_100k ?? '—'} / 100k</div>
            <div><b>Genes</b> {detail.genes?.join(', ') || '—'}</div>
          </div>
          {detail.founder_risk?.length > 0 && <div className="note">Founder risk: {detail.founder_risk.map(f => `${f.community} — ${f.note}`).join('; ')}</div>}
        </div>
      )}
    </>
  )
}

function fmt(x) { return typeof x === 'number' ? x.toFixed(3) : '?' }
