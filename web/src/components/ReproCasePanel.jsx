import React, { useEffect, useState } from 'react'
import { api, setNavContext } from '../api.js'

const SAFETY = 'Calculated genetic probability, not a clinical outcome prediction.'
const STATUSES = [['carrier', 'Carrier'], ['not_carrier', 'Not a carrier'], ['affected', 'Affected'], ['unknown', 'Unknown']]
const pct = (x) => (x == null ? 'Not available' : `${(x * 100).toFixed(2)}%`)

function Punnett({ p }) {
  if (!p || !p.cells) return null
  return (
    <table data-testid="repro-punnett" className="text-xs border border-outline-variant/40">
      <caption className="text-left text-on-surface-variant pb-1">Punnett square ({p.parent_a} x {p.parent_b})</caption>
      <tbody>
        <tr><th />{p.gametes_b.map((g, i) => <th key={i} className="px-3">{g}</th>)}</tr>
        {p.cells.map((row, i) => (
          <tr key={i}><th className="px-3">{p.gametes_a[i]}</th>{row.map((c, j) => <td key={j} className="border border-outline-variant/40 px-3 py-1 text-center">{c.genotype}</td>)}</tr>
        ))}
      </tbody>
    </table>
  )
}

export default function ReproCasePanel({ onNavigate }) {
  const [patients, setPatients] = useState([])
  const [pid, setPid] = useState('')
  const [members, setMembers] = useState(null)
  const [couple, setCouple] = useState({ a: '', b: '' })
  const [res, setRes] = useState(null)
  const [sel, setSel] = useState('')
  const [explain, setExplain] = useState(null)
  const [mc, setMc] = useState(null)
  const [mcIn, setMcIn] = useState({ n: 20000, seed: 5 })
  const [scn, setScn] = useState({ a: 'carrier', b: 'not_carrier' })
  const [scenario, setScenario] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => { api.listPatients().then((p) => setPatients(Array.isArray(p) ? p : p?.patients || [])).catch(() => {}) }, [])

  const run = async (id, a, b) => {
    setRes(null); setExplain(null); setMc(null); setScenario(null); setError(null); setBusy(true)
    try {
      const r = await api.reproCase(id, a, b)
      setRes(r)
      setSel(r.risks?.find((x) => x.supported)?.disease_id || r.risks?.[0]?.disease_id || '')
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  const pick = async (id) => {
    setPid(id); setMembers(null); setRes(null); setError(null)
    if (!id) return
    try {
      const m = await api.reproMembers(id)
      setMembers(m)
      const d = m.default_couple
      setCouple({ a: d?.partner_a || '', b: d?.partner_b || '' })
      if (d) await run(id, d.partner_a, d.partner_b)
    } catch (e) { setError(e.message) }
  }
  const guard = async (fn) => { setError(null); try { await fn() } catch (e) { setError(e.message) } }
  const row = res?.risks?.find((r) => r.disease_id === sel)
  const askAi = () => {
    setNavContext('ai-assistant', { prompt: 'Explain this couple reproductive risk in plain language.', patient_id: pid, include_repro: true })
    onNavigate?.('ai-assistant')
  }

  return (
    <section className="panel p-4 space-y-3" data-testid="repro-case">
      <div>
        <h3 className="text-base font-bold text-on-surface">Case reproductive genetics</h3>
        <p className="text-xs text-on-surface-variant">{SAFETY} Genotypes come from the case pedigree; unrecorded genotypes are treated as unknown, never as normal.</p>
      </div>
      {error && <div role="alert" className="rounded-lg border border-red-200 bg-red-50 text-red-800 text-xs px-3 py-2">{error}</div>}
      <label className="text-xs font-semibold block">Case
        <select aria-label="Repro case" value={pid} onChange={(e) => pick(e.target.value)} className="mt-1 block w-full max-w-sm rounded-lg border border-outline-variant p-2 text-sm font-normal">
          <option value="">No case selected</option>
          {patients.map((p) => <option key={p.patient_id} value={p.patient_id}>{p.patient_id}{p.name ? ` — ${p.name}` : ''}</option>)}
        </select>
      </label>
      {members && members.members.length === 0 && <p data-testid="repro-nomembers" className="text-xs text-on-surface-variant">{members.note}</p>}
      {members && members.members.length > 0 && (
        <div className="flex flex-wrap gap-2 items-end text-xs">
          {['a', 'b'].map((k) => (
            <label key={k} className="font-semibold">Partner {k.toUpperCase()}
              <select aria-label={`Partner ${k.toUpperCase()}`} value={couple[k]} onChange={(e) => setCouple({ ...couple, [k]: e.target.value })} className="mt-1 block rounded-lg border border-outline-variant p-2 font-normal">
                <option value="">Select member</option>
                {members.members.map((m) => <option key={m.member_id} value={m.member_id}>{m.label} ({m.sex})</option>)}
              </select>
            </label>
          ))}
          <button onClick={() => run(pid, couple.a, couple.b)} disabled={!couple.a || !couple.b || couple.a === couple.b} className="px-3 py-2 rounded-lg bg-primary text-white font-semibold disabled:opacity-50">Analyze couple</button>
        </div>
      )}
      {busy && <p className="text-xs text-on-surface-variant">Calculating…</p>}
      {res && !res.available && <p data-testid="repro-empty" className="text-xs text-on-surface-variant">{res.note}</p>}
      {res?.available && (
        <>
          <div className="overflow-x-auto" data-testid="repro-carriers">
            <table className="w-full text-xs"><thead><tr className="text-left text-on-surface-variant"><th>Partner</th><th>Gene</th><th>Variant</th><th>Classification</th><th>Genotype</th></tr></thead>
              <tbody>{res.partners.map((p) => (p.variants.length ? p.variants.map((v) => (
                <tr key={`${p.member_id}-${v.variant_key}`} className="border-t border-outline-variant/30"><td className="py-1 font-semibold">{p.label}</td><td>{v.gene}</td><td>{v.variant_key}</td><td>{v.classification || 'Not documented'}</td><td>{v.genotype_state}</td></tr>
              )) : <tr key={p.member_id} className="border-t border-outline-variant/30"><td className="py-1 font-semibold">{p.label}</td><td colSpan={4}>{p.note}</td></tr>))}</tbody></table>
          </div>
          <p className="text-xs text-on-surface-variant">Overall band: <b>{res.risk_band}</b>{res.relationship_from_pedigree && <> · Relationship from pedigree: {res.relationship_from_pedigree}</>}</p>
          <label className="text-xs font-semibold block">Condition
            <select aria-label="Condition" value={sel} onChange={(e) => { setSel(e.target.value); setExplain(null); setMc(null); setScenario(null) }} className="mt-1 block rounded-lg border border-outline-variant p-2 text-sm font-normal">
              {res.risks.map((r) => <option key={r.disease_id} value={r.disease_id}>{r.disease_name} ({r.gene}){r.supported ? '' : ' — not supported'}</option>)}
            </select>
          </label>
          {row && !row.supported && <p data-testid="repro-unsupported" className="text-xs text-amber-800">{row.note}</p>}
          {row?.supported && (
            <div className="space-y-3" data-testid="repro-detail">
              <div className="text-xs">
                <b>{row.inheritance}</b> · A: {row.carrier_status.partner_a} · B: {row.carrier_status.partner_b}
                <div data-testid="repro-probs">Both carriers {pct(row.probabilities.both_carriers)} · Child affected {pct(row.probabilities.child_affected)}{row.probabilities.one_in_n ? ` (1 in ${row.probabilities.one_in_n})` : ''} · Child carrier {pct(row.probabilities.child_carrier)}</div>
              </div>
              <div data-testid="repro-bayes" className="text-xs">
                <table><thead><tr className="text-left text-on-surface-variant"><th className="pr-4">Partner</th><th className="pr-4">Prior</th><th className="pr-4">Posterior</th><th>Basis</th></tr></thead>
                  <tbody>{['partner_a', 'partner_b'].map((k) => (
                    <tr key={k}><td className="pr-4">{k === 'partner_a' ? 'A' : 'B'}</td><td className="pr-4">{row.bayesian[k].prior ?? 'Not available'}</td><td className="pr-4">{row.bayesian[k].posterior}</td><td>{row.bayesian[k].update_basis}</td></tr>))}</tbody></table>
                <p className="text-outline">{row.bayesian.note}</p>
              </div>
              {row.punnett ? <Punnett p={row.punnett} /> : <p className="text-xs text-on-surface-variant">{row.punnett_note}</p>}
              {row.saved_evidence?.length > 0 && <div className="text-xs">Saved evidence: {row.saved_evidence.map((e) => e.title).join('; ')}</div>}

              <div className="flex flex-wrap gap-2 items-end text-xs border-t border-outline-variant/30 pt-2">
                <label className="font-semibold">Simulations<input aria-label="Simulations" type="number" min="1000" max="200000" value={mcIn.n} onChange={(e) => setMcIn({ ...mcIn, n: Number(e.target.value) })} className="mt-1 block w-28 rounded-lg border border-outline-variant p-2 font-normal" /></label>
                <label className="font-semibold">Seed<input aria-label="Seed" type="number" value={mcIn.seed} onChange={(e) => setMcIn({ ...mcIn, seed: Number(e.target.value) })} className="mt-1 block w-20 rounded-lg border border-outline-variant p-2 font-normal" /></label>
                <button onClick={() => guard(async () => setMc(await api.reproMonteCarlo(pid, { disease_id: sel, partner_a: couple.a || null, partner_b: couple.b || null, n: mcIn.n, seed: mcIn.seed })))} disabled={row.mode !== 'autosomal recessive'} className="px-3 py-2 rounded-lg border border-primary/30 text-primary font-semibold disabled:opacity-50">Run Monte Carlo</button>
                {row.mode !== 'autosomal recessive' && <span className="text-outline">Monte Carlo is available for autosomal recessive conditions only.</span>}
              </div>
              {mc && <div data-testid="repro-mc" className="text-xs">
                {Object.entries(mc.distribution).map(([k, v]) => <div key={k}>{k.replace(/_/g, ' ')}: {pct(v)} ({mc.counts[k]} of {mc.n_simulations})</div>)}
                <div>Affected 95% interval: {pct(mc.affected_ci95[0])} to {pct(mc.affected_ci95[1])} · Analytic: {pct(mc.analytic_affected_probability)}</div>
                <ul className="text-outline list-disc pl-4">{mc.assumptions.map((a) => <li key={a}>{a}</li>)}</ul></div>}

              <div className="flex flex-wrap gap-2 items-end text-xs border-t border-outline-variant/30 pt-2">
                {['a', 'b'].map((k) => (
                  <label key={k} className="font-semibold">What if partner {k.toUpperCase()} is
                    <select aria-label={`Scenario partner ${k.toUpperCase()}`} value={scn[k]} onChange={(e) => setScn({ ...scn, [k]: e.target.value })} className="mt-1 block rounded-lg border border-outline-variant p-2 font-normal">
                      {STATUSES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                    </select></label>))}
                <button onClick={() => guard(async () => setScenario(await api.reproScenario(pid, { disease_id: sel, status_a: scn.a, status_b: scn.b, partner_a: couple.a || null, partner_b: couple.b || null })))} className="px-3 py-2 rounded-lg border border-primary/30 text-primary font-semibold">Compare scenario</button>
              </div>
              {scenario && <div data-testid="repro-scenario" className="text-xs">
                <div>Baseline: child affected {pct(scenario.baseline.child_affected)}</div>
                <div>Scenario ({scenario.scenario.partner_a} / {scenario.scenario.partner_b}): child affected {pct(scenario.result.child_affected)}</div>
                <div className="text-outline">{scenario.note}</div></div>}

              <div className="flex flex-wrap gap-2 text-xs">
                <button onClick={() => guard(async () => setExplain(await api.reproExplain(pid, sel)))} className="px-3 py-1.5 rounded-lg border border-primary/30 text-primary font-semibold">Patient-friendly explanation</button>
                <button onClick={askAi} className="px-3 py-1.5 rounded-lg border border-primary/30 text-primary font-semibold">Ask AI Assistant</button>
                <button onClick={() => onNavigate?.('evidence')} className="px-3 py-1.5 rounded-lg border border-primary/30 text-primary font-semibold">Evidence</button>
              </div>
              {explain?.available && <div data-testid="repro-explain" className="text-xs space-y-1 rounded-lg bg-primary/5 p-3">
                <p>{explain.sections.what_we_know}</p><p>{explain.sections.what_the_calculation_means}</p>
                <p>{explain.sections.what_remains_uncertain}</p><p>{explain.sections.discuss_with_clinician}</p></div>}
            </div>
          )}
          <ul className="text-xs text-outline list-disc pl-4">{res.assumptions.map((a) => <li key={a}>{a}</li>)}</ul>
        </>
      )}
    </section>
  )
}
