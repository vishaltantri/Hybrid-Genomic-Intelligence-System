import React from 'react'
import {
  Cpu,
  Bot,
  Dna,
  BookOpen,
  Calendar,
  CheckCircle2,
  Clock,
  ArrowRight,
  ShieldCheck,
} from 'lucide-react'

const ROADMAP_DETAILS = {
  'digital-twin': {
    title: 'Patient Digital Twin Engine',
    phase: 'Phase 4 (In-Silico Computational Modeling)',
    icon: Cpu,
    color: 'text-primary',
    bg: 'bg-primary/10',
    summary:
      'Patient-specific computational state model integrating phenotypic vectors, variant callsets, organ system risk matrices, and pharmacogenomic metabolizer profiles for longitudinal scenario testing.',
    plannedFeatures: [
      'Phenotype trajectory progression and what-if simulation',
      'Variant reclassification in-silico impact analysis',
      'Adverse drug-drug and drug-gene metabolic interaction forecast',
      'Longitudinal case state snapshots & diff comparison',
    ],
    technicalSpec:
      'Backed by DifferentialDiagnosisEngine and PGxEngine; reuses Resnik semantic similarity and Hardy-Weinberg probability spaces without mock models.',
  },
  'ai-assistant': {
    title: 'Genomera Clinical Intelligence Copilot',
    phase: 'Phase 3 (Grounded Decision-Support Assistant)',
    icon: Bot,
    color: 'text-secondary',
    bg: 'bg-secondary/10',
    summary:
      'Grounded clinical conversational assistant utilizing an internal Groq LLM architecture to provide natural language explanations of ranked differentials, variant pathogenicity, and founder effect risks.',
    plannedFeatures: [
      'Case-aware conversational reasoning referencing active patient findings',
      'Direct attribution citations linking HPO terms to OMIM/Orphanet IDs',
      'Strict clinical safety guardrails (never diagnoses autonomously)',
      'Prompt injection defenses and isolated inference context',
    ],
    technicalSpec:
      'Internal orchestration layer with Knowledge Graph RAG retrieval; provider name abstracted from clinical interface.',
  },
  variants: {
    title: 'VCF Variant Interpretation & ACMG Prioritization',
    phase: 'Phase 2 (Genomics & Bioinformatics Foundation)',
    icon: Dna,
    color: 'text-tertiary',
    bg: 'bg-tertiary/10',
    summary:
      'End-to-end VCF file ingestion, automated ACMG/AMP tier classification (PVS1, PS1-4, PM1-6, PP1-5), and IndiGenomes/gnomAD population allele frequency filtering.',
    plannedFeatures: [
      'Patient VCF/gVCF file upload and sequencing QC filter validation',
      'Heuristic ACMG criteria evidence assignment',
      'Joint phenotype + genotype rank multiplication',
      'Protein structural domain mapping and Missense impact scoring',
    ],
    technicalSpec:
      'Integration with Ensembl VEP / ClinVar databases to complement phenotype-only ranking.',
  },
  evidence: {
    title: 'Literature & Clinical Evidence Synthesis',
    phase: 'Phase 2 (Evidence Intelligence)',
    icon: BookOpen,
    color: 'text-primary-container',
    bg: 'bg-primary-container/10',
    summary:
      'Real-time scientific literature grounding engine connecting candidate genetic variants and disease phenotypes to peer-reviewed PubMed/PMC evidence and CPIC clinical trials.',
    plannedFeatures: [
      'Automated PubMed REST retrieval with evidence freshness scoring',
      'Citation extraction with paper DOI links and abstract summaries',
      'Discrepancy detection between historical assertions and current publications',
      'Evidence provenance graphs linking functional assays to diagnostic calls',
    ],
    technicalSpec:
      'NCBI E-utilities integration with rate limiting and local SQLite evidence caching.',
  },
}

export default function PlaceholderView({ moduleId, onNavigateToDiagnosis }) {
  const info = ROADMAP_DETAILS[moduleId] || {
    title: 'Module Under Active Development',
    phase: 'Scheduled in Master Plan',
    icon: Clock,
    color: 'text-primary',
    bg: 'bg-primary/10',
    summary: 'This capability is documented in PLAN.md and scheduled for implementation.',
    plannedFeatures: ['Under architectural specification'],
    technicalSpec: 'Engineered in upcoming milestone phases.',
  }

  const Icon = info.icon

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Header Banner */}
      <div className="p-8 rounded-2xl bg-white border border-outline-variant/40 shadow-xs">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-6 border-b border-outline-variant/30">
          <div className="flex items-center gap-4">
            <div className={`w-12 h-12 rounded-xl ${info.bg} flex items-center justify-center ${info.color} shrink-0`}>
              <Icon size={26} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-mono uppercase font-bold text-secondary px-2 py-0.5 rounded bg-secondary-container/20">
                  {info.phase}
                </span>
                <span className="text-[11px] text-outline font-mono">SPEC: PLAN.md</span>
              </div>
              <h2 className="text-xl font-bold font-headline-sm text-on-surface mt-1">{info.title}</h2>
            </div>
          </div>
        </div>

        {/* Narrative Description */}
        <div className="py-6 space-y-4">
          <p className="text-sm text-on-surface-variant leading-relaxed">{info.summary}</p>

          <div className="p-4 rounded-xl bg-surface-container-low border border-outline-variant/30">
            <h4 className="text-xs font-bold text-on-surface uppercase tracking-wider mb-2 flex items-center gap-1.5">
              <ShieldCheck size={14} className="text-secondary" />
              <span>Architectural Rigor Note</span>
            </h4>
            <p className="text-xs text-on-surface-variant leading-relaxed">{info.technicalSpec}</p>
          </div>
        </div>

        {/* Planned Capabilities */}
        <div>
          <h4 className="text-xs font-bold text-on-surface uppercase tracking-wider mb-3">
            Engineered Capabilities Under Implementation:
          </h4>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {info.plannedFeatures.map((feat, idx) => (
              <div key={idx} className="p-3 rounded-lg bg-white border border-outline-variant/30 flex items-start gap-2.5 text-xs text-on-surface">
                <CheckCircle2 size={16} className="text-secondary shrink-0 mt-0.5" />
                <span>{feat}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Action Link to Functional Modules */}
        <div className="mt-8 pt-5 border-t border-outline-variant/30 flex items-center justify-between">
          <span className="text-xs text-outline">
            Phase 1 is active: Differential Diagnosis, PGx, Reproductive & KG are live.
          </span>
          {onNavigateToDiagnosis && (
            <button
              onClick={() => onNavigateToDiagnosis('diagnosis')}
              className="inline-flex items-center gap-1.5 text-xs font-semibold text-primary hover:underline"
            >
              <span>Explore Active Diagnosis</span>
              <ArrowRight size={14} />
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
