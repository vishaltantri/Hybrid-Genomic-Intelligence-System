import React, { useEffect, useRef, useState } from 'react'
import { api, consumeNavContext } from '../api.js'
import { Search, Loader2, ArrowRight, CheckCircle2 } from 'lucide-react'

const MATCH_LABEL = { id: 'ID', name: 'Name', synonym: 'Synonym', indian_synonym: 'Hindi / Indian synonym', semantic: 'Semantic' }

function Chip({ children, tone = 'sky' }) {
  const t = { sky: 'bg-sky-50 text-sky-900 border-sky-200', red: 'bg-red-50 text-red-800 border-red-200', amber: 'bg-amber-50 text-amber-800 border-amber-200', gray: 'bg-surface-container text-on-surface-variant border-outline-variant' }[tone]
  return <span className={`px-2 py-0.5 rounded-full border text-[11px] font-semibold ${t}`}>{children}</span>
}

function Panel({ title, testid, children, count }) {
  return (
    <div className="panel p-3 text-xs" data-testid={testid}>
      <div className="font-bold text-sm mb-2">{title}{count != null ? <span className="ml-1 text-outline font-normal">({count})</span> : null}</div>
      {children}
    </div>
  )
}

export default function PhenotypesView({ onNavigateToDiagnosis }) {
  const [patients, setPatients] = useState([])
  const [pid, setPid] = useState('')
  const [q, setQ] = useState('')
  const [hits, setHits] = useState(null)
  const [searchNote, setSearchNote] = useState(null)
  const [term, setTerm] = useState(null)
  const [cs, setCs] = useState(null)
  const [cmp, setCmp] = useState(null)
  const [imp, setImp] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [msg, setMsg] = useState(null)
  const seq = useRef(0)

  useEffect(() => {
    api.listPatients().then((p) => setPatients(Array.isArray(p) ? p : p?.patients || [])).catch(() => {})
    const ctx = consumeNavContext('phenotypes')
    if (ctx?.nlp_import) {
      const n = ctx.nlp_import
      const mk = (arr, assertion) => (arr || []).map((p) => ({ ...p, assertion, selected: true }))
      setImp({ items: [...mk(n.present, 'present'), ...mk(n.absent, 'absent'), ...mk(n.possible, 'possible')], conflicts: n.conflicts || [] })
    }
  }, [])

  useEffect(() => {
    if (q.trim().length < 2) { setHits(null); return undefined }
    const my = ++seq.current
    const t = setTimeout(async () => {
      try {
        const r = await api.phenoSearch(q.trim())
        if (my === seq.current) { setHits(r.results); setSearchNote(r.semantic_note || null); setError(null) }
      } catch (e) { if (my === seq.current) setError(e.message) }
    }, 250)
    return () => clearTimeout(t)
  }, [q])

  const loadCase = async (id = pid) => {
    if (!id) { setCs(null); return }
    setBusy(true); setError(null); setCmp(null)
    try { setCs(await api.phenoCase(id)) } catch (e) { setCs(null); setError(e.message) } finally { setBusy(false) }
  }
  const pick = async (id) => { setPid(id); await loadCase(id) }
  const openTerm = async (hid) => {
    try { setTerm(await api.phenoTerm(hid, pid || undefined)) } catch (e) { setError(e.message) }
  }
  const compare = async (disease_id) => {
    try { setCmp(await api.phenoCompare(pid, disease_id)) } catch (e) { setError(e.message) }
  }
  const addTerm = async (h, assertion) => {
    if (!pid) { setError('Select a case first.'); return }
    try {
      await api.phenoImport(pid, [{ hpo_id: h.hpo_id, assertion, evidence_text: q.trim().slice(0, 200) || undefined }])
      setMsg(`${h.name} recorded as ${assertion} for ${pid}.`); await loadCase(pid)
    } catch (e) { setError(e.message) }
  }
  const confirmImport = async () => {
    const items = imp.items.filter((i) => i.selected).map((i) => ({ hpo_id: i.hpo_id, assertion: i.assertion, evidence_text: i.evidence_text || undefined }))
    try {
      const r = await api.phenoImport(pid, items)
      setMsg(`Imported ${r.present} present and ${r.negated_or_uncertain} negated/uncertain findings into ${pid}.`)
      setImp(null); await loadCase(pid)
    } catch (e) { setError(e.message) }
  }

  return (
    <div className="space-y-5" data-testid="phenotype-view">
      <div>
        <h2 className="text-xl font-bold text-on-surface">Phenotype Intelligence</h2>
        <p className="text-xs text-on-surface-variant mt-0.5">Search HPO by name, synonym, ID, Hindi term or plain phrase, record observed / absent / uncertain findings for a case, and compare them with a disease. Clinical decision support; clinician review required.</p>
      </div>

      {error && <div role="alert" className="rounded-lg border border-red-200 bg-red-50 text-red-800 text-xs px-3 py-2">{error}</div>}
      {msg && <div role="status" className="rounded-lg border border-emerald-200 bg-emerald-50 text-emerald-800 text-xs px-3 py-2 flex gap-2"><CheckCircle2 size={14} />{msg}</div>}

      <div className="panel p-4 grid md:grid-cols-[260px_1fr] gap-4">
        <label className="text-xs font-semibold">Case
          <select aria-label="Case" value={pid} onChange={(e) => pick(e.target.value)} className="mt-1 w-full rounded-lg border border-outline-variant p-2 text-sm font-normal">
            <option value="">No case selected</option>
            {patients.map((p) => <option key={p.patient_id} value={p.patient_id}>{p.patient_id}{p.name ? ` — ${p.name}` : ''}</option>)}
          </select>
        </label>
        <div>
          <label className="text-xs font-semibold" htmlFor="hpo-q">HPO search</label>
          <div className="relative mt-1">
            <Search size={14} className="absolute left-2.5 top-3 text-outline" />
            <input id="hpo-q" aria-label="Search HPO terms" value={q} onChange={(e) => setQ(e.target.value)} maxLength={200}
              placeholder="e.g. tremor, HP:0001337, piliya, yellow skin and eyes" className="w-full pl-8 pr-3 py-2 rounded-lg border border-outline-variant text-sm" />
          </div>
          {searchNote && <p className="text-[11px] text-amber-700 mt-1">{searchNote}</p>}
          {hits && (
            <ul className="mt-2 divide-y divide-outline-variant/30" data-testid="hpo-results">
              {hits.length === 0 && <li className="py-2 text-xs text-on-surface-variant">No matching HPO term.</li>}
              {hits.map((h) => (
                <li key={h.hpo_id} className="py-1.5 flex flex-wrap items-center gap-2 text-xs">
                  <button onClick={() => openTerm(h.hpo_id)} className="font-semibold text-primary text-left">{h.name}</button>
                  <span className="font-mono text-outline">{h.hpo_id}</span>
                  <Chip tone={h.match === 'semantic' ? 'amber' : 'sky'}>{MATCH_LABEL[h.match]}{h.score != null ? ` · ${h.score}` : ''}</Chip>
                  {h.matched_text && h.match !== 'name' && h.match !== 'id' && <span className="text-on-surface-variant">via “{h.matched_text}”</span>}
                  {pid && (
                    <span className="ml-auto flex gap-1">
                      {['present', 'absent', 'possible'].map((a) => <button key={a} onClick={() => addTerm(h, a)} className="px-2 py-0.5 rounded border border-primary/30 text-primary">{a === 'possible' ? 'Uncertain' : a === 'absent' ? 'Absent' : 'Present'}</button>)}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {imp && (
        <Panel title="Review text-derived findings before saving" testid="nlp-import">
          <p className="text-on-surface-variant mb-2">Extracted automatically from clinical text. Nothing is saved until you confirm{pid ? ` for ${pid}` : ' and select a case'}.</p>
          {imp.conflicts.length > 0 && <p role="alert" className="text-amber-800 bg-amber-50 rounded px-2 py-1 mb-2">Documented as both present and absent: {imp.conflicts.map((c) => c.name).join(', ')}.</p>}
          <ul className="space-y-1">
            {imp.items.map((i, k) => (
              <li key={`${i.hpo_id}-${i.assertion}`} className="flex items-center gap-2">
                <input type="checkbox" aria-label={`Include ${i.name}`} checked={i.selected} onChange={() => setImp({ ...imp, items: imp.items.map((x, j) => (j === k ? { ...x, selected: !x.selected } : x)) })} />
                <span className="font-semibold">{i.name}</span><span className="font-mono text-outline">{i.hpo_id}</span>
                <Chip tone={i.assertion === 'present' ? 'sky' : i.assertion === 'absent' ? 'red' : 'amber'}>{i.assertion === 'possible' ? 'uncertain' : i.assertion}</Chip>
              </li>
            ))}
          </ul>
          <div className="flex gap-2 mt-3">
            <button onClick={confirmImport} disabled={!pid || !imp.items.some((i) => i.selected)} className="px-3 py-1.5 rounded-lg bg-primary text-white font-semibold disabled:opacity-50">Confirm and save to case</button>
            <button onClick={() => setImp(null)} className="px-3 py-1.5 rounded-lg border border-outline-variant">Discard</button>
          </div>
        </Panel>
      )}

      {term && (
        <Panel title={`${term.name}`} testid="term-detail">
          <div className="space-y-1">
            <div className="font-mono text-outline">{term.hpo_id}</div>
            <div>{term.definition || 'No definition available.'}</div>
            <div><b>Hierarchy:</b> {term.ancestors.length ? term.ancestors.map((a) => a.name).join(' › ') : 'Top-level term'}</div>
            {term.children.length > 0 && <div><b>More specific:</b> {term.children.map((c) => c.name).join(', ')}</div>}
            <div><b>Synonyms:</b> {[...term.synonyms, ...term.indian_synonyms.map((s) => s.text)].join(', ') || 'None recorded'}</div>
            <div><b>Phenotype → disease → gene:</b></div>
            <ul className="list-disc ml-5">
              {term.diseases.length === 0 && <li>No disease in the knowledge graph lists this term.</li>}
              {term.diseases.map((d) => <li key={d.disease_id}>{d.disease_name} ({d.genes.join(', ') || 'no gene recorded'})</li>)}
            </ul>
            {pid && <div><b>Case variants in those genes:</b> {term.case_variants.length ? term.case_variants.map((v) => `${v.gene_symbol} ${v.hgvs || ''} [${v.acmg_classification || 'unclassified'}]`).join('; ') : (term.variant_note || 'No matching record')}</div>}
          </div>
        </Panel>
      )}

      {busy && <Loader2 className="animate-spin text-primary" size={16} />}
      {!pid && !busy && <p className="text-xs text-on-surface-variant">Select a case to see its observed, absent and uncertain findings.</p>}
      {cs && (
        <div className="grid lg:grid-cols-2 gap-4" data-testid="case-phenotypes">
          <Panel title="Observed" count={cs.observed.length} testid="observed">
            {cs.observed.length === 0 ? <p className="text-on-surface-variant">No phenotypes documented for this case.</p> : (
              <table className="w-full"><thead><tr className="text-left text-on-surface-variant"><th>Term</th><th>Onset</th><th>Severity</th><th>System</th></tr></thead>
                <tbody>{cs.observed.map((o) => (
                  <tr key={o.hpo_id} className="border-t border-outline-variant/30">
                    <td className="py-1"><button onClick={() => openTerm(o.hpo_id)} className="text-primary font-semibold text-left">{o.name}</button> <span className="font-mono text-outline">{o.hpo_id}</span>{!o.in_knowledge_graph && <Chip tone="amber">Not in knowledge graph</Chip>}</td>
                    <td className={o.onset === 'Not documented' ? 'text-outline' : ''}>{o.onset}</td>
                    <td className={o.severity === 'Not documented' ? 'text-outline' : ''}>{o.severity}</td>
                    <td>{o.organ_systems.map((s) => s.name.replace('Abnormality of the ', '')).join(', ') || '—'}</td>
                  </tr>))}</tbody></table>)}
          </Panel>
          <div className="space-y-4">
            <Panel title="Explicitly absent" count={cs.negated.length} testid="negated">
              {cs.negated.length ? cs.negated.map((n) => <Chip key={n.hpo_id} tone="red">{n.name}</Chip>) : <span className="text-on-surface-variant">None recorded.</span>}
            </Panel>
            <Panel title="Uncertain" count={cs.uncertain.length} testid="uncertain">
              {cs.uncertain.length ? cs.uncertain.map((n) => <Chip key={n.hpo_id} tone="amber">{n.name}</Chip>) : <span className="text-on-surface-variant">None recorded.</span>}
              <p className="text-[11px] text-outline mt-1">{cs.note}</p>
            </Panel>
            {cs.conflicts.length > 0 && <div role="alert" className="text-xs rounded bg-amber-50 text-amber-800 px-2 py-1">Conflict: {cs.conflicts.map((c) => c.name).join(', ')}</div>}
          </div>
          <Panel title="Expected for the top diagnosis but not documented" count={cs.not_documented.length} testid="undocumented">
            {cs.diagnosis_note ? <p className="text-on-surface-variant">{cs.diagnosis_note}</p> : cs.not_documented.map((m) => (
              <div key={m.hpo_id} className="flex items-center gap-2 py-0.5"><span>{m.name}</span><Chip tone="gray">{m.status}</Chip>
                <button onClick={() => addTerm(m, 'present')} className="ml-auto text-primary">Present</button><button onClick={() => addTerm(m, 'absent')} className="text-primary">Absent</button></div>))}
          </Panel>
          <Panel title="Compare with a disease" testid="compare-panel">
            {cs.top_diagnoses.length === 0 ? <p className="text-on-surface-variant">Insufficient evidence to rank diseases.</p> : (
              <div className="flex flex-wrap gap-1.5 mb-2">{cs.top_diagnoses.map((d) => (
                <button key={d.disease_id} onClick={() => compare(d.disease_id)} className="px-2 py-1 rounded border border-primary/30 text-primary">{d.disease_name}</button>))}</div>)}
            {cmp && (
              <div data-testid="compare-result" className="space-y-1">
                <div className="font-semibold">{cmp.disease_name}{cmp.score ? ` — probability ${cmp.score.probability}, similarity ${cmp.score.phenotype_similarity}` : ''}</div>
                {cmp.score_note && <div className="text-on-surface-variant">{cmp.score_note}</div>}
                <div><b>Matched:</b> {cmp.matched.map((m) => `${m.patient_term_name} → ${m.disease_term_name} (${m.weight_pct}%)`).join('; ') || 'none'}</div>
                <div><b>Explicitly absent:</b> {cmp.explicitly_absent.map((a) => a.name).join(', ') || 'none'}</div>
                <div><b>Not documented:</b> {cmp.not_documented.map((a) => a.name).join(', ') || 'none'}</div>
                <div><b>Genes / case variants:</b> {cmp.genes.join(', ') || '—'} / {cmp.case_variants.length ? cmp.case_variants.map((v) => `${v.gene_symbol} ${v.hgvs || ''}`).join('; ') : cmp.variant_note}</div>
              </div>)}
          </Panel>
        </div>
      )}
      {cs && cs.observed.length > 0 && onNavigateToDiagnosis && (
        <button onClick={() => onNavigateToDiagnosis()} className="inline-flex items-center gap-1.5 text-xs font-semibold text-primary">Open diagnosis <ArrowRight size={13} /></button>
      )}
    </div>
  )
}
