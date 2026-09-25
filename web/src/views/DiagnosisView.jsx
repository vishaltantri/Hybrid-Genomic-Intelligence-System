import React, { useEffect, useState } from 'react'
import { api } from '../api.js'

export default function DiagnosisView() {
  const [text, setText] = useState('6 mahine se pet kharab, aankhon mein brown ring, chalna mushkil ho gaya')
  const [state, setState] = useState('Andhra Pradesh')
  const [community, setCommunity] = useState('')
  const [sex, setSex] = useState('')
  const [states, setStates] = useState([])
  const [communities, setCommunities] = useState([])
  const [res, setRes] = useState(null)
  const [mapped, setMapped] = useState(null)  // what the NER understood: hpo terms + unmapped
  const [xai, setXai] = useState(null)        // /xai/explain bundle: {diagnosis, explanation}
  const [detail, setDetail] = useState(null)  // /diseases/{id}: {disease, phenotypes, genes, founder_risk}
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api.reference().then(r => { setStates(r.states || []); setCommunities(r.communities || []) }).catch(() => {})
  }, [])

  async function run() {
    setBusy(true); setErr(null); setRes(null); setXai(null); setDetail(null); setMapped(null)
    try {
      const body = { text, state, community, sex, top_k: 10 }
      // show what the system understood, even when it finds nothing
      try {
        const m = await api.mapHpo({ text })
        setMapped(m)
      } catch { /* non-fatal */ }
      const r = await api.diagnose(body)
      setRes(r)
      if (r.results?.length) {
        try { setXai(await api.explain({ ...body, top_k: 5 })) } catch { /* XAI optional */ }
      }
    } catch (ex) { setErr(ex.message) } finally { setBusy(false) }
  }

  async function openDisease(id) {
    setErr(null)
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
          <div><label>Patient state (sets consanguinity prior)</label>
            <select value={state} onChange={e => setState(e.target.value)}>
              <option value="">Not stated</option>
              {states.map(s => <option key={s.id} value={s.id}>{s.name}{s.consanguinity_rate ? ` (${s.consanguinity_rate}%)` : ''}</option>)}
            </select></div>
          <div><label>Community (optional, sets founder prior)</label>
            <select value={community} onChange={e => setCommunity(e.target.value)}>
              <option value="">Not stated</option>
              {communities.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select></div>
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

      {mapped && (
        <div className="alert info">
          <b>Understood findings:</b>{' '}
          {mapped.hpo_profile?.length
            ? mapped.hpo_profile.map(h => `${h.hpo_name || h.hpo_id} (${Math.round((h.confidence || 0) * 100)}%)`).join(' · ')
            : 'none — try describing symptoms differently (e.g. “piliya”, “daure”, “pet mein dard”)'}
          {mapped.unmapped_symptoms?.length > 0 && (
            <div className="note">Could not map: {mapped.unmapped_symptoms.join(', ')}</div>
          )}
        </div>
      )}

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

      {xai?.explanation && (
        <div className="panel">
          <h3>Why #{1} — {xai.explanation.disease_name}? (XAI)</h3>
          <div className="note" style={{ marginBottom: 10 }}>
            Attribution method: {xai.explanation.attribution?.method || '—'} · probability {fmt(xai.explanation.probability)}
          </div>
          <table>
            <thead><tr><th>Finding</th><th>Contribution</th><th>Weight</th></tr></thead>
            <tbody>
              {(xai.explanation.attribution?.attributions || []).map(a => (
                <tr key={a.hpo_id}>
                  <td>{a.hpo_name || a.hpo_id}</td>
                  <td>{typeof a.contribution === 'number' ? a.contribution.toFixed(3) : '—'}</td>
                  <td style={{ minWidth: 160 }}>
                    {a.weight_pct ?? '—'}%
                    <div className="bar"><div style={{ width: `${a.weight_pct || 0}%` }} /></div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {xai.explanation.missing_findings?.length > 0 && (
            <>
              <h3 style={{ marginTop: 16 }}>Findings that would raise certainty</h3>
              <ul className="kv">{xai.explanation.missing_findings.slice(0, 5).map(m => <li key={m.hpo_id}>{m.hpo_name} — {m.would_increase}</li>)}</ul>
            </>
          )}
          {xai.explanation.case_based_reasoning?.similar_cases?.length > 0 && (
            <p className="note">Similar past cases: {xai.explanation.case_based_reasoning.similar_cases.length} retrieved from the case archive.</p>
          )}
          {typeof xai.explanation.narrative?.markdown === 'string' && (
            <details style={{ marginTop: 10 }}>
              <summary style={{ cursor: 'pointer', fontSize: 13, color: 'var(--accent)' }}>Full written explanation</summary>
              <pre style={{ whiteSpace: 'pre-wrap', fontSize: 13, background: 'var(--bg)', padding: 14, borderRadius: 8, marginTop: 8 }}>
{xai.explanation.narrative.markdown}
              </pre>
            </details>
          )}
        </div>
      )}

      {detail?.disease && (
        <div className="panel">
          <h3>{detail.disease.name}</h3>
          <div className="kv">
            <div><b>Prevalence</b> {detail.disease.prevalence_per_100k ?? '—'} / 100k</div>
            <div><b>Inheritance</b> {detail.disease.inheritance || '—'}</div>
            <div><b>Genes</b> {detail.genes?.join(', ') || '—'}</div>
          </div>
          {detail.phenotypes?.length > 0 && (
            <p className="note">{detail.phenotypes.length} phenotype annotations. Top: {detail.phenotypes.slice(0, 6).map(p => p.name).join(' · ')}</p>
          )}
          {detail.founder_risk?.length > 0 && <div className="note">Founder risk: {detail.founder_risk.map(f => `${f.community} — ${f.note}`).join('; ')}</div>}
        </div>
      )}
    </>
  )
}

function fmt(x) { return typeof x === 'number' ? x.toFixed(3) : '?' }
