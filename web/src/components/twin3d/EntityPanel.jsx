import React from 'react'
import { ChevronRight } from 'lucide-react'
import { ClassBadge, Note, pct } from '../twin/TwinSections.jsx'
import { geneRecord, systemById, variantById } from './selection.js'

function Chain({ items }) {
  return (
    <ol className="flex flex-wrap items-center gap-1 text-[11px]" data-testid="entity-chain" aria-label="Relationship chain">
      {items.map((it, i) => (
        <li key={`${it.label}-${i}`} className="flex items-center gap-1">
          {i > 0 && <ChevronRight size={12} className="text-outline" />}
          {it.onClick ? (
            <button onClick={it.onClick} className="px-2 py-0.5 rounded-full bg-primary/10 text-primary font-semibold hover:bg-primary/20">
              <span className="text-[9px] uppercase opacity-70 mr-1">{it.kind}</span>{it.label}
            </button>
          ) : (
            <span className="px-2 py-0.5 rounded-full bg-surface-container text-on-surface-variant">
              <span className="text-[9px] uppercase opacity-70 mr-1">{it.kind}</span>{it.label}
            </span>
          )}
        </li>
      ))}
    </ol>
  )
}

const Btn = ({ onClick, children, testId }) => (
  <button onClick={onClick} data-testid={testId} className="px-3 py-1.5 rounded-lg border border-primary text-primary text-xs font-semibold hover:bg-primary/5">
    {children}
  </button>
)

export default function EntityPanel({ twin, selection, patientId, nav, onSelect, onAsk }) {
  if (!selection) {
    return (
      <div className="text-xs text-on-surface-variant" data-testid="entity-panel">
        Select an organ system, a variant (genome or DNA view) or the leading diagnosis to see its evidence from this patient's data.
      </div>
    )
  }
  const analysisId = twin.genomic.analysis_id

  if (selection.kind === 'variant') {
    const v = variantById(twin, selection.id)
    if (!v) return <Note tone="warn">Variant not found in the selected analysis.</Note>
    const gene = geneRecord(twin, v.gene_symbol)
    const sys = twin.anatomy.systems.filter((s) => s.variant_ids.includes(v.variant_id))
    const diseases = gene?.diseases || []
    const openVariant = () => nav('variants', { patient_id: patientId, analysis_id: analysisId, variant_id: v.variant_id })
    return (
      <div className="space-y-3 text-xs" data-testid="entity-panel">
        <Chain items={[
          { kind: 'DNA', label: v.chrom || 'chr?' },
          { kind: 'Gene', label: v.gene_symbol || 'unknown', onClick: v.gene_symbol ? () => onSelect({ kind: 'gene', id: v.gene_symbol }) : undefined },
          { kind: 'Variant', label: v.cdna || v.hgvs },
          ...(sys.length ? sys.map((s) => ({ kind: 'System', label: s.label, onClick: () => onSelect({ kind: 'system', id: s.id }) }))
            : [{ kind: 'System', label: 'no supported association' }]),
          ...(diseases[0] ? [{ kind: 'Disease', label: diseases[0].name }] : []),
        ]} />
        <div>
          <div className="text-base font-bold text-on-surface">{v.gene_symbol} <span className="font-mono text-sm">{v.cdna || v.hgvs}</span></div>
          <div className="mt-1 flex flex-wrap items-center gap-2"><ClassBadge value={v.acmg_classification} /> <span>Priority {v.priority_score} · {v.priority_tier}</span></div>
        </div>
        <div className="grid grid-cols-2 gap-x-3 gap-y-1">
          <span>Position: <b className="font-mono">{v.chrom}:{v.pos}</b></span>
          <span>Zygosity: <b>{v.zygosity}</b></span>
          <span>Consequence: <b>{v.consequence}</b></span>
          <span>Indian AF: <b>{v.af_indian == null ? 'not in catalog' : v.af_indian}</b></span>
          <span>ClinVar: <b>{v.clinvar_significance || 'no record'}</b></span>
          <span>Inheritance: <b>{v.inheritance || '-'}</b></span>
        </div>
        <div>
          <b>Associated condition:</b> {diseases.length ? diseases.map((d) => d.name).join(', ') : (v.disease_name || 'none in the knowledge graph')}
        </div>
        <div>
          <b>Phenotype relevance:</b>{' '}
          {v.matched_hpo_terms?.length
            ? v.matched_hpo_terms.map((h) => twin.phenotype.observed.find((o) => o.hpo_id === h)?.name || h).join(', ')
            : 'no documented patient phenotype overlaps this variant\'s disease'}
        </div>
        <div>
          <b>ACMG criteria met:</b> {[...(v.criteria_met_pathogenic || []), ...(v.criteria_met_benign || [])].join(', ') || 'none'}
          {v.acmg_explanation && <p className="text-on-surface-variant mt-0.5">{v.acmg_explanation}</p>}
        </div>
        <div className="text-on-surface-variant"><b>Evidence sources:</b> ACMG/AMP engine, {v.clinvar_id ? `ClinVar ${v.clinvar_id}` : 'ClinVar (no matching record)'}, IndiGenomes/GenomeIndia frequencies, Genomera knowledge graph</div>
        <div className="flex flex-wrap gap-2">
          <Btn testId="view-acmg" onClick={openVariant}>View ACMG Evidence</Btn>
          <Btn testId="view-variant" onClick={openVariant}>View Variant</Btn>
          <Btn testId="view-kg" onClick={() => nav('kg', { disease_id: diseases[0]?.disease_id, genes: [v.gene_symbol], variant_ids: [v.variant_id] })}>View Knowledge Graph</Btn>
          <Btn testId="ask-variant" onClick={() => onAsk(`Why is this patient's ${v.gene_symbol} variant important?`, v.variant_id)}>Ask AI</Btn>
        </div>
      </div>
    )
  }

  if (selection.kind === 'gene') {
    const g = geneRecord(twin, selection.id)
    if (!g) return <Note tone="warn">Gene not found in this patient's analysis.</Note>
    return (
      <div className="space-y-3 text-xs" data-testid="entity-panel">
        <Chain items={[{ kind: 'Gene', label: g.gene }, ...Object.keys(g.systems).map((id) => ({ kind: 'System', label: systemById(twin, id)?.label || id, onClick: () => onSelect({ kind: 'system', id }) }))]} />
        <div className="text-base font-bold">{g.gene} <span className="text-xs font-normal text-on-surface-variant">{g.node?.name}</span></div>
        <div><b>Diseases (knowledge graph):</b> {g.diseases.map((d) => `${d.name}${d.inheritance ? ` (${d.inheritance})` : ''}`).join('; ') || 'none'}</div>
        <div><b>Patient variants:</b>{' '}
          {g.variants.map((x) => (
            <button key={x.variant_id} className="mr-2 text-primary font-semibold hover:underline" onClick={() => onSelect({ kind: 'variant', id: x.variant_id })}>{x.hgvs} ({x.classification})</button>
          ))}
        </div>
        <div><b>Body systems (via documented disease manifestations):</b> {Object.keys(g.systems).map((id) => systemById(twin, id)?.label).join(', ') || 'none mapped'}</div>
        <div className="flex gap-2">
          <Btn onClick={() => nav('kg', { disease_id: g.diseases[0]?.disease_id, genes: [g.gene], variant_ids: g.variants.map((x) => x.variant_id) })}>Open Knowledge Graph</Btn>
          <Btn onClick={() => nav('variants', { patient_id: patientId, analysis_id: analysisId, variant_id: g.variants[0]?.variant_id })}>Open Variant Intelligence</Btn>
          <Btn onClick={() => onAsk(`What is the clinical significance of ${g.gene} for this patient?`, g.variants[0]?.variant_id)}>Ask AI</Btn>
        </div>
      </div>
    )
  }

  if (selection.kind === 'system') {
    const s = systemById(twin, selection.id)
    if (!s) return null
    return (
      <div className="space-y-3 text-xs" data-testid="entity-panel">
        <div className="text-base font-bold">{s.label}</div>
        {!s.has_case_data ? (
          <>
            <Note>{s.note}</Note>
            <div className="text-on-surface-variant">Clinical state: no organ-specific data available.</div>
          </>
        ) : (
          <>
            <div><b>Relevant findings:</b>
              <ul className="list-disc ml-5">{s.phenotypes.map((p) => <li key={p.hpo_id}>{p.name} <span className="font-mono text-outline">{p.hpo_id}</span></li>)}
                {!s.phenotypes.length && <li>No documented phenotype maps here; linked through genomic findings only.</li>}</ul></div>
            <div><b>Genes:</b>{' '}{s.genes.map((g) => <button key={g} className="mr-2 text-primary font-semibold hover:underline" onClick={() => onSelect({ kind: 'gene', id: g })}>{g}</button>)}{!s.genes.length && '-'}</div>
            <div><b>Variants:</b>{' '}{s.variant_ids.map((id) => { const v = variantById(twin, id); return <button key={id} className="mr-2 text-primary font-semibold hover:underline" onClick={() => onSelect({ kind: 'variant', id })}>{v?.gene_symbol} {v?.cdna || v?.hgvs}</button> })}{!s.variant_ids.length && '-'}</div>
            <div><b>Diseases:</b> {s.diseases.map((d) => d.name).join(', ') || '-'}</div>
            <div className="flex gap-2">
              <Btn onClick={() => nav('kg', { disease_id: s.diseases[0]?.disease_id, genes: s.genes, variant_ids: s.variant_ids })}>Open Knowledge Graph</Btn>
              <Btn onClick={() => onAsk(`Which findings in this patient relate to the ${s.label.toLowerCase()} system?`)}>Ask AI</Btn>
            </div>
          </>
        )}
        <p className="text-[10px] text-outline">Highlighting indicates mapped data, not organ damage or imaging findings.</p>
      </div>
    )
  }

  if (selection.kind === 'diagnosis') {
    const d = twin.diagnosis.differential.find((x) => x.disease_id === selection.id) || twin.diagnosis.top_diagnosis
    if (!d) return null
    return (
      <div className="space-y-3 text-xs" data-testid="entity-panel">
        <div className="text-[10px] uppercase text-outline font-semibold">Current leading diagnosis</div>
        <div className="text-base font-bold">{d.disease_name} <span className="font-mono text-xs text-outline">{d.disease_id}</span></div>
        <div>Probability (existing engine): <b>{pct(d.probability)}</b> · similarity {d.phenotype_similarity}</div>
        <ul className="space-y-0.5">
          <li>{d.supporting_phenotype_count > 0 ? '✓' : '–'} Phenotypes: {d.supporting_phenotype_count} supporting</li>
          <li>{d.genes.length ? '✓' : '–'} Gene: {d.genes.join(', ') || 'none in knowledge graph'}</li>
          <li>{d.genomic_support.variant_ids.length ? '✓' : '–'} Variant: {d.genomic_support.variant_ids.length} non-benign (P/LP {d.genomic_support.pathogenic_or_likely}, VUS {d.genomic_support.vus})</li>
          <li>{d.confirmatory_tests ? '✓' : '–'} Confirmatory tests: {(d.confirmatory_tests?.first_line || []).join('; ') || 'none listed'}</li>
        </ul>
        <div className="flex gap-2">
          <Btn testId="open-diagnosis-2" onClick={() => nav('diagnosis', { patient_id: patientId, text: twin.phenotype.observed.map((o) => o.name).join(', '), state: twin.demographic.state, community: twin.demographic.community, sex: twin.demographic.sex })}>Open Diagnosis</Btn>
          <Btn onClick={() => nav('kg', { disease_id: d.disease_id, genes: d.genes, variant_ids: d.genomic_support.variant_ids })}>Open Knowledge Graph</Btn>
        </div>
      </div>
    )
  }
  return null
}
