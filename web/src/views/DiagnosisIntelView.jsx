import React, { useEffect, useState } from 'react'
import { api, setNavContext } from '../api.js'
import { Loader2 } from 'lucide-react'

function Chip({ children, tone = 'sky' }) {
  const t = { sky: 'bg-sky-50 text-sky-900 border-sky-200', red: 'bg-red-50 text-red-800 border-red-200', amber: 'bg-amber-50 text-amber-800 border-amber-200', gray: 'bg-surface-container text-on-surface-variant border-outline-variant' }[tone]
  return <span className={`px-2 py-0.5 rounded-full border text-[11px] font-semibold ${t}`}>{children}</span>
}

function Panel({ title, testid, children }) {
  return <div className="panel p-3 text-xs space-y-1" data-testid={testid}><div className="font-bold text-sm mb-1">{title}</div>{children}</div>
}

export default function DiagnosisIntelView({ onNavigate }) {
  const [patients, setPatients] = useState([])
  const [pid, setPid] = useState('')
  const [ws, setWs] = useState(null)
  const [sel, setSel] = useState(null)
  const [why, setWhy] = useState(null)
  const [matrix, setMatrix] = useState(null)
  const [disc, setDisc] = useState(null)
  const [wi, setWi] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [msg, setMsg] = useState(null)

  useEffect(() => { api.listPatients().then((p) => setPatients(Array.isArray(p) ? p : p?.patients || [])).catch(() => {}) }, [])

  const load = async (id) => {
    setPid(id); setWs(null); setWhy(null); setMatrix(null); setDisc(null); setWi(null); setSel(null); setError(null)
    if (!id) return
    setBusy(true)
    try {
      const w = await api.dxCase(id)
      setWs(w)
      if (w.available) { setSel(w.top_diagnosis.disease_id); setWhy(await api.dxWhy(id, w.top_diagnosis.disease_id)) }
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  const pickDisease = async (d) => {
    setSel(d.disease_id)
    try { setWhy(await api.dxWhy(pid, d.disease_id)) } catch (e) { setError(e.message) }
  }
  const run = async (fn, set) => { try { set(await fn()) } catch (e) { setError(e.message) } }
  const record = async (m, assertion) => {
    try { await api.phenoImport(pid, [{ hpo_id: m.hpo_id, assertion }]); setMsg(`${m.name} recorded as ${assertion}. Diagnosis recalculated.`); await load(pid) } catch (e) { setError(e.message) }
  }
  const whatIf = async (type, hpo_id) => {
    try { setWi(await api.dxWhatIf(pid, { type, params: { hpo_ids: [hpo_id] } })) } catch (e) { setError(e.message) }
  }
  const askAi = (prompt) => { setNavContext('ai-assistant', { prompt, patient_id: pid, include_diagnosis_intel: true }); onNavigate?.('ai-assistant') }

  const cur = ws?.differential?.find((d) => d.disease_id === sel)
  return (
    <div className="space-y-5" data-testid="dx-intel-view">
      <div>
        <h2 className="text-xl font-bold text-on-surface">Diagnosis Intelligence</h2>
        <p className="text-xs text-on-surface-variant mt-0.5">Clinical Decision Support. Ranking comes from the existing engine (phenotype similarity x Indian population prior); clinician review required. Variants are shown as separate genomic support and do not change the ranking.</p>
      </div>
      {error && <div role="alert" className="rounded-lg border border-red-200 bg-red-50 text-red-800 text-xs px-3 py-2">{error}</div>}
      {msg && <div role="status" className="rounded-lg border border-emerald-200 bg-emerald-50 text-emerald-800 text-xs px-3 py-2">{msg}</div>}
      <div className="panel p-4">
        <label className="text-xs font-semibold">Case
          <select aria-label="Case" value={pid} onChange={(e) => load(e.target.value)} className="mt-1 block w-full max-w-sm rounded-lg border border-outline-variant p-2 text-sm font-normal">
            <option value="">No case selected</option>
            {patients.map((p) => <option key={p.patient_id} value={p.patient_id}>{p.patient_id}{p.name ? ` — ${p.name}` : ''}</option>)}
          </select>
        </label>
      </div>
      {busy && <Loader2 className="animate-spin text-primary" size={16} />}
      {ws && (
        <>
          <Panel title="Case summary" testid="dx-summary">
            <div>{ws.summary.age ?? 'Age not documented'} y · {ws.summary.sex || 'Sex not documented'} · {ws.summary.state} · {ws.summary.community}</div>
            <div>{ws.summary.phenotypes} phenotype(s) used · {ws.summary.explicitly_absent} explicitly absent · {ws.summary.uncertain} uncertain · {ws.summary.saved_evidence} saved evidence item(s)</div>
            <div>{ws.summary.variant_note || `${ws.summary.variants} variant(s)`} · {ws.summary.pedigree_note || `${ws.summary.pedigree_members} pedigree member(s)`}</div>
          </Panel>
          {!ws.available ? <p data-testid="dx-empty" className="text-xs text-on-surface-variant">{ws.note}</p> : (
            <>
              <Panel title="Differential diagnosis" testid="dx-differential">
                <table className="w-full"><thead><tr className="text-left text-on-surface-variant"><th>#</th><th>Disease</th><th>Probability</th><th>Similarity</th><th>Genes</th><th>Variants</th><th>Evidence</th></tr></thead>
                  <tbody>{ws.differential.map((d) => (
                    <tr key={d.disease_id} onClick={() => pickDisease(d)} className={`border-t border-outline-variant/30 cursor-pointer ${sel === d.disease_id ? 'bg-primary/5' : ''}`}>
                      <td>{d.rank}</td><td className="py-1 font-semibold">{d.disease_name}{d.rank === 1 && <span className="ml-1"><Chip>Top</Chip></span>}</td>
                      <td>{d.probability}</td><td>{d.phenotype_similarity}</td><td>{d.genes.join(', ') || '—'}</td>
                      <td>{d.variants.length ? d.variants.map((v) => v.gene_symbol).join(', ') : (ws.summary.variant_note ? 'Not analyzed' : 'None matching')}</td>
                      <td>{d.evidence_quality.label}</td>
                    </tr>))}</tbody></table>
              </Panel>
              {cur && (
                <div className="grid lg:grid-cols-2 gap-4" data-testid="dx-detail">
                  <Panel title={`Why ${cur.rank === 1 ? 'ranked first' : `rank ${cur.rank}`}: ${cur.disease_name}`} testid="dx-why">
                    {why && why.disease_id === cur.disease_id ? (<>
                      <ul className="list-disc ml-4 space-y-0.5">{why.explanation.map((l) => <li key={l}>{l}</li>)}</ul>
                      <div className="text-[11px] text-outline pt-1">Factors: similarity {why.factors.phenotype_similarity} · prior relative weight {why.factors.relative_prior_weight} · prior applied {String(why.factors.prior_applied)}</div>
                    </>) : <Loader2 size={14} className="animate-spin" />}
                  </Panel>
                  <Panel title="Supporting and missing findings" testid="dx-findings">
                    <div><b>Supporting:</b> {cur.supporting_phenotypes.map((s) => `${s.name} (${s.weight_pct}%)`).join('; ') || 'none'}</div>
                    <div className="space-y-1"><b>Not documented:</b>
                      {cur.missing_findings.length === 0 && <span> none</span>}
                      {cur.missing_findings.map((m) => (
                        <div key={m.hpo_id} className="flex items-center gap-2"><span>{m.name}</span><Chip tone="gray">{m.status}</Chip>
                          <button onClick={() => record(m, 'present')} className="ml-auto text-primary">Present</button>
                          <button onClick={() => record(m, 'absent')} className="text-primary">Absent</button>
                          <button onClick={() => whatIf('phenotype_add', m.hpo_id)} className="text-primary">What if present?</button></div>))}
                    </div>
                    <div><b>Evidence:</b> {cur.evidence_quality.note}</div>
                  </Panel>
                </div>
              )}
              <div className="flex flex-wrap gap-2">
                <button onClick={() => run(() => api.dxMatrix(pid), setMatrix)} className="px-3 py-1.5 rounded-lg border border-primary/30 text-primary text-xs font-semibold">Show differential matrix</button>
                <button onClick={() => run(() => api.dxDiscriminating(pid), setDisc)} className="px-3 py-1.5 rounded-lg border border-primary/30 text-primary text-xs font-semibold">Which finding would change the differential?</button>
                <button onClick={() => askAi('Why is the first diagnosis ranked first, and what evidence is missing?')} className="px-3 py-1.5 rounded-lg border border-primary/30 text-primary text-xs font-semibold">Ask AI Assistant</button>
                <button onClick={() => onNavigate?.('digital-twin')} className="px-3 py-1.5 rounded-lg border border-primary/30 text-primary text-xs font-semibold">Open Digital Twin</button>
                <button onClick={() => onNavigate?.('pedigree')} className="px-3 py-1.5 rounded-lg border border-primary/30 text-primary text-xs font-semibold">Pedigree</button>
                <button onClick={() => onNavigate?.('evidence')} className="px-3 py-1.5 rounded-lg border border-primary/30 text-primary text-xs font-semibold">Evidence</button>
              </div>
            </>
          )}
        </>
      )}
      {matrix && (
        <Panel title="Differential matrix" testid="dx-matrix">
          <div className="overflow-x-auto"><table className="text-xs"><thead><tr><th className="text-left pr-3">Disease</th>{matrix.columns.map((c) => <th key={c.hpo_id} className="px-2 text-left">{c.name}</th>)}<th className="px-2">Explicitly absent</th></tr></thead>
            <tbody>{matrix.rows.map((r) => (
              <tr key={r.disease_id} className="border-t border-outline-variant/30"><td className="pr-3 py-1 font-semibold">{r.rank}. {r.disease_name}</td>
                {r.cells.map((c) => <td key={c.hpo_id} className={`px-2 ${c.matched ? 'bg-sky-50 font-semibold' : 'text-outline'}`}>{c.matched ? c.similarity : 'No match'}</td>)}
                <td className="px-2">{r.explicitly_absent.map((a) => a.name).join(', ') || '—'}</td></tr>))}</tbody></table></div>
          <p className="text-[11px] text-outline">{matrix.legend}</p>
        </Panel>
      )}
      {disc && (
        <Panel title="Findings that would change the differential" testid="dx-discriminating">
          <p>Current top: {disc.current_top} ({disc.current_probability}). {disc.note}</p>
          {disc.probes.map((p) => (
            <div key={p.hpo_id} className="flex gap-2 items-center"><span className="font-semibold">{p.name}</span><Chip tone="gray">{p.status}</Chip>
              {p.changes_top_diagnosis ? <Chip tone="amber">Top becomes {p.top_after} ({p.top_probability_after})</Chip> : <span className="text-on-surface-variant">Top stays; probability change {p.top_probability_change}</span>}</div>))}
        </Panel>
      )}
      {wi && (
        <Panel title={`What-if: ${wi.type_label}`} testid="dx-whatif">
          <div className="grid md:grid-cols-2 gap-3">
            {[['Baseline', wi.baseline], ['Scenario', wi.scenario]].map(([t, b]) => (
              <div key={t}><div className="font-semibold">{t}: {b.top_diagnosis || 'none'}</div>
                <ol className="list-decimal ml-4">{b.differential.map((d) => <li key={d.disease_id}>{d.disease_name} — {d.probability}</li>)}</ol></div>))}
          </div>
          <p>{wi.top_diagnosis_changed ? 'Top diagnosis changed.' : 'Top diagnosis unchanged.'} {wi.explanation.join(' ')}</p>
          <p className="text-outline">{wi.note}</p>
        </Panel>
      )}
      <p className="text-[11px] text-outline">Clinical Decision Support. Clinician review required.</p>
    </div>
  )
}
