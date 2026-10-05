import React, { useRef, useState, useMemo } from 'react'
import { ScanText, Upload, Loader2, Eraser } from 'lucide-react'
import { api, setNavContext } from '../api.js'

const LABEL_STYLE = {
  PHENOTYPE: 'bg-sky-100 text-sky-900 border-sky-300',
  DISEASE: 'bg-indigo-100 text-indigo-900 border-indigo-300',
  GENE: 'bg-emerald-100 text-emerald-900 border-emerald-300',
  VARIANT: 'bg-amber-100 text-amber-900 border-amber-300',
  DRUG: 'bg-teal-100 text-teal-900 border-teal-300',
  LAB: 'bg-slate-100 text-slate-900 border-slate-300',
  FAMILY_RELATION: 'bg-violet-100 text-violet-900 border-violet-300',
  AGE: 'bg-gray-100 text-gray-800 border-gray-300',
  ONSET: 'bg-gray-100 text-gray-800 border-gray-300',
  SEVERITY: 'bg-orange-100 text-orange-900 border-orange-300',
}
const ASSERT_STYLE = {
  absent: 'line-through decoration-red-500',
  possible: 'border-dashed',
  historical: 'italic',
}

/** Renders the text with each entity as a highlighted span. Overlapping spans of different labels are shown once (first wins). */
export function highlight(text, entities, selectedId, onSelect) {
  const ordered = [...entities].sort((a, b) => a.start - b.start || b.end - b.start - (a.end - a.start))
  const out = []
  let pos = 0
  for (const e of ordered) {
    if (e.start < pos) continue
    if (e.start > pos) out.push(text.slice(pos, e.start))
    out.push(
      <mark key={e.id} data-testid="nlp-span" data-label={e.label} data-assertion={e.assertion || ''} onClick={() => onSelect(e.id)}
        className={`cursor-pointer rounded px-1 border ${LABEL_STYLE[e.label] || ''} ${ASSERT_STYLE[e.assertion] || ''} ${selectedId === e.id ? 'ring-2 ring-primary' : ''}`}
        title={`${e.label}${e.assertion ? ' · ' + e.assertion : ''}`}>
        {text.slice(e.start, e.end)}<sup className="ml-0.5 text-[9px] font-bold opacity-70">{e.label.replace('_', ' ')}</sup>
      </mark>,
    )
    pos = e.end
  }
  if (pos < text.length) out.push(text.slice(pos))
  return out
}

function Flags({ e }) {
  const f = []
  if (e.assertion === 'absent') f.push(['Negated', 'bg-red-50 text-red-800'])
  if (e.ruled_out) f.push(['Ruled out', 'bg-red-50 text-red-800'])
  if (e.assertion === 'possible') f.push(['Uncertain', 'bg-amber-50 text-amber-800'])
  if (e.assertion === 'historical') f.push(['History of', 'bg-surface-container text-on-surface'])
  if (e.experiencer === 'family') f.push([`Family: ${e.family_relation}`, 'bg-violet-50 text-violet-800'])
  return f.map(([t, c]) => <span key={t} className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${c}`}>{t}</span>)
}

const SAMPLE = 'Patient is a 12 year old girl with tremor and jaundice since 6 months. No fever, seizures or tremor. Mother has Wilson disease. ATP7B c.3207C>A found. Hb: 9.2. Wilson disease ruled out in brother.'

export default function ClinicalTextView({ onNavigate }) {
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [res, setRes] = useState(null)
  const [sel, setSel] = useState(null)
  const [filter, setFilter] = useState('ALL')
  const fileRef = useRef(null)

  const analyze = async () => {
    setBusy(true); setError(null); setSel(null)
    try { setRes(await api.nlpAnalyze({ text })) } catch (e) { setRes(null); setError(e.message) } finally { setBusy(false) }
  }
  const onFile = (ev) => {
    const f = ev.target.files?.[0]
    if (!f) return
    if (f.size > 100000) { setError('File too large (max 100 KB of text)'); return }
    const rd = new FileReader()
    rd.onload = () => setText(String(rd.result).slice(0, 20000))
    rd.readAsText(f)
  }
  const labels = useMemo(() => ['ALL', ...Object.keys(res?.counts || {})], [res])
  const shown = (res?.entities || []).filter((e) => filter === 'ALL' || e.label === filter)
  const selected = res?.entities.find((e) => e.id === sel)
  const sm = res?.summary

  const importToPhenotypes = () => {
    setNavContext('phenotypes', { nlp_import: { text, present: sm.present_phenotypes, absent: sm.absent_phenotypes, possible: sm.possible_phenotypes, conflicts: sm.conflicts } })
    onNavigate?.('phenotypes')
  }

  return (
    <div className="space-y-5" data-testid="clinical-text-view">
      <div>
        <h1 className="text-xl font-bold text-on-surface flex items-center gap-2"><ScanText size={20} className="text-primary" /> Clinical Text Intelligence</h1>
        <p className="text-xs text-on-surface-variant mt-1">Extracts phenotypes, diseases, genes, variants, drugs, labs and family context from a note. Rule-based assertion detection and the existing HPO mapper; automated extraction for clinician review. Nothing is saved to a case.</p>
      </div>

      <div className="panel p-4 space-y-3">
        <textarea aria-label="Clinical note" value={text} onChange={(e) => setText(e.target.value)} rows={6} maxLength={20000}
          placeholder="Paste a clinical note (English, Hindi or code-mixed)…" className="w-full text-sm rounded-lg border border-outline-variant p-3 font-sans" />
        <div className="flex flex-wrap gap-2 items-center">
          <button onClick={analyze} disabled={busy || !text.trim()} className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-primary text-white text-sm font-semibold disabled:opacity-60">
            {busy ? <Loader2 size={14} className="animate-spin" /> : <ScanText size={14} />}{busy ? 'Analysing…' : 'Analyse text'}</button>
          <button onClick={() => fileRef.current?.click()} className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border border-primary/30 text-primary text-xs font-semibold"><Upload size={13} />Upload .txt</button>
          <input ref={fileRef} type="file" accept=".txt,text/plain" onChange={onFile} className="hidden" aria-label="Upload text file" />
          <button onClick={() => setText(SAMPLE)} className="text-xs text-primary font-semibold">Use synthetic example</button>
          <button onClick={() => { setText(''); setRes(null); setError(null) }} className="inline-flex items-center gap-1 text-xs text-on-surface-variant"><Eraser size={12} />Clear</button>
          <span className="ml-auto text-[11px] text-outline">{text.length}/20000</span>
        </div>
      </div>

      {error && <div role="alert" className="rounded-lg border border-red-200 bg-red-50 text-red-800 text-xs px-3 py-2">{error}</div>}

      {res && (
        <>
          <div className="panel p-4" data-testid="nlp-highlighted">
            <div className="flex flex-wrap gap-1.5 mb-3">
              {labels.map((l) => (
                <button key={l} onClick={() => setFilter(l)} className={`px-2.5 py-1 rounded-full text-[11px] font-semibold border ${filter === l ? 'bg-primary text-white border-primary' : 'border-outline-variant text-on-surface-variant'}`}>
                  {l === 'ALL' ? 'All' : l.replace('_', ' ')}{l !== 'ALL' ? ` (${res.counts[l]})` : ''}</button>
              ))}
            </div>
            <p className="text-sm leading-8 whitespace-pre-wrap">{highlight(res.text, filter === 'ALL' ? res.entities : shown, sel, setSel)}</p>
            {res.entities.length === 0 && <p className="text-xs text-on-surface-variant">No clinical entities were recognised in this text.</p>}
            <p className="text-[11px] text-outline mt-3">Struck-through = negated · dashed = uncertain · italic = history of. {res.disclaimer}</p>
          </div>

          <div className="grid lg:grid-cols-[1fr_340px] gap-4">
            <div className="panel p-4 overflow-x-auto">
              <table className="w-full text-xs" data-testid="nlp-table">
                <thead><tr className="text-left text-on-surface-variant"><th className="py-1 pr-2">Text</th><th className="pr-2">Type</th><th className="pr-2">Normalised concept</th><th className="pr-2">Context</th></tr></thead>
                <tbody>
                  {shown.map((e) => (
                    <tr key={e.id} onClick={() => setSel(e.id)} className={`border-t border-outline-variant/30 cursor-pointer ${sel === e.id ? 'bg-primary/5' : ''}`}>
                      <td className="py-1.5 pr-2 font-semibold">{e.text}</td>
                      <td className="pr-2">{e.label.replace('_', ' ')}</td>
                      <td className="pr-2">
                        {e.normalized?.id ? <span><span className="font-mono">{e.normalized.id}</span> {e.normalized.name !== e.normalized.id ? e.normalized.name : ''}
                          {e.normalized.status === 'needs_review' && <span className="ml-1 text-amber-700 font-semibold">needs review</span>}</span>
                          : (e.normalized ? <span className="text-outline">Not mapped</span> : <span className="text-outline">—</span>)}
                      </td>
                      <td className="space-x-1"><Flags e={e} />{e.severity && <span className="text-[10px] px-1.5 py-0.5 rounded bg-orange-50 text-orange-800 font-semibold">{e.severity}</span>}
                        {e.onset && <span className="text-[10px] text-on-surface-variant">onset {e.onset.term || `${e.onset.amount} ${e.onset.unit}`}</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="space-y-3">
              {selected && (
                <div className="panel p-3 text-xs space-y-1" data-testid="nlp-detail">
                  <div className="font-bold">{selected.text} <span className="text-outline font-normal">{selected.label}</span></div>
                  <div>Source: {selected.source} · confidence {selected.confidence}</div>
                  {selected.normalized?.id && <div>{selected.normalized.system}: {selected.normalized.id} via {selected.normalized.method} ({selected.normalized.confidence})</div>}
                  {selected.value?.gene_link && <div>Gene link: {selected.value.gene ? `${selected.value.gene} — ` : ''}{selected.value.gene_link}</div>}
                  <div className="space-x-1"><Flags e={selected} /></div>
                </div>
              )}
              <div className="panel p-3 text-xs space-y-2" data-testid="nlp-summary">
                <div className="font-bold text-sm">Findings summary</div>
                <div><b>Present:</b> {sm.present_phenotypes.map((p) => `${p.name} (${p.hpo_id})`).join('; ') || 'none extracted'}</div>
                <div><b>Absent (negated):</b> {sm.absent_phenotypes.map((p) => `${p.name} (${p.hpo_id})`).join('; ') || 'none extracted'}</div>
                <div><b>Uncertain:</b> {sm.possible_phenotypes.map((p) => `${p.name} (${p.hpo_id})`).join('; ') || 'none extracted'}</div>
                {sm.family_findings.length > 0 && <div><b>Family:</b> {sm.family_findings.map((f) => `${f.relation}: ${f.concept_name || f.text} [${f.assertion}]`).join('; ')}</div>}
                {sm.conflicts.length > 0 && <div role="alert" className="text-amber-800 bg-amber-50 rounded px-2 py-1">Conflict: {sm.conflicts.map((c) => c.name).join(', ')} documented as both present and absent.</div>}
                {sm.unmapped_phenotypes.length > 0 && <div className="text-on-surface-variant">Not mapped to HPO: {sm.unmapped_phenotypes.join(', ')}</div>}
                <div className="text-[11px] text-outline">Not extracted: {Object.keys(res.engine.unsupported_labels).join(', ')} ({'no lexicon or model configured'}).</div>
                <button onClick={importToPhenotypes} disabled={!sm.present_phenotypes.length && !sm.absent_phenotypes.length} className="w-full mt-1 px-3 py-2 rounded-lg bg-primary text-white font-semibold disabled:opacity-50">Review in Phenotypes</button>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
