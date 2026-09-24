import React, { useState } from 'react'
import { api } from '../api.js'

export default function ReproView() {
  const [mother, setMother] = useState('Sindhi')
  const [father, setFather] = useState('Punjabi Khatri')
  const [consanguineous, setCons] = useState(false)
  const [disease, setDisease] = useState('Beta thalassemia')
  const [lang, setLang] = useState('en')
  const [res, setRes] = useState(null)
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)

  async function run() {
    setBusy(true); setErr(null); setRes(null)
    try {
      setRes(await api.counsel({
        mother_community: mother, father_community: father,
        consanguineous: consanguineous, disease: disease, language: lang,
      }))
    } catch (ex) { setErr(ex.message) } finally { setBusy(false) }
  }

  return (
    <>
      <h2>Family Planning Counselor</h2>
      <p className="lede">Carrier risk for the couple and recurrence risk for children, with a printable report in the family's language.</p>

      <div className="panel">
        <div className="row">
          <div><label>Mother's community</label><input value={mother} onChange={e => setMother(e.target.value)} /></div>
          <div><label>Father's community</label><input value={father} onChange={e => setFather(e.target.value)} /></div>
          <div><label>Concern</label><input value={disease} onChange={e => setDisease(e.target.value)} /></div>
          <div><label>Report language</label>
            <select value={lang} onChange={e => setLang(e.target.value)}>
              <option value="en">English</option><option value="hi">हिंदी</option><option value="ta">தமிழ்</option>
            </select></div>
        </div>
        <div style={{ marginTop: 12 }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 14, color: 'var(--ink)' }}>
            <input type="checkbox" checked={consanguineous} onChange={e => setCons(e.target.checked)} style={{ width: 'auto' }} />
            Parents are blood relatives (consanguineous marriage)
          </label>
        </div>
        <div style={{ marginTop: 14 }}>
          <button className="primary" onClick={run} disabled={busy}>{busy ? 'Computing…' : 'Generate counseling report'}</button>
        </div>
      </div>

      {err && <div className="alert error">{err}</div>}

      {res && (
        <div className="panel">
          <h3>Report</h3>
          {typeof res.report === 'string'
            ? <div style={{ whiteSpace: 'pre-wrap', fontSize: 14, lineHeight: 1.55 }}>{res.report}</div>
            : <pre style={{ whiteSpace: 'pre-wrap', fontSize: 13, background: 'var(--bg)', padding: 14, borderRadius: 8 }}>{JSON.stringify(res, null, 2)}</pre>}
        </div>
      )}
    </>
  )
}
