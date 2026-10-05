import React, { useState } from 'react'
import { ArrowRight, Dna, Network, Stethoscope, Pill } from 'lucide-react'

export const pct = (p) => (p == null ? '-' : `${(p * 100).toFixed(1)}%`)
export const fmt = (v) => (v == null ? '-' : typeof v === 'number' ? String(Math.round(v * 10000) / 10000) : String(v))

const CLASS_STYLE = {
  Pathogenic: 'bg-red-100 text-red-800 border-red-300',
  'Likely pathogenic': 'bg-orange-100 text-orange-800 border-orange-300',
  'Uncertain significance': 'bg-amber-100 text-amber-900 border-amber-300',
  'Likely benign': 'bg-emerald-50 text-emerald-800 border-emerald-200',
  Benign: 'bg-emerald-50 text-emerald-800 border-emerald-200',
}

export function ClassBadge({ value }) {
  return (
    <span className={`px-2 py-0.5 rounded-full text-[10px] font-semibold border ${CLASS_STYLE[value] || 'bg-gray-100 text-gray-700 border-gray-300'}`}>
      {value}
    </span>
  )
}

export function Note({ children, tone = 'info' }) {
  const cls =
    tone === 'warn'
      ? 'bg-amber-50 border-amber-200 text-amber-900'
      : 'bg-surface-container-low border-outline-variant/40 text-on-surface-variant'
  return <div className={`text-xs rounded-lg border px-3 py-2 leading-relaxed ${cls}`}>{children}</div>
}

function Stat({ label, value }) {
  return (
    <div className="rounded-lg border border-outline-variant/40 bg-white px-3 py-2">
      <div className="text-[10px] uppercase tracking-wider text-outline font-semibold">{label}</div>
      <div className="text-lg font-bold text-on-surface">{value}</div>
    </div>
  )
}

function ActionButton({ onClick, icon: Icon = ArrowRight, children, testId }) {
  return (
    <button
      onClick={onClick}
      data-testid={testId}
      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-primary text-white text-xs font-semibold hover:bg-primary-container transition-colors"
    >
      <Icon size={13} />
      <span>{children}</span>
    </button>
  )
}

// ------------------------------- Phenotype -------------------------------

export function PhenotypePanel({ twin }) {
  const ph = twin.phenotype
  if (!ph.available) return <Note tone="warn">{ph.note}</Note>
  const max = Math.max(...ph.organ_systems.map((s) => s.hpo_ids.length), 1)
  return (
    <div className="space-y-4">
      <div>
        <h4 className="text-xs font-bold text-on-surface mb-2">Observed ({ph.count})</h4>
        <div className="divide-y divide-outline-variant/30 rounded-lg border border-outline-variant/40 bg-white">
          {ph.observed.map((o) => (
            <div key={o.hpo_id} className="px-3 py-2 text-xs" data-testid={`phenotype-${o.hpo_id}`}>
              <div className="flex items-center justify-between gap-2">
                <span className="font-semibold text-on-surface">
                  {o.name} <span className="font-mono text-outline">{o.hpo_id}</span>
                </span>
                <span className="text-[10px] text-outline">
                  first documented {o.first_documented_utc ? o.first_documented_utc.slice(0, 10) : 'n/a'}
                </span>
              </div>
              <div className="mt-0.5 text-on-surface-variant">
                Source: {o.sources.map((s) => `${s.label} (${s.ref})`).join('; ')}
                {o.sources.some((s) => s.evidence_text) &&
                  ` — "${o.sources.find((s) => s.evidence_text).evidence_text}"`}
              </div>
              <div className="text-[10px] text-outline">Onset: not recorded · Severity: not recorded</div>
            </div>
          ))}
        </div>
        <p className="text-[11px] text-outline mt-1">{ph.onset_severity}</p>
      </div>
      <div>
        <h4 className="text-xs font-bold text-on-surface mb-2">Organ systems (from the HPO hierarchy)</h4>
        <div className="space-y-1.5" data-testid="organ-systems">
          {ph.organ_systems.map((s) => (
            <div key={s.system_id} className="text-xs">
              <div className="flex justify-between">
                <span>{s.system}</span>
                <span className="font-mono text-outline">{s.hpo_ids.length}</span>
              </div>
              <div className="h-1.5 rounded bg-surface-container">
                <div className="h-1.5 rounded bg-primary" style={{ width: `${(100 * s.hpo_ids.length) / max}%` }} />
              </div>
            </div>
          ))}
        </div>
      </div>
      <div>
        <h4 className="text-xs font-bold text-on-surface mb-1">Missing / unknown</h4>
        {ph.expected_but_undocumented.length ? (
          <>
            <p className="text-[11px] text-outline mb-1">
              Expected for {ph.expected_for} but not documented (unknown, not confirmed absent):
            </p>
            <div className="flex flex-wrap gap-1.5">
              {ph.expected_but_undocumented.map((m) => (
                <span key={m.hpo_id} className="px-2 py-0.5 rounded-full bg-surface-container text-[11px]">
                  {m.hpo_name}
                </span>
              ))}
            </div>
          </>
        ) : (
          <p className="text-xs text-on-surface-variant">None identified for the current top diagnosis.</p>
        )}
        {ph.unmapped_symptoms.length > 0 && (
          <p className="text-xs text-on-surface-variant mt-2">
            Unmapped symptom text: {ph.unmapped_symptoms.join(', ')}
          </p>
        )}
      </div>
    </div>
  )
}

// ------------------------------- Genomic -------------------------------

export function GenomicPanel({ twin, patientId, nav }) {
  const g = twin.genomic
  if (!g.available) return <Note tone="warn">{g.note}</Note>
  const c = g.counts
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-2" data-testid="genomic-counts">
        <Stat label="Analysed" value={c.total} />
        <Stat label="Pathogenic" value={c.pathogenic} />
        <Stat label="Likely path." value={c.likely_pathogenic} />
        <Stat label="VUS" value={c.vus} />
        <Stat label="Benign / LB" value={c.benign_likely_benign} />
      </div>
      <div className="text-xs text-on-surface-variant">
        Analysis <span className="font-mono">{g.analysis_id}</span> · {g.filename}
        {g.hpo_set_differs_from_twin && (
          <span className="ml-2 text-amber-800">
            · analysis was prioritised with a different HPO set than the Twin's current one
          </span>
        )}
      </div>
      <div className="overflow-x-auto rounded-lg border border-outline-variant/40 bg-white">
        <table className="w-full text-xs">
          <thead className="bg-surface-container-low text-outline text-[10px] uppercase">
            <tr>
              <th className="text-left px-3 py-2">#</th>
              <th className="text-left px-3 py-2">Variant</th>
              <th className="text-left px-3 py-2">ACMG</th>
              <th className="text-left px-3 py-2">Priority</th>
              <th className="text-left px-3 py-2">Zygosity</th>
              <th className="px-3 py-2" />
            </tr>
          </thead>
          <tbody>
            {g.variants.map((v) => (
              <tr key={v.variant_id} className="border-t border-outline-variant/30" data-testid={`variant-row-${v.variant_id}`}>
                <td className="px-3 py-1.5 font-mono">{v.rank}</td>
                <td className="px-3 py-1.5">
                  <span className="font-semibold">{v.gene_symbol || '?'}</span> {v.cdna || v.hgvs}
                </td>
                <td className="px-3 py-1.5"><ClassBadge value={v.acmg_classification} /></td>
                <td className="px-3 py-1.5 font-mono">{v.priority_score}</td>
                <td className="px-3 py-1.5">{v.zygosity}</td>
                <td className="px-3 py-1.5 text-right">
                  <button
                    className="text-primary font-semibold hover:underline"
                    onClick={() => nav('variants', { patient_id: patientId, analysis_id: g.analysis_id, variant_id: v.variant_id })}
                  >
                    Open
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Note>{g.inheritance_note}</Note>
      <ActionButton icon={Dna} testId="open-variants" onClick={() => nav('variants', { patient_id: patientId, analysis_id: g.analysis_id })}>
        View Variant Analysis
      </ActionButton>
    </div>
  )
}

// ------------------------------- Diagnosis -------------------------------

export function DiagnosisPanel({ twin, patientId, nav }) {
  const dx = twin.diagnosis
  const [open, setOpen] = useState(null)
  if (!dx.available) return <Note tone="warn">{dx.note}</Note>
  const hpoNames = twin.phenotype.observed.map((o) => o.name).join(', ')
  const nm = Object.fromEntries(twin.phenotype.observed.map((o) => [o.hpo_id, o.name]))
  const d = twin.demographic
  return (
    <div className="space-y-4">
      <Note>{dx.ranking_basis}</Note>
      <div className="space-y-2" data-testid="differential">
        {dx.differential.map((r) => (
          <div key={r.disease_id} className="rounded-lg border border-outline-variant/40 bg-white p-3 text-xs">
            <div className="flex items-center justify-between gap-2">
              <div>
                <span className="font-mono text-outline mr-2">#{r.rank}</span>
                <span className="font-bold text-on-surface">{r.disease_name}</span>
                <span className="font-mono text-outline ml-2">{r.disease_id}</span>
              </div>
              <div className="font-mono font-bold text-primary">{pct(r.probability)}</div>
            </div>
            <div className="h-1.5 rounded bg-surface-container my-1.5">
              <div className="h-1.5 rounded bg-primary" style={{ width: `${Math.min(100, r.probability * 100)}%` }} />
            </div>
            <div className="flex flex-wrap gap-x-4 gap-y-1 text-on-surface-variant">
              <span>Similarity {fmt(r.phenotype_similarity)}</span>
              <span>Supporting phenotypes {r.supporting_phenotype_count}</span>
              <span>Genes: {r.genes.join(', ') || '-'}</span>
              <span>
                Genomic support: P/LP {r.genomic_support.pathogenic_or_likely} · VUS {r.genomic_support.vus}
              </span>
            </div>
            <div className="mt-2 flex items-center gap-3">
              <button className="text-primary font-semibold hover:underline" onClick={() => setOpen(open === r.disease_id ? null : r.disease_id)}>
                {open === r.disease_id ? 'Hide evidence' : 'Show evidence'}
              </button>
              <button
                className="text-primary font-semibold hover:underline"
                onClick={() => nav('kg', { disease_id: r.disease_id, genes: r.genes, variant_ids: r.genomic_support.variant_ids })}
              >
                Knowledge Graph
              </button>
            </div>
            {open === r.disease_id && (
              <div className="mt-2 space-y-2 border-t border-outline-variant/30 pt-2">
                <div>
                  <b>Chain:</b>{' '}
                  {r.genes.length ? r.genes.join(', ') : 'no gene'} → {r.disease_name} →{' '}
                  {(r.driving_symptoms || []).map((s) => nm[s.patient_term] || s.patient_term).join(', ') || 'no matched phenotype'}
                  {r.genomic_support.variant_ids.length > 0 && ` → ${r.genomic_support.variant_ids.join(', ')}`}
                </div>
                <div>
                  <b>Driving phenotypes:</b>{' '}
                  {(r.driving_symptoms || []).map((s) => `${nm[s.patient_term] || s.patient_term} (${s.weight_pct}%)`).join('; ') || '-'}
                </div>
                <div>
                  <b>Missing findings:</b> {(r.missing_findings || []).map((m) => m.hpo_name).join(', ') || '-'}
                </div>
                {r.confirmatory_tests && (
                  <div>
                    <b>Confirmatory tests:</b> {(r.confirmatory_tests.first_line || []).join('; ')}
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
      {dx.genomic_candidates.length > 0 && (
        <div>
          <h4 className="text-xs font-bold text-on-surface mb-1">Genomically implicated diseases</h4>
          <p className="text-[11px] text-outline mb-1">
            Diseases linked through the Knowledge Graph to non-benign variants. Shown separately from the
            phenotype ranking.
          </p>
          <div className="space-y-1" data-testid="genomic-candidates">
            {dx.genomic_candidates.map((c) => (
              <div key={c.disease_id} className="text-xs rounded border border-outline-variant/40 bg-white px-3 py-1.5 flex justify-between">
                <span className="font-semibold">{c.disease_name}</span>
                <span className="text-on-surface-variant">
                  P/LP {c.genomic_support.pathogenic_or_likely} · VUS {c.genomic_support.vus} · phenotype rank{' '}
                  {c.phenotype_rank_in_differential || 'outside top 10'}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
      <ActionButton
        icon={Stethoscope}
        testId="open-diagnosis"
        onClick={() => nav('diagnosis', { patient_id: patientId, text: hpoNames, state: d.state, community: d.community, sex: d.sex })}
      >
        Open Diagnosis Engine
      </ActionButton>
    </div>
  )
}

// ------------------------------- PGx -------------------------------

export function PgxPanel({ twin, nav }) {
  const p = twin.pgx
  if (!p.available) return <Note tone="warn">{p.note}</Note>
  return (
    <div className="space-y-3">
      <div className="space-y-1">
        {p.observations.map((o) => (
          <div key={o.variant_id} className="text-xs rounded border border-outline-variant/40 bg-white px-3 py-1.5">
            <b>{o.star_allele}</b> · {o.function} · {o.zygosity} ·{' '}
            {o.assigned_status ? `status: ${o.assigned_status}` : 'no metabolizer status assigned'}
          </div>
        ))}
      </div>
      {p.findings.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-outline-variant/40 bg-white">
          <table className="w-full text-xs" data-testid="pgx-findings">
            <thead className="bg-surface-container-low text-outline text-[10px] uppercase">
              <tr>
                <th className="text-left px-3 py-2">Drug</th>
                <th className="text-left px-3 py-2">Gene</th>
                <th className="text-left px-3 py-2">Severity</th>
                <th className="text-left px-3 py-2">Guideline / basis</th>
              </tr>
            </thead>
            <tbody>
              {p.findings.map((f) => (
                <tr key={`${f.drug}-${f.gene}`} className="border-t border-outline-variant/30">
                  <td className="px-3 py-1.5 font-semibold">{f.drug}</td>
                  <td className="px-3 py-1.5">{f.gene}</td>
                  <td className="px-3 py-1.5">{f.severity}</td>
                  <td className="px-3 py-1.5 text-on-surface-variant">
                    {f.recommendation || f.actionability} <span className="text-outline">({f.basis})</span>
                    {f.evidence_level && <span className="text-outline"> · evidence {f.evidence_level}</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <Note>{p.note}</Note>
      <ActionButton icon={Pill} onClick={() => nav('pgx', {})}>Open Pharmacogenomics</ActionButton>
    </div>
  )
}

// ------------------------------- Family -------------------------------

export function FamilyPanel({ twin }) {
  const f = twin.family
  return (
    <div className="space-y-3 text-xs">
      {!f.available && <Note tone="warn">{f.note}</Note>}
      {f.available && (
        <div className="rounded-lg border border-outline-variant/40 bg-white p-3 space-y-1">
          <div>Consanguineous parents: <b>{f.consanguineous_parents ? 'Yes' : 'No'}</b></div>
          {Object.entries(f.family_history).map(([k, v]) => (
            <div key={k}>Family history — {k}: {v}</div>
          ))}
          {f.known_carrier.length > 0 && <div>Known carrier: {f.known_carrier.join(', ')}</div>}
          {f.known_affected.length > 0 && <div>Known affected: {f.known_affected.join(', ')}</div>}
          {f.vcf_samples.length > 0 && <div>VCF samples: {f.vcf_samples.join(', ')}</div>}
        </div>
      )}
      <Note>{f.limitation}</Note>
    </div>
  )
}

// ------------------------------- Timeline -------------------------------

export function TimelinePanel({ twin }) {
  const t = twin.timeline
  return (
    <div className="space-y-3">
      {t.note && <Note tone="warn">{t.note}</Note>}
      <ol className="relative border-l border-outline-variant/50 ml-2 space-y-3" data-testid="timeline">
        {t.events.map((e, i) => (
          <li key={`${e.source.ref}-${i}`} className="ml-4 text-xs">
            <span className="absolute -left-1.5 w-3 h-3 rounded-full bg-primary" />
            <div className="font-semibold text-on-surface">{e.title}</div>
            <div className="text-on-surface-variant">{e.detail}</div>
            <div className="text-[10px] text-outline font-mono">
              {e.timestamp_utc} · {e.source.type}:{e.source.ref}
            </div>
          </li>
        ))}
      </ol>
    </div>
  )
}

// ------------------------------- Provenance -------------------------------

export function ProvenancePanel({ twin }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-outline-variant/40 bg-white">
      <table className="w-full text-xs" data-testid="provenance">
        <thead className="bg-surface-container-low text-outline text-[10px] uppercase">
          <tr>
            <th className="text-left px-3 py-2">Section</th>
            <th className="text-left px-3 py-2">Source</th>
            <th className="text-left px-3 py-2">Reference</th>
            <th className="text-left px-3 py-2">When</th>
          </tr>
        </thead>
        <tbody>
          {twin.provenance.map((p, i) => (
            <tr key={i} className="border-t border-outline-variant/30">
              <td className="px-3 py-1.5 font-semibold">{p.section}</td>
              <td className="px-3 py-1.5">{p.source}</td>
              <td className="px-3 py-1.5 font-mono">{p.ref}</td>
              <td className="px-3 py-1.5 font-mono text-outline">{p.timestamp_utc || 'computed now'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export { Stat, ActionButton, Network }
