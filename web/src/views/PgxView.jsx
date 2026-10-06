import React, { useEffect, useState } from 'react'
import { api } from '../api.js'
import {
  Pill,
  ShieldAlert,
  AlertTriangle,
  CheckCircle2,
  AlertOctagon,
  Info,
  Sparkles,
  ArrowRight,
  Search,
  BookOpen,
  Languages,
  Code2,
  ChevronDown,
  ChevronRight,
  Activity,
  Layers,
  Database,
} from 'lucide-react'
import PgxCasePanel from '../components/PgxCasePanel.jsx'
import { PageHeader } from '../components/ui/PageHeader.jsx'
import { ClinicalCard } from '../components/ui/ClinicalCard.jsx'
import { SeverityBadge, EvidenceBadge, StatusBadge } from '../components/ui/StatusBadge.jsx'
import { ScoreBar } from '../components/ui/ScoreBar.jsx'
import { StatCard } from '../components/ui/StatCard.jsx'
import { ErrorAlert } from '../components/ui/ErrorAlert.jsx'
import { SkeletonCard } from '../components/ui/LoadingSkeleton.jsx'
import { EmptyState } from '../components/ui/EmptyState.jsx'

const QUICK_PRESETS = [
  {
    label: 'Preset 1: Clopidogrel + Primaquine',
    drugs: 'clopidogrel, primaquine',
    state: 'Gujarat',
    ethnicity: '',
    genotypes: 'CYP2C19: *2/*2, G6PD: deficient',
  },
  {
    label: 'Preset 2: Carbamazepine (SCAR Risk)',
    drugs: 'carbamazepine',
    state: 'Tamil Nadu',
    ethnicity: '',
    genotypes: 'HLA-B: *15:02',
  },
  {
    label: 'Preset 3: Warfarin Anticoagulation',
    drugs: 'warfarin',
    state: 'Maharashtra',
    ethnicity: 'Parsi',
    genotypes: 'CYP2C9: *3/*3',
  },
]

export default function PgxView({ onNavigate }) {
  const [drugs, setDrugs] = useState(QUICK_PRESETS[0].drugs)
  const [state, setState] = useState(QUICK_PRESETS[0].state)
  const [ethnicity, setEthnicity] = useState(QUICK_PRESETS[0].ethnicity)
  const [genotypes, setGenotypes] = useState(QUICK_PRESETS[0].genotypes)
  const [coverage, setCoverage] = useState(null)
  const [coverageFilter, setCoverageFilter] = useState('')
  const [res, setRes] = useState(null)
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)
  const [showRawJson, setShowRawJson] = useState(false)

  useEffect(() => {
    api.pgxCoverage()
      .then(setCoverage)
      .catch(() => {})
  }, [])

  async function run() {
    if (!drugs.trim()) return
    setBusy(true)
    setErr(null)
    setRes(null)

    try {
      const known = {}
      genotypes.split(',').forEach((pair) => {
        const [gene, gt] = pair.split(':')
        if (gene?.trim() && gt?.trim()) known[gene.trim()] = gt.trim()
      })
      const body = {
        drugs: drugs
          .split(',')
          .map((d) => d.trim())
          .filter(Boolean),
        lang: 'en',
      }
      if (state.trim()) body.state = state.trim()
      if (ethnicity.trim()) body.ethnicity = ethnicity.trim()
      if (Object.keys(known).length) body.known_genotypes = known

      const r = await api.pgxCheck(body)
      setRes(r)
    } catch (ex) {
      setErr(ex.message)
    } finally {
      setBusy(false)
    }
  }

  const applyPreset = (p) => {
    setDrugs(p.drugs)
    setState(p.state)
    setEthnicity(p.ethnicity)
    setGenotypes(p.genotypes)
  }

  // Filter coverage rows
  const filteredCoverage = (coverage?.rows || []).filter((r) => {
    if (!coverageFilter) return true
    const q = coverageFilter.toLowerCase()
    return (
      (r.drug || '').toLowerCase().includes(q) ||
      (r.gene || '').toLowerCase().includes(q) ||
      (r.severity || '').toLowerCase().includes(q)
    )
  })

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <PageHeader
        title="Pharmacogenomic Drug Safety"
        subtitle="Prescription screening calibrated by Indian allele frequencies (IndiGenomes) and CPIC Level 1A/1B clinical guidelines."
        badge={{
          label: 'CPIC + IndiGenomes Engine',
          color: 'secondary',
          icon: Pill,
        }}
      />
      <PgxCasePanel onNavigate={onNavigate} />

      {/* Input Configuration Card */}
      <ClinicalCard
        title="Prescription & Genomic Profile"
        subtitle="Enter prescribed medications, optional regional population context, and known patient genotypes."
        icon={Pill}
      >
        <div className="space-y-4">
          {/* Quick Presets */}
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[11px] font-semibold text-outline uppercase tracking-wider">
              Quick Scenarios:
            </span>
            {QUICK_PRESETS.map((p, i) => (
              <button
                key={i}
                type="button"
                onClick={() => applyPreset(p)}
                className="text-xs px-2.5 py-1 rounded-md bg-surface-container-low hover:bg-surface-container border border-outline-variant/40 text-on-surface-variant hover:text-primary transition-colors font-medium"
              >
                {p.label}
              </button>
            ))}
          </div>

          {/* Medication Input */}
          <div>
            <label className="block text-xs font-bold text-on-surface uppercase tracking-wider mb-1">
              Prescribed Medications (Comma-separated)
            </label>
            <input aria-label="Prescribed Medications (Comma-separated)"
              type="text"
              value={drugs}
              onChange={(e) => setDrugs(e.target.value)}
              placeholder="e.g., clopidogrel, primaquine, warfarin, carbamazepine"
              className="w-full h-10 px-3.5 rounded-lg bg-surface-container-low border border-outline-variant/60 text-sm text-on-surface focus:outline-none focus:border-primary font-medium"
            />
          </div>

          {/* Demographic & Genotype Inputs */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div>
              <label className="block text-xs font-semibold text-on-surface-variant mb-1">
                Patient State (Optional AF Prior)
              </label>
              <input aria-label="Patient State (Optional AF Prior)"
                type="text"
                value={state}
                onChange={(e) => setState(e.target.value)}
                placeholder="e.g. Gujarat, Tamil Nadu"
                className="w-full h-10 px-3 rounded-lg bg-surface-container-low border border-outline-variant/60 text-xs text-on-surface focus:outline-none focus:border-primary font-medium"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-on-surface-variant mb-1">
                Community / Ethnicity (Optional)
              </label>
              <input aria-label="Community / Ethnicity (Optional)"
                type="text"
                value={ethnicity}
                onChange={(e) => setEthnicity(e.target.value)}
                placeholder="e.g. Sindhi, Parsi"
                className="w-full h-10 px-3 rounded-lg bg-surface-container-low border border-outline-variant/60 text-xs text-on-surface focus:outline-none focus:border-primary font-medium"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-on-surface-variant mb-1">
                Known Genotypes (gene: variant)
              </label>
              <input aria-label="Known Genotypes (gene: variant)"
                type="text"
                value={genotypes}
                onChange={(e) => setGenotypes(e.target.value)}
                placeholder="e.g. CYP2C19: *2/*2, G6PD: deficient"
                className="w-full h-10 px-3 rounded-lg bg-surface-container-low border border-outline-variant/60 text-xs text-on-surface focus:outline-none focus:border-primary font-mono"
              />
            </div>
          </div>

          {/* Action Row */}
          <div className="flex items-center justify-between pt-2 border-t border-outline-variant/30">
            <span className="text-[11px] text-outline">
              Integrates Hardy-Weinberg equilibrium inference if genotypes are unsequenced
            </span>
            <button
              onClick={run}
              disabled={busy || !drugs.trim()}
              className="px-5 py-2.5 rounded-lg bg-primary text-white text-xs font-bold hover:bg-primary-hover disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-sm flex items-center gap-2"
            >
              {busy ? (
                <>
                  <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  <span>Checking Guidelines…</span>
                </>
              ) : (
                <>
                  <ShieldAlert size={15} />
                  <span>Assess Prescription Risk</span>
                </>
              )}
            </button>
          </div>
        </div>
      </ClinicalCard>

      {/* Error Alert */}
      {err && <ErrorAlert error={err} onRetry={run} />}

      {/* Loading Skeletons */}
      {busy && (
        <div className="space-y-4">
          <SkeletonCard />
          <SkeletonCard />
        </div>
      )}

      {/* Results Section */}
      {res && !busy && (
        <div className="space-y-6">
          {/* Summary Metric Cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard
              title="Total Alerts"
              value={res.summary?.total_alerts ?? (res.alerts?.length || 0)}
              subtitle="Interactions evaluated"
              icon={Activity}
              color="primary"
            />
            <StatCard
              title="Critical Severity"
              value={res.summary?.critical ?? 0}
              subtitle="Contraindicated / high risk"
              icon={AlertOctagon}
              color="danger"
            />
            <StatCard
              title="High / Elevated"
              value={res.summary?.high ?? 0}
              subtitle="Dose modification needed"
              icon={AlertTriangle}
              color="warning"
            />
            <StatCard
              title="Moderate / Low"
              value={(res.summary?.medium ?? 0) + (res.summary?.low ?? 0)}
              subtitle="Monitor therapy"
              icon={CheckCircle2}
              color="success"
            />
          </div>

          {/* Headline Banner */}
          {res.summary?.headline && (
            <div
              className={`p-4 rounded-xl border flex items-center gap-3 ${
                (res.summary?.critical || 0) > 0
                  ? 'bg-red-50/70 border-red-200 text-red-900'
                  : (res.summary?.high || 0) > 0
                  ? 'bg-amber-50/70 border-amber-200 text-amber-900'
                  : 'bg-emerald-50/70 border-emerald-200 text-emerald-900'
              }`}
            >
              {(res.summary?.critical || 0) > 0 ? (
                <AlertOctagon size={20} className="shrink-0 text-red-700" />
              ) : (
                <ShieldAlert size={20} className="shrink-0 text-amber-700" />
              )}
              <div className="text-xs font-semibold leading-relaxed">
                {res.summary.headline}
              </div>
            </div>
          )}

          {/* Structured Drug Risk Cards */}
          {res.alerts?.length > 0 && (
            <div className="space-y-4">
              <h4 className="text-xs font-bold text-outline uppercase tracking-wider">
                Pharmacogenomic Actionable Alerts ({res.alerts.length})
              </h4>

              <div className="grid grid-cols-1 gap-4">
                {res.alerts.map((a, i) => (
                  <div
                    key={i}
                    className="p-5 rounded-xl bg-white border border-outline-variant/40 shadow-xs space-y-4"
                  >
                    {/* Header Row: Drug, Gene, Severity, Evidence */}
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-outline-variant/30">
                      <div className="flex items-center gap-3">
                        <div className="p-2.5 rounded-lg bg-surface-container text-primary">
                          <Pill size={20} />
                        </div>
                        <div>
                          <div className="flex items-center gap-2">
                            <h4 className="text-base font-bold text-on-surface uppercase">
                              {a.drug}
                            </h4>
                            <span className="text-xs font-mono font-bold text-primary px-2 py-0.5 rounded bg-primary-container/20 border border-primary/20">
                              {a.gene}
                            </span>
                          </div>
                          <div className="text-[11px] text-outline mt-0.5">
                            Status: <span className="font-semibold text-on-surface capitalize">{a.inferred_status?.replace(/_/g, ' ')}</span>
                            {a.assumption && (
                              <span className="ml-1 text-outline">
                                ({a.assumption === 'known_genotype' ? 'Known Patient Genotype' : 'Inferred from Indian Population AF'})
                              </span>
                            )}
                          </div>
                        </div>
                      </div>

                      <div className="flex items-center gap-2">
                        {a.evidence_level && (
                          <EvidenceBadge level={`Level ${a.evidence_level}`} source="CPIC" />
                        )}
                        <SeverityBadge severity={a.severity} />
                      </div>
                    </div>

                    {/* CPIC Clinical Recommendation */}
                    {a.recommendation && (
                      <div className="p-3.5 rounded-lg bg-surface-container-low border border-outline-variant/40 space-y-1">
                        <div className="text-[10px] font-bold text-outline uppercase tracking-wider">
                          CPIC Clinical Guideline Recommendation
                        </div>
                        <div className="text-xs text-on-surface leading-relaxed font-medium">
                          {a.recommendation}
                        </div>
                      </div>
                    )}

                    {/* Alternatives Section */}
                    {a.alternatives?.length > 0 && (
                      <div className="space-y-1.5">
                        <span className="text-[10px] font-bold text-outline uppercase tracking-wider block">
                          Suggested Safe Alternative Therapies:
                        </span>
                        <div className="flex flex-wrap gap-2">
                          {a.alternatives.map((alt, idx) => (
                            <span
                              key={idx}
                              className="inline-flex items-center gap-1.5 px-3 py-1 rounded-md bg-emerald-50 text-emerald-800 border border-emerald-200 text-xs font-semibold"
                            >
                              <CheckCircle2 size={13} className="text-emerald-600" />
                              <span>{alt}</span>
                            </span>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Phenotype Distribution Probabilities (Hardy-Weinberg) */}
                    {a.phenotype_probabilities && (
                      <div className="p-3.5 rounded-lg bg-surface-container-lowest border border-outline-variant/30 space-y-2">
                        <div className="text-[10px] font-bold text-outline uppercase tracking-wider flex items-center justify-between">
                          <span>Hardy-Weinberg Population Phenotype Probabilities</span>
                          {a.af_source && (
                            <span className="font-normal font-mono text-[10px] text-outline">
                              Source: {a.af_source}
                            </span>
                          )}
                        </div>
                        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1">
                          {Object.entries(a.phenotype_probabilities).map(([ph, prob]) => (
                            <div
                              key={ph}
                              className="p-2 rounded bg-surface-container-low border border-outline-variant/30 text-center"
                            >
                              <div className="text-[10px] text-outline truncate capitalize">
                                {ph.replace(/_/g, ' ')}
                              </div>
                              <div className="text-xs font-mono font-bold text-on-surface mt-0.5">
                                {(prob * 100).toFixed(1)}%
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Patient-facing Hindi Counseling Explanation */}
                    {a.patient_explanation_hi && (
                      <div className="p-3 rounded-lg bg-blue-50/60 border border-blue-200/60 text-xs text-blue-900 space-y-1">
                        <div className="flex items-center gap-1.5 font-bold text-[11px] text-blue-800">
                          <Languages size={14} />
                          <span>मरीज परामर्श विवरण (Hindi Patient Counseling Explanation)</span>
                        </div>
                        <p className="text-xs leading-relaxed text-blue-950">
                          {a.patient_explanation_hi}
                        </p>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Unaffected / Normal Risk Drugs */}
          {res.drugs_without_pgx_rule?.length > 0 && (
            <div className="p-4 rounded-xl bg-white border border-outline-variant/40 space-y-2">
              <span className="text-[10px] font-bold text-outline uppercase tracking-wider">
                Uninvolved Medications (Standard Prescribing / No High-Risk Rules)
              </span>
              <div className="flex flex-wrap gap-2">
                {res.drugs_without_pgx_rule.map((d, idx) => (
                  <span
                    key={idx}
                    className="px-2.5 py-1 rounded-md bg-surface-container-low text-xs text-on-surface-variant border border-outline-variant/30 flex items-center gap-1.5"
                  >
                    <CheckCircle2 size={13} className="text-outline" />
                    <span className="capitalize">{d}</span>
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Formal Clinical Report Prose */}
          {res.report && (
            <ClinicalCard
              title="Clinical Pharmacogenomics Consultation Report"
              subtitle="Generated consultation note for patient EMR chart"
              icon={BookOpen}
            >
              <div className="text-xs text-on-surface leading-relaxed whitespace-pre-wrap bg-surface-container-low/50 p-4 rounded-xl border border-outline-variant/40 font-mono">
                {typeof res.report === "string" ? res.report : (res.report?.markdown || "")}
              </div>
            </ClinicalCard>
          )}

          {/* Disclaimer */}
          {res.disclaimer && (
            <div className="text-[11px] text-outline italic text-center">
              {res.disclaimer}
            </div>
          )}

          {/* Raw JSON Debug Accordion */}
          <div className="pt-2">
            <button
              onClick={() => setShowRawJson(!showRawJson)}
              className="text-xs font-mono text-outline hover:text-on-surface flex items-center gap-1.5"
            >
              <Code2 size={14} />
              <span>{showRawJson ? 'Hide Raw PGx Payload' : 'Inspect Raw PGx Payload (Audit Log)'}</span>
            </button>
            {showRawJson && (
              <pre className="mt-2 p-4 rounded-xl bg-surface-container-lowest border border-outline-variant/40 text-[11px] font-mono text-on-surface-variant overflow-x-auto max-h-96">
                {JSON.stringify(res, null, 2)}
              </pre>
            )}
          </div>
        </div>
      )}

      {/* Drug-Gene Coverage Table */}
      {coverage && (
        <ClinicalCard
          title={`CPIC & Indian Allele Coverage (${coverage.n_pairs} Drug–Gene Pairs)`}
          subtitle={`${coverage.n_critical} critical interactions mapped with IndiGenomes population data`}
          icon={Database}
          defaultOpen={false}
          headerBadge={{
            label: `${coverage.n_pairs} Pairs`,
            color: 'primary',
          }}
          actions={
            <div className="relative w-48">
              <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-outline" />
              <input aria-label="Filter pairs..."
                type="text"
                placeholder="Filter pairs..."
                value={coverageFilter}
                onChange={(e) => setCoverageFilter(e.target.value)}
                className="w-full h-8 pl-7 pr-2 rounded bg-surface-container border border-outline-variant/40 text-xs text-on-surface focus:outline-none"
              />
            </div>
          }
        >
          <div className="overflow-x-auto rounded-lg border border-outline-variant/40">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="bg-surface-container-low text-on-surface-variant border-b border-outline-variant/40 font-semibold uppercase text-[10px]">
                  <th className="p-2.5">Gene</th>
                  <th className="p-2.5">Drug</th>
                  <th className="p-2.5">Severity</th>
                  <th className="p-2.5">Evidence</th>
                  <th className="p-2.5">Indian AF</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-outline-variant/20">
                {filteredCoverage.slice(0, 20).map((r, i) => (
                  <tr key={i} className="hover:bg-surface-container-low/40">
                    <td className="p-2.5 font-mono font-bold text-primary">{r.gene}</td>
                    <td className="p-2.5 font-bold text-on-surface capitalize">{r.drug}</td>
                    <td className="p-2.5">
                      <SeverityBadge severity={r.severity} />
                    </td>
                    <td className="p-2.5 text-outline">{r.evidence_level || '1A'}</td>
                    <td className="p-2.5 font-mono text-outline">
                      {typeof r.allele_frequency === 'number'
                        ? `${(r.allele_frequency * 100).toFixed(1)}%`
                        : r.allele_frequency || '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="text-[11px] text-outline mt-2">
            Sources: CPIC Level 1A/1B guidelines × IndiGenomes / 1000 Genomes SAS frequencies.
          </div>
        </ClinicalCard>
      )}

      {/* Empty State when no assessment run */}
      {!res && !busy && (
        <EmptyState
          icon={Pill}
          title="No Prescription Risk Assessed"
          description="Enter medications or choose a quick scenario above, then click 'Assess Prescription Risk' to screen drug-gene interactions."
          actionText="Run Clopidogrel + Primaquine Scenario"
          onAction={() => {
            applyPreset(QUICK_PRESETS[0])
            run()
          }}
        />
      )}
    </div>
  )
}
