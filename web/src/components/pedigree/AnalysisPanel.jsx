import React from 'react'
import { Check, X, HelpCircle, Info } from 'lucide-react'

const STATE_TEXT = { het: 'Heterozygous', hom: 'Homozygous', hemi: 'Hemizygous', absent: 'Absent', unknown: 'Unavailable', unavailable: 'Not recorded' }
const VERDICT_STYLE = {
  consistent: 'bg-emerald-50 text-emerald-900 border-emerald-300',
  possible: 'bg-sky-50 text-sky-900 border-sky-300',
  inconclusive: 'bg-amber-50 text-amber-900 border-amber-300',
  not_consistent: 'bg-slate-100 text-slate-700 border-slate-300',
}
const VERDICT_TEXT = { consistent: 'Consistent', possible: 'Possible', inconclusive: 'Inconclusive', not_consistent: 'Not consistent' }
const EV_ICON = { supports: <Check size={13} className="text-emerald-700 mt-0.5 shrink-0" />, conflicts: <X size={13} className="text-red-700 mt-0.5 shrink-0" />, unknown: <HelpCircle size={13} className="text-amber-700 mt-0.5 shrink-0" />, note: <Info size={13} className="text-sky-700 mt-0.5 shrink-0" /> }

const Card = ({ title, children, testId }) => (
  <section className="rounded-xl border border-outline-variant/40 bg-white p-4 space-y-2" data-testid={testId}>
    <h4 className="text-xs font-bold text-on-surface">{title}</h4>
    {children}
  </section>
)

export function InheritanceTab({ a }) {
  const best = a.most_consistent
  return (
    <div className="space-y-3 text-xs" data-testid="inheritance-result">
      <div className="rounded-xl border border-primary/30 bg-primary/5 p-4 space-y-1">
        <div className="text-[10px] uppercase tracking-wider text-outline font-semibold">Inheritance assessment</div>
        <div className="text-base font-bold text-on-surface" data-testid="most-consistent">
          {best ? `Most consistent model: ${best.label} (${VERDICT_TEXT[best.verdict].toLowerCase()})` : 'Inheritance pattern inconclusive'}
        </div>
        <div>Evidence completeness: <b data-testid="completeness">{a.completeness.level}</b>
          <span className="text-on-surface-variant"> · {a.completeness.parents_with_genotype} parent genotype(s), {a.completeness.informative_relatives} informative relative(s)</span></div>
        {a.reference_inheritance.text && (
          <div className="text-on-surface-variant">Knowledge-graph reference for this gene's condition: {a.reference_inheritance.text}
            {a.reference_inheritance.agrees === true ? ' — agrees with the family data.' : a.reference_inheritance.agrees === false ? ' — differs from the family-supported model.' : '.'}</div>
        )}
      </div>
      {a.why.length > 0 && (
        <Card title="Why?" testId="why">
          <ol className="list-decimal ml-5 space-y-0.5">{a.why.map((w, i) => <li key={i}>{w}</li>)}</ol>
        </Card>
      )}
      {a.models.map((m) => (
        <Card key={m.model} title={`${m.label}`} testId={`model-${m.model}`}>
          <span className={`inline-block px-2 py-0.5 rounded-full border text-[10px] font-semibold ${VERDICT_STYLE[m.verdict]}`}>{VERDICT_TEXT[m.verdict]}</span>
          <ul className="space-y-1 mt-1">
            {m.evidence.map((e, i) => <li key={i} className="flex gap-1.5" data-status={e.status}>{EV_ICON[e.status]}<span>{e.text}</span></li>)}
          </ul>
        </Card>
      ))}
      {a.uncertainty.length > 0 && (
        <Card title="Uncertainty and missing data" testId="uncertainty">
          <ul className="space-y-1">{a.uncertainty.map((u, i) => <li key={i} className="flex gap-1.5"><HelpCircle size={13} className="text-amber-700 mt-0.5 shrink-0" /><span>{u}</span></li>)}</ul>
        </Card>
      )}
    </div>
  )
}

export function SegregationTab({ a }) {
  const s = a.segregation
  const c = s.counts
  return (
    <div className="space-y-3 text-xs" data-testid="segregation-result">
      <Card title="Genotype comparison (trio)" testId="trio-table">
        {a.trio.available ? (
          <table className="w-full"><thead className="text-[10px] uppercase text-outline"><tr><th className="text-left py-1">Member</th><th className="text-left">{a.variant.gene} {a.variant.hgvs}</th><th className="text-left">Status</th></tr></thead>
            <tbody>{a.trio.rows.map((r) => (
              <tr key={r.role} className="border-t border-outline-variant/30"><td className="py-1">{r.role}{r.label && r.label !== r.role ? ` (${r.label})` : ''}</td>
                <td data-testid={`trio-${r.role}`}>{STATE_TEXT[r.state] || r.state}</td><td>{r.affected || r.note || '-'}</td></tr>))}</tbody></table>
        ) : <p className="text-on-surface-variant">{a.trio.note || 'No trio recorded.'}</p>}
        {a.trio.note && a.trio.available && <p className="text-amber-800">{a.trio.note}</p>}
      </Card>
      <Card title="Segregation" testId="segregation-table">
        <table className="w-full">
          <tbody>
            {[['Affected + variant', c.affected_carrier], ['Affected + no variant', c.affected_noncarrier], ['Unaffected + variant', c.unaffected_carrier], ['Unaffected + no variant', c.unaffected_noncarrier]].map(([l, n]) => (
              <tr key={l} className="border-t border-outline-variant/30"><td className="py-1">{l}</td><td className="font-mono font-bold text-right" data-testid={`seg-${l.replace(/[^a-z]+/gi, '-').toLowerCase()}`}>{n}</td></tr>
            ))}
          </tbody>
        </table>
        <p className="text-on-surface-variant">Informative members: {s.informative_members}. Excluded: {s.excluded.unknown_genotype.length} without genotype, {s.excluded.unknown_affected_status.length} with unknown affected status.</p>
        {s.note && <p className="text-amber-800">{s.note}</p>}
      </Card>
      <Card title="De novo assessment" testId="de-novo">
        <div className="font-semibold">{a.de_novo.status === 'candidate' ? 'Candidate de novo' : a.de_novo.status === 'inherited' ? 'Inherited' : a.de_novo.status === 'not_applicable' ? 'Not applicable' : 'Cannot be assessed'}</div>
        {a.de_novo.parents.length > 0 && <div>Parental genotypes: {a.de_novo.parents.map((p) => `${p.role}: ${STATE_TEXT[p.state] || p.state}`).join(' · ')}</div>}
        <p>{a.de_novo.assessment}</p>
        {a.de_novo.caveat && <p className="text-on-surface-variant">{a.de_novo.caveat}</p>}
      </Card>
      {a.compound_het && (
        <Card title={`Compound heterozygosity — ${a.compound_het.gene}`} testId="compound-het">
          {a.compound_het.pairs.map((p, i) => (
            <div key={i} className="border-t border-outline-variant/30 pt-1" data-phase={p.phase}>
              <div className="font-semibold">{p.hgvs_a || p.variant_a} + {p.hgvs_b || p.variant_b}: {p.phase === 'trans' ? 'in trans' : p.phase === 'cis' ? 'in cis' : 'phase unavailable'}</div>
              <div className="text-on-surface-variant">{p.assessment}</div>
            </div>
          ))}
        </Card>
      )}
    </div>
  )
}

export function EvidenceTab({ a }) {
  const p = a.pp1
  const acmg = a.acmg
  const dc = a.diagnosis_context
  return (
    <div className="space-y-3 text-xs" data-testid="evidence-result">
      <Card title="PP1 — co-segregation with disease" testId="pp1">
        <div className="flex items-center gap-2">
          <span className={`px-2 py-0.5 rounded-full border text-[10px] font-semibold ${p.status === 'supported' ? VERDICT_STYLE.consistent : p.status === 'not_supported' ? VERDICT_STYLE.not_consistent : VERDICT_STYLE.inconclusive}`} data-testid="pp1-status">
            {p.status === 'supported' ? `Supported (${p.strength})` : p.status === 'not_supported' ? 'Not supported' : 'Insufficient'}
          </span>
          <span className="text-on-surface-variant">Source: {p.source}</span>
        </div>
        <p>{p.reason}</p>
        <p className="text-on-surface-variant">Thresholds (affected carriers incl. proband): {p.thresholds.map(([n, s]) => `${n}+ ${s}`).join(', ')}. Heuristic; assumes full penetrance.</p>
        <div className="rounded-lg bg-surface-container-low p-2" data-testid="acmg-preview">
          <div>Stored ACMG/AMP classification: <b>{acmg.stored_classification}</b></div>
          {acmg.classification_with_pp1
            ? <div>With PP1 ({p.strength}) the engine would classify it as <b>{acmg.classification_with_pp1}</b>{acmg.changed ? ' (changed)' : ' (unchanged)'}.</div>
            : <div className="text-on-surface-variant">PP1 is not applied.</div>}
          <div className="text-[11px] text-outline">{acmg.note}</div>
        </div>
      </Card>
      {dc && (
        <Card title="Pedigree and diagnosis" testId="diagnosis-context">
          {dc.available ? (
            <>
              {dc.pedigree_pattern && <p className="font-semibold">{dc.pedigree_pattern}</p>}
              <ul className="space-y-0.5">
                {dc.candidates.map((c) => (
                  <li key={c.disease_id}>{c.disease_name} <span className="text-outline">({(c.probability * 100).toFixed(1)}%, {c.inheritance || 'inheritance n/a'})</span>
                    {c.gene_has_family_variant ? ' — gene carries a family variant' : ''}{c.pattern_compatible === true ? ' — pattern compatible' : c.pattern_compatible === false ? ' — pattern differs' : ''}</li>
                ))}
              </ul>
              <p className="text-on-surface-variant">{dc.note}</p>
            </>
          ) : <p className="text-amber-800">{dc.note}</p>}
        </Card>
      )}
    </div>
  )
}

export function PrioritisationTab({ data }) {
  if (!data) return <p className="text-xs text-on-surface-variant">Loading…</p>
  return (
    <div className="space-y-2 text-xs" data-testid="prioritisation">
      <p className="text-on-surface-variant">{data.method}</p>
      {data.rows.length === 0 && <p className="text-amber-800">No non-benign variant carried by the proband is registered in this pedigree.</p>}
      {data.rows.map((r) => (
        <div key={r.variant_key} className="rounded-xl border border-outline-variant/40 bg-white p-3" data-testid={`prio-${r.gene}`}>
          <div className="flex justify-between"><b>{r.gene} {r.hgvs}</b><span className="font-mono">{r.base_priority_score ?? 'n/a'} → <b>{r.family_adjusted_score ?? 'n/a'}</b></span></div>
          <div className="text-on-surface-variant">{r.classification} · {r.most_consistent_model || 'no consistent model'}</div>
          {r.adjustments.length ? (
            <ul className="mt-1 space-y-0.5">{r.adjustments.map((x) => <li key={x.code}><span className="font-mono">{x.delta > 0 ? '+' : ''}{x.delta}</span> {x.reason}</li>)}</ul>
          ) : <div className="text-outline mt-1">No family-based adjustment applies.</div>}
        </div>
      ))}
    </div>
  )
}

export function ReproTab({ data, error, busy, onRun }) {
  return (
    <div className="space-y-2 text-xs" data-testid="repro-tab">
      <button onClick={onRun} disabled={busy} data-testid="run-repro" className="px-3 py-1.5 rounded-lg bg-primary text-white font-semibold disabled:opacity-60">{busy ? 'Calculating…' : 'Use family inheritance data'}</button>
      {error && <div role="alert" className="text-red-800">{error}</div>}
      {data && (
        <div className="space-y-1" data-testid="repro-result">
          <p>Partners: {data.partners.map((p) => p.label).join(' and ')}{data.relationship_from_pedigree ? ` (related: ${data.relationship_from_pedigree.replace('_', ' ')})` : ''}</p>
          <p>Risk band: <b>{data.assessment.risk_band}</b></p>
          <ul className="space-y-0.5">{data.assessment.top_risks.slice(0, 5).map((r) => (
            <li key={r.disease_id}>{r.disease_name}: both carriers {(r.both_carriers_probability * 100).toFixed(0)}%, affected child {(r.child_affected_probability * 100).toFixed(1)}%</li>))}</ul>
          <p className="text-on-surface-variant">{data.note}</p>
        </div>
      )}
    </div>
  )
}
