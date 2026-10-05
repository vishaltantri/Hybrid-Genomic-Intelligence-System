import React, { useEffect, useState, useCallback } from 'react'
import { BookOpen, Search, ExternalLink, ChevronDown, ChevronUp, Bookmark, FileText, Trash2, Loader2 } from 'lucide-react'
import { api, consumeNavContext } from '../api.js'

const KINDS = [['auto', 'Auto-detect'], ['gene', 'Gene'], ['variant', 'Variant'], ['hgvs', 'HGVS'], ['disease', 'Disease'], ['phenotype', 'Phenotype'], ['pmid', 'PMID']]
const TYPES = ['', 'Meta-analysis', 'Systematic review', 'Randomized controlled trial', 'Clinical trial', 'Practice guideline', 'Observational study', 'Case report', 'Review']

function SourceStrip({ sources }) {
  if (!sources) return null
  const list = Array.isArray(sources) ? sources : sources.sources || []
  return (
    <div className="flex flex-wrap gap-2" data-testid="evidence-sources">
      {list.map((s) => (
        <span key={s.source} className={`text-[11px] px-2.5 py-1 rounded-full border ${s.status === 'configured' || s.status === 'local seed' ? 'border-primary/30 bg-primary/5 text-primary' : 'border-outline-variant bg-surface-container text-on-surface-variant'}`}
          title={s.detail || ''}>{s.source}: {s.status}</span>
      ))}
    </div>
  )
}

function Card({ r, caseId, onSave, saved, variantId }) {
  const [open, setOpen] = useState(false)
  const isPub = r.source === 'PubMed'
  return (
    <article className="panel p-4 space-y-2" data-testid="evidence-card">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-sm font-bold text-on-surface leading-snug">
            {r.url ? <a href={r.url} target="_blank" rel="noopener noreferrer" className="hover:underline text-primary">{r.title || r.source_id}</a> : (r.title || r.source_id)}
          </h3>
          <p className="text-[11px] text-on-surface-variant mt-0.5">
            {[(r.authors || []).slice(0, 4).join(', ') + ((r.authors || []).length > 4 ? ' et al.' : ''), r.journal, r.publication_date].filter(Boolean).join(' · ')}
          </p>
        </div>
        {r.relevance != null && (
          <div className="text-right shrink-0" title={r.relevance_note}>
            <div className="text-xs font-bold text-primary">{Math.round(r.relevance * 100)}%</div>
            <div className="text-[10px] text-outline">relevance</div>
          </div>
        )}
      </div>
      <div className="flex flex-wrap gap-1.5 text-[10px]">
        <span className="px-2 py-0.5 rounded bg-surface-container font-semibold">{r.source}</span>
        {r.pmid && <span className="px-2 py-0.5 rounded bg-surface-container font-mono">PMID {r.pmid}</span>}
        {r.doi && <a className="px-2 py-0.5 rounded bg-surface-container font-mono hover:underline" href={`https://doi.org/${r.doi}`} target="_blank" rel="noopener noreferrer">DOI {r.doi}</a>}
        <span className="px-2 py-0.5 rounded bg-primary/10 text-primary">{r.evidence_type || 'Study design not classified'}</span>
        {(r.mentions?.genes || []).map((g) => <span key={g} className="px-2 py-0.5 rounded bg-emerald-50 text-emerald-800">{g}</span>)}
        {(r.mentions?.hgvs_c || []).concat(r.mentions?.hgvs_p || []).slice(0, 4).map((h) => <span key={h} className="px-2 py-0.5 rounded bg-amber-50 text-amber-800 font-mono">{h}</span>)}
        {(r.linked_variants || []).map((l) => <span key={l.variant_id} className="px-2 py-0.5 rounded bg-primary text-white" title={(l.basis || []).join('; ')}>Linked to case variant {l.gene}</span>)}
      </div>
      {r.summary && <p className={`text-xs text-on-surface-variant ${open ? '' : 'line-clamp-2'}`}>{r.summary}</p>}
      {open && (
        <dl className="text-[11px] grid grid-cols-[110px_1fr] gap-x-3 gap-y-1 bg-surface-container-low rounded-lg p-3" data-testid="evidence-provenance">
          <dt className="font-semibold">Provenance</dt><dd>{r.provenance?.database}</dd>
          {r.provenance?.query && (<><dt className="font-semibold">Query</dt><dd className="font-mono">{r.provenance.query}</dd></>)}
          <dt className="font-semibold">Retrieved</dt><dd>{r.retrieved_at}</dd>
          {r.provenance?.strength_basis && (<><dt className="font-semibold">Design basis</dt><dd>{r.provenance.strength_basis}</dd></>)}
          {(r.provenance?.mesh_terms || []).length > 0 && (<><dt className="font-semibold">MeSH</dt><dd>{r.provenance.mesh_terms.join(', ')}</dd></>)}
          {r.relevance_note && (<><dt className="font-semibold">Relevance</dt><dd>{r.relevance_note}</dd></>)}
        </dl>
      )}
      <div className="flex flex-wrap gap-2 pt-1">
        <button onClick={() => setOpen(!open)} className="inline-flex items-center gap-1 text-[11px] text-primary font-semibold">{open ? <ChevronUp size={13} /> : <ChevronDown size={13} />}{open ? 'Hide details' : 'Abstract & provenance'}</button>
        <span className="flex-1" />
        <button disabled={!caseId || saved} onClick={() => onSave(r, false, variantId)} className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg border border-primary/30 text-primary text-[11px] font-semibold disabled:opacity-50"><Bookmark size={12} />{saved ? 'Saved to case' : 'Save to case'}</button>
        <button disabled={!caseId} onClick={() => onSave(r, true, variantId)} className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-primary text-white text-[11px] font-semibold disabled:opacity-50"><FileText size={12} />Add to report</button>
      </div>
      {isPub && !r.summary && <p className="text-[11px] text-outline">No abstract available from PubMed for this record.</p>}
    </article>
  )
}

export default function EvidenceView() {
  const [sources, setSources] = useState(null)
  const [patients, setPatients] = useState([])
  const [caseId, setCaseId] = useState('')
  const [q, setQ] = useState('')
  const [kind, setKind] = useState('auto')
  const [yearFrom, setYearFrom] = useState('')
  const [yearTo, setYearTo] = useState('')
  const [etype, setEtype] = useState('')
  const [page, setPage] = useState(1)
  const [state, setState] = useState({ phase: 'idle' })
  const [variantCtx, setVariantCtx] = useState(null)
  const [structured, setStructured] = useState([])
  const [saved, setSaved] = useState([])
  const [notice, setNotice] = useState(null)

  const loadSaved = useCallback((cid) => {
    if (!cid) { setSaved([]); return }
    api.evidenceCase(cid).then((r) => setSaved(r.items || [])).catch((e) => setNotice(e.message))
  }, [])

  const run = useCallback(async (opts = {}) => {
    const p = opts.page || 1
    setState({ phase: 'loading' })
    try {
      if (opts.variant) {
        const r = await api.evidenceVariant(opts.variant.analysis_id, opts.variant.variant_id, p)
        setStructured(r.structured || [])
        setVariantCtx(r.variant)
        setState({ phase: r.literature.status, res: r.literature, note: r.literature.note, searchedWith: r.searched_with })
      } else {
        setStructured([])
        const res = await api.evidenceSearch({ q: opts.q ?? q, kind, page: p, size: 10, year_from: yearFrom, year_to: yearTo, evidence_type: etype, analysis_id: variantCtx ? opts.analysis : '' })
        setState({ phase: res.status, res })
      }
      setPage(p)
    } catch (e) {
      setState({ phase: 'error', message: e.message })
    }
  }, [q, kind, yearFrom, yearTo, etype, variantCtx])

  useEffect(() => {
    api.evidenceSources().then(setSources).catch(() => setSources(null))
    const ctx = consumeNavContext('evidence')
    api.listPatients().then((l) => {
      setPatients(l || [])
      if (ctx?.patient_id) { setCaseId(ctx.patient_id); loadSaved(ctx.patient_id) }
    }).catch(() => {})
    if (ctx?.analysis_id && ctx?.variant_id) {
      setVariantCtx({ gene: ctx.gene, hgvs: ctx.hgvs, ...ctx })
      run({ variant: ctx })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const save = async (rec, inReport, variantId) => {
    try {
      await api.evidenceSave(caseId, { record: rec, variant_id: variantId || variantCtx?.variant_id || null, in_report: inReport })
      setNotice(inReport ? 'Saved to case and added to the report section.' : 'Saved to case.')
      loadSaved(caseId)
    } catch (e) { setNotice(e.message) }
  }
  const isSaved = (r) => saved.some((s) => s.source === r.source && s.source_id === (r.source_id || r.pmid))
  const submit = (e) => { e?.preventDefault(); if (q.trim()) { setVariantCtx(null); run({ q: q.trim() }) } }
  const res = state.res
  const total = res?.total || 0
  const pages = Math.max(1, Math.ceil(total / (res?.size || 10)))

  return (
    <div className="space-y-5" data-testid="evidence-view">
      <div>
        <h1 className="text-xl font-bold text-on-surface flex items-center gap-2"><BookOpen size={20} className="text-primary" /> Evidence &amp; Literature</h1>
        <p className="text-xs text-on-surface-variant mt-1">Live PubMed search through the NCBI E-utilities, plus the ClinVar and Orphanet records already in Genomera. Relevance ranks matches to your query; it is not a measure of certainty. Clinical Decision Support — clinician review required.</p>
      </div>
      <SourceStrip sources={sources} />

      <form onSubmit={submit} className="panel p-4 space-y-3">
        <div className="flex flex-wrap gap-2">
          <input aria-label="Search literature" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Gene, variant (c.3207C>A), disease, phenotype or PMID"
            className="flex-1 min-w-[240px] text-sm rounded-lg border border-outline-variant px-3 py-2" maxLength={200} />
          <button type="submit" disabled={!q.trim() || state.phase === 'loading'} className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-primary text-white text-sm font-semibold disabled:opacity-60"><Search size={14} />Search</button>
        </div>
        <div className="flex flex-wrap gap-2 text-xs">
          <label className="flex items-center gap-1">Type <select aria-label="Query type" value={kind} onChange={(e) => setKind(e.target.value)} className="rounded border border-outline-variant px-2 py-1">{KINDS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></label>
          <label className="flex items-center gap-1">From <input aria-label="Year from" type="number" min="1900" max="2100" value={yearFrom} onChange={(e) => setYearFrom(e.target.value)} className="w-20 rounded border border-outline-variant px-2 py-1" /></label>
          <label className="flex items-center gap-1">To <input aria-label="Year to" type="number" min="1900" max="2100" value={yearTo} onChange={(e) => setYearTo(e.target.value)} className="w-20 rounded border border-outline-variant px-2 py-1" /></label>
          <label className="flex items-center gap-1">Design <select aria-label="Evidence type" value={etype} onChange={(e) => setEtype(e.target.value)} className="rounded border border-outline-variant px-2 py-1">{TYPES.map((t) => <option key={t} value={t}>{t || 'Any'}</option>)}</select></label>
          <label className="flex items-center gap-1 ml-auto">Case <select aria-label="Case" value={caseId} onChange={(e) => { setCaseId(e.target.value); loadSaved(e.target.value) }} className="rounded border border-outline-variant px-2 py-1">
            <option value="">No case selected</option>{patients.map((p) => <option key={p.patient_id} value={p.patient_id}>{p.patient_id}</option>)}</select></label>
        </div>
      </form>

      {notice && <div role="status" className="text-xs rounded-lg bg-primary/5 border border-primary/20 px-3 py-2">{notice}</div>}

      {variantCtx?.variant_id && (
        <div className="panel p-3 text-xs" data-testid="variant-context">
          <b>Variant context:</b> {variantCtx.gene} {variantCtx.hgvs || variantCtx.cdna} {variantCtx.clinical_significance ? `· ClinVar: ${variantCtx.clinical_significance}` : ''}
          {state.searchedWith && <span className="text-on-surface-variant"> · literature searched with {state.searchedWith}</span>}
        </div>
      )}

      {structured.map((r) => <Card key={r.source + r.source_id} r={r} caseId={caseId} onSave={save} saved={isSaved(r)} variantId={variantCtx?.variant_id} />)}

      {state.phase === 'idle' && <div className="panel p-6 text-center text-xs text-on-surface-variant">Search PubMed to see results. Nothing is shown until a query is run.</div>}
      {state.phase === 'loading' && <div className="panel p-6 text-center text-xs flex items-center justify-center gap-2"><Loader2 size={14} className="animate-spin" /> Querying PubMed…</div>}
      {state.phase === 'unavailable' && <div role="alert" className="rounded-lg border border-amber-200 bg-amber-50 text-amber-900 text-xs px-3 py-2">Literature unavailable: {res?.message || 'PubMed could not be reached.'} No results are shown rather than guessed ones.</div>}
      {state.phase === 'error' && <div role="alert" className="rounded-lg border border-red-200 bg-red-50 text-red-800 text-xs px-3 py-2">{state.message}</div>}
      {state.phase === 'no_results' && <div className="panel p-6 text-center text-xs text-on-surface-variant">No matching publications found{res?.query_translation ? ` for ${res.query_translation}` : ''}.</div>}
      {state.note && <p className="text-[11px] text-on-surface-variant">{state.note}</p>}

      {state.phase === 'ok' && (
        <div className="space-y-3">
          <div className="text-[11px] text-on-surface-variant">{total} matching publications · retrieved {res.retrieved_at}</div>
          {res.results.map((r) => <Card key={r.pmid} r={r} caseId={caseId} onSave={save} saved={isSaved(r)} variantId={variantCtx?.variant_id} />)}
          {pages > 1 && (
            <div className="flex items-center justify-center gap-3 text-xs">
              <button disabled={page <= 1} onClick={() => run(variantCtx?.analysis_id ? { variant: variantCtx, page: page - 1 } : { q, page: page - 1 })} className="px-3 py-1 rounded border border-outline-variant disabled:opacity-50">Previous</button>
              <span>Page {page} of {pages}</span>
              <button disabled={page >= pages} onClick={() => run(variantCtx?.analysis_id ? { variant: variantCtx, page: page + 1 } : { q, page: page + 1 })} className="px-3 py-1 rounded border border-outline-variant disabled:opacity-50">Next</button>
            </div>
          )}
        </div>
      )}

      {caseId && (
        <section className="panel p-4 space-y-2" data-testid="saved-evidence">
          <h2 className="text-sm font-bold">Saved evidence for {caseId}</h2>
          {saved.length === 0 && <p className="text-xs text-on-surface-variant">No evidence saved to this case yet.</p>}
          {saved.map((s) => (
            <div key={s.evidence_id} className="flex items-start gap-2 text-xs border-t border-outline-variant/30 pt-2">
              <div className="flex-1 min-w-0">
                <div className="font-semibold">{s.payload?.title || s.source_id}</div>
                <div className="text-[11px] text-on-surface-variant">{s.source} {s.payload?.pmid ? `· PMID ${s.record.pmid}` : ''} {s.variant_id ? `· variant ${s.variant_id}` : ''}</div>
              </div>
              <label className="flex items-center gap-1 text-[11px]"><input type="checkbox" checked={!!s.in_report} onChange={(e) => api.evidencePatch(caseId, s.evidence_id, { in_report: e.target.checked }).then(() => loadSaved(caseId))} />In report</label>
              <button aria-label="Remove saved evidence" onClick={() => api.evidenceDelete(caseId, s.evidence_id).then(() => loadSaved(caseId))} className="text-red-700"><Trash2 size={13} /></button>
            </div>
          ))}
        </section>
      )}
    </div>
  )
}
