import React, { useEffect, useState } from 'react'
import { api, setNavContext } from '../api.js'

const SAFETY = 'Pharmacogenomic decision support. Clinical prescribing decisions require qualified clinician review.'

export default function PgxCasePanel({ onNavigate }) {
  const [patients, setPatients] = useState([])
  const [pid, setPid] = useState('')
  const [ws, setWs] = useState(null)
  const [drug, setDrug] = useState('')
  const [lookup, setLookup] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => { api.listPatients().then((p) => setPatients(Array.isArray(p) ? p : p?.patients || [])).catch(() => {}) }, [])

  const load = async (id) => {
    setPid(id); setWs(null); setLookup(null); setError(null)
    if (!id) return
    setBusy(true)
    try { setWs(await api.pgxCase(id)) } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  const search = async () => {
    setError(null)
    try { setLookup(await api.pgxCaseDrug(pid, drug)) } catch (e) { setError(e.message) }
  }
  const askAi = (prompt) => { setNavContext('ai-assistant', { prompt, patient_id: pid, include_pgx: true }); onNavigate?.('ai-assistant') }

  return (
    <section className="panel p-4 space-y-3" data-testid="pgx-case">
      <div>
        <h3 className="text-base font-bold text-on-surface">Case pharmacogenomics</h3>
        <p className="text-xs text-on-surface-variant">{SAFETY} Genotypes come only from the case's variant analysis; no allele is inferred.</p>
      </div>
      {error && <div role="alert" className="rounded-lg border border-red-200 bg-red-50 text-red-800 text-xs px-3 py-2">{error}</div>}
      <label className="text-xs font-semibold block">Case
        <select aria-label="PGx case" value={pid} onChange={(e) => load(e.target.value)} className="mt-1 block w-full max-w-sm rounded-lg border border-outline-variant p-2 text-sm font-normal">
          <option value="">No case selected</option>
          {patients.map((p) => <option key={p.patient_id} value={p.patient_id}>{p.patient_id}{p.name ? ` — ${p.name}` : ''}</option>)}
        </select>
      </label>
      {busy && <p className="text-xs text-on-surface-variant">Loading pharmacogenomic findings…</p>}
      {ws && !ws.available && <p data-testid="pgx-case-empty" className="text-xs text-on-surface-variant">{ws.note}</p>}
      {ws?.available && (
        <>
          <div className="overflow-x-auto" data-testid="pgx-genotypes">
            <table className="w-full text-xs"><thead><tr className="text-left text-on-surface-variant"><th>Gene</th><th>Alleles</th><th>Diplotype</th><th>Predicted phenotype</th><th>Indian population context</th></tr></thead>
              <tbody>{ws.genes.map((g) => (
                <tr key={g.gene} className="border-t border-outline-variant/30 align-top">
                  <td className="py-1 font-semibold">{g.gene}</td>
                  <td>{g.alleles.map((a) => `${a.allele} (${a.zygosity}, ${a.function})`).join('; ')}</td>
                  <td>{g.diplotype || 'Not determined'}{g.diplotype_note && <div className="text-outline">{g.diplotype_note}</div>}</td>
                  <td>{g.phenotype || 'Not assigned'}{g.phenotype_note && <div className="text-outline">{g.phenotype_note}</div>}</td>
                  <td>{g.population ? <>
                    <div>Allele frequency {g.population.allele_frequency} ({g.population.match}; n={g.population.n_samples})</div>
                    <div className="text-outline">Expected HWE: {Object.entries(g.population.hwe_expected).map(([k, v]) => `${k} ${v}`).join(', ')}</div>
                    <div className="text-outline">{g.population.note}</div></> : 'No matching record'}</td>
                </tr>))}</tbody></table>
          </div>
          <div className="overflow-x-auto" data-testid="pgx-matrix">
            <table className="w-full text-xs"><thead><tr className="text-left text-on-surface-variant"><th>Drug</th><th>Gene</th><th>Genotype</th><th>Phenotype</th><th>Risk</th><th>Recommendation</th><th>Alternatives</th><th>Evidence</th></tr></thead>
              <tbody>{ws.matrix.map((r) => (
                <tr key={`${r.drug}-${r.gene}`} className="border-t border-outline-variant/30 align-top">
                  <td className="py-1 font-semibold">{r.drug}</td><td>{r.gene}</td><td>{r.genotype}</td><td>{r.phenotype || 'Not assigned'}</td><td>{r.risk}</td>
                  <td>{r.recommendation || r.status}</td>
                  <td>{r.alternatives.length ? <>{r.alternatives.join(', ')}<div className="text-outline">Source: {r.alternatives_source}</div></> : 'None listed'}</td>
                  <td>{r.evidence_level}<div className="text-outline">{r.sources.join('; ')}</div>
                    {r.saved_evidence.map((e) => <div key={e.identifier}>Saved: {e.title}</div>)}</td>
                </tr>))}</tbody></table>
          </div>
        </>
      )}
      {pid && (
        <div className="flex flex-wrap gap-2 items-center">
          <input aria-label="Drug name" value={drug} onChange={(e) => setDrug(e.target.value)} placeholder="Look up a drug" className="rounded-lg border border-outline-variant p-2 text-xs" />
          <button onClick={search} disabled={drug.trim().length < 2} className="px-3 py-1.5 rounded-lg border border-primary/30 text-primary text-xs font-semibold">Check drug for this case</button>
          <button onClick={() => askAi('What does this patient\'s pharmacogenomic result mean?')} className="px-3 py-1.5 rounded-lg border border-primary/30 text-primary text-xs font-semibold">Ask AI Assistant</button>
          <button onClick={() => onNavigate?.('evidence')} className="px-3 py-1.5 rounded-lg border border-primary/30 text-primary text-xs font-semibold">Evidence</button>
        </div>
      )}
      {lookup && (
        <div data-testid="pgx-lookup" className="text-xs space-y-1">
          {!lookup.supported ? <p>{lookup.note}</p> : (<>
            {lookup.rows.map((r) => <div key={r.gene}><b>{r.gene}</b>: {r.recommendation || r.status}</div>)}
            {lookup.genes_without_genotype.map((m) => <div key={m.gene}><b>{m.gene}</b>: {m.genotype}</div>)}
          </>)}
        </div>
      )}
    </section>
  )
}
