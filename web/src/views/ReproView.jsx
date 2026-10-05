import ReproCasePanel from '../components/ReproCasePanel.jsx'
import ReproFromPedigree from '../components/pedigree/ReproFromPedigree.jsx'
import React, { useState } from 'react'
import { api } from '../api.js'
import {
  HeartHandshake,
  Users,
  ShieldAlert,
  AlertTriangle,
  CheckCircle2,
  Sparkles,
  Info,
  Calendar,
  Building,
  FileText,
  Languages,
  Code2,
  ChevronRight,
  TrendingUp,
  Percent,
} from 'lucide-react'
import { PageHeader } from '../components/ui/PageHeader.jsx'
import { ClinicalCard } from '../components/ui/ClinicalCard.jsx'
import { StatusBadge, SeverityBadge } from '../components/ui/StatusBadge.jsx'
import { ScoreBar } from '../components/ui/ScoreBar.jsx'
import { StatCard } from '../components/ui/StatCard.jsx'
import { ErrorAlert } from '../components/ui/ErrorAlert.jsx'
import { SkeletonCard } from '../components/ui/LoadingSkeleton.jsx'
import { EmptyState } from '../components/ui/EmptyState.jsx'

const QUICK_COUPLES = [
  {
    label: 'Scenario 1: First Cousins (Sindhi × Punjabi Khatri)',
    aCommunity: 'Sindhi',
    bCommunity: 'Punjabi Khatri',
    state: 'Maharashtra',
    relation: 'first_cousins',
    lang: 'en',
  },
  {
    label: 'Scenario 2: South India Uncle–Niece (Andhra Pradesh)',
    aCommunity: 'Reddy',
    bCommunity: 'Reddy',
    state: 'Andhra Pradesh',
    relation: 'uncle_niece',
    lang: 'en',
  },
  {
    label: 'Scenario 3: Non-Consanguineous Endogamy',
    aCommunity: 'Chettiar',
    bCommunity: 'Chettiar',
    state: 'Tamil Nadu',
    relation: '',
    lang: 'hi',
  },
]

export default function ReproView({ onNavigate } = {}) {
  const [aCommunity, setACommunity] = useState(QUICK_COUPLES[0].aCommunity)
  const [bCommunity, setBCommunity] = useState(QUICK_COUPLES[0].bCommunity)
  const [state, setState] = useState(QUICK_COUPLES[0].state)
  const [relation, setRelation] = useState(QUICK_COUPLES[0].relation)
  const [lang, setLang] = useState(QUICK_COUPLES[0].lang)
  const [res, setRes] = useState(null)
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)
  const [showRawJson, setShowRawJson] = useState(false)

  async function run() {
    setBusy(true)
    setErr(null)
    setRes(null)
    try {
      const mk = (community) => {
        const p = { community, sex: 'F' }
        if (state.trim()) p.state = state.trim()
        if (relation) p.relationship = relation
        return p
      }
      const r = await api.counsel({
        partner_a: mk(aCommunity),
        partner_b: { ...mk(bCommunity), sex: 'M' },
        lang,
      })
      setRes(r)
    } catch (ex) {
      setErr(ex.message)
    } finally {
      setBusy(false)
    }
  }

  const applyCouple = (c) => {
    setACommunity(c.aCommunity)
    setBCommunity(c.bCommunity)
    setState(c.state)
    setRelation(c.relation)
    setLang(c.lang)
  }

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <PageHeader
        title="Reproductive Genetic Counseling"
        subtitle="Couple carrier risk evaluation, inbreeding coefficient computation, and government rare disease support schemes (NPRD 2021)."
        badge={{
          label: 'Carrier Screening & Inbreeding Model',
          color: 'primary',
          icon: HeartHandshake,
        }}
      />

      {/* Input Panel */}
      <ClinicalCard
        title="Couple Demographics & Pedigree Kinship"
        subtitle="Configure partner communities, geographic origin, and consanguinity coefficient."
        icon={Users}
      >
        <div className="space-y-4">
          {/* Quick Scenarios */}
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[11px] font-semibold text-outline uppercase tracking-wider">
              Scenarios:
            </span>
            {QUICK_COUPLES.map((c, i) => (
              <button
                key={i}
                type="button"
                onClick={() => applyCouple(c)}
                className="text-xs px-2.5 py-1 rounded-md bg-surface-container-low hover:bg-surface-container border border-outline-variant/40 text-on-surface-variant hover:text-primary transition-colors font-medium"
              >
                {c.label}
              </button>
            ))}
          </div>

          {/* Form Fields */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
            <div>
              <label className="block text-xs font-semibold text-on-surface-variant mb-1">
                Partner A Community
              </label>
              <input
                type="text"
                value={aCommunity}
                onChange={(e) => setACommunity(e.target.value)}
                placeholder="e.g. Sindhi"
                className="w-full h-10 px-3 rounded-lg bg-surface-container-low border border-outline-variant/60 text-xs text-on-surface focus:outline-none focus:border-primary font-medium"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-on-surface-variant mb-1">
                Partner B Community
              </label>
              <input
                type="text"
                value={bCommunity}
                onChange={(e) => setBCommunity(e.target.value)}
                placeholder="e.g. Punjabi Khatri"
                className="w-full h-10 px-3 rounded-lg bg-surface-container-low border border-outline-variant/60 text-xs text-on-surface focus:outline-none focus:border-primary font-medium"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-on-surface-variant mb-1">
                State (Optional)
              </label>
              <input
                type="text"
                value={state}
                onChange={(e) => setState(e.target.value)}
                placeholder="e.g. Maharashtra"
                className="w-full h-10 px-3 rounded-lg bg-surface-container-low border border-outline-variant/60 text-xs text-on-surface focus:outline-none focus:border-primary font-medium"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-on-surface-variant mb-1">
                Consanguinity Kinship
              </label>
              <select
                value={relation}
                onChange={(e) => setRelation(e.target.value)}
                className="w-full h-10 px-3 rounded-lg bg-surface-container-low border border-outline-variant/60 text-xs text-on-surface focus:outline-none focus:border-primary font-medium"
              >
                <option value="">Non-consanguineous</option>
                <option value="first_cousins">First Cousins (F = 0.0625)</option>
                <option value="uncle_niece">Uncle–Niece (F = 0.125)</option>
                <option value="second_cousins">Second Cousins (F = 0.0156)</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-semibold text-on-surface-variant mb-1">
                Report Language
              </label>
              <select
                value={lang}
                onChange={(e) => setLang(e.target.value)}
                className="w-full h-10 px-3 rounded-lg bg-surface-container-low border border-outline-variant/60 text-xs text-on-surface focus:outline-none focus:border-primary font-medium"
              >
                <option value="en">English</option>
                <option value="hi">हिंदी (Hindi)</option>
                <option value="ta">தமிழ் (Tamil)</option>
              </select>
            </div>
          </div>

          {/* Action Row */}
          <div className="flex items-center justify-between pt-2 border-t border-outline-variant/30">
            <span className="text-[11px] text-outline">
              Calculates joint carrier risk using South Asian founder frequencies and pedigree coefficients
            </span>
            <button
              onClick={run}
              disabled={busy}
              className="px-5 py-2.5 rounded-lg bg-primary text-white text-xs font-bold hover:bg-primary-hover disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-sm flex items-center gap-2"
            >
              {busy ? (
                <>
                  <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  <span>Computing Risks…</span>
                </>
              ) : (
                <>
                  <Sparkles size={15} />
                  <span>Generate Counseling Report</span>
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
          {/* Top Risk Band & Metrics */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard
              title="Risk Band"
              value={res.risk_band ? res.risk_band.toUpperCase() : 'STANDARD'}
              subtitle="Overall couple risk tier"
              icon={ShieldAlert}
              color={
                (res.risk_band || '').toLowerCase() === 'high'
                  ? 'danger'
                  : (res.risk_band || '').toLowerCase() === 'elevated'
                  ? 'warning'
                  : 'success'
              }
            />
            <StatCard
              title="Inbreeding Coeff (F)"
              value={res.inbreeding_coefficient != null ? res.inbreeding_coefficient : '0.000'}
              subtitle={relation ? relation.replace(/_/g, ' ') : 'Unrelated pedigree'}
              icon={Percent}
              color="primary"
            />
            <StatCard
              title="High-Risk Conditions"
              value={res.high_risk_conditions?.length || 0}
              subtitle="Carrier overlap conditions"
              icon={AlertTriangle}
              color="warning"
            />
            <StatCard
              title="Screening Tests"
              value={res.recommended_screening?.length || 0}
              subtitle="Pre-conception actions"
              icon={CheckCircle2}
              color="secondary"
            />
          </div>

          {/* Regional Consanguinity Notice */}
          {res.regional_consanguinity_flag && (
            <div className="p-4 rounded-xl bg-amber-50 border border-amber-200 text-amber-900 flex items-center gap-3">
              <AlertTriangle size={20} className="shrink-0 text-amber-700" />
              <div className="text-xs leading-relaxed">
                <span className="font-bold">Elevated Regional Consanguinity: </span>
                This patient's geographic origin is classified as an area with high historical consanguinity. Baseline risks for rare autosomal recessive conditions are elevated above national non-consanguineous averages.
              </div>
            </div>
          )}

          {/* Punnett Square Probability Model Card */}
          {res.top_risks?.[0] && (
            <div className="p-5 rounded-xl bg-white border border-outline-variant/40 shadow-xs space-y-4">
              <div className="flex items-center justify-between">
                <div className="space-y-0.5">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-outline">
                    Autosomal Recessive Mendelian Distribution
                  </span>
                  <h4 className="text-base font-bold text-on-surface">
                    Top Identified Risk: {res.top_risks[0].disease_name}
                  </h4>
                </div>
                <div className="text-right">
                  <span className="text-xs font-mono font-bold text-primary px-2.5 py-1 rounded bg-primary-container/20">
                    {res.top_risks[0].one_in_n_children || 'Risk Ratio'}
                  </span>
                </div>
              </div>

              {/* Punnett Visualizer */}
              <div className="grid grid-cols-3 gap-3 p-4 rounded-xl bg-surface-container-low border border-outline-variant/30 text-center">
                <div className="p-3 rounded-lg bg-emerald-50 border border-emerald-200">
                  <span className="text-[10px] font-bold text-emerald-800 uppercase block">
                    Unaffected (Non-Carrier)
                  </span>
                  <div className="text-xl font-mono font-bold text-emerald-700 mt-1">25%</div>
                  <span className="text-[10px] text-emerald-600">AA Normal</span>
                </div>
                <div className="p-3 rounded-lg bg-blue-50 border border-blue-200">
                  <span className="text-[10px] font-bold text-blue-800 uppercase block">
                    Asymptomatic Carrier
                  </span>
                  <div className="text-xl font-mono font-bold text-blue-700 mt-1">50%</div>
                  <span className="text-[10px] text-blue-600">Aa Carrier</span>
                </div>
                <div className="p-3 rounded-lg bg-red-50 border border-red-200">
                  <span className="text-[10px] font-bold text-red-800 uppercase block">
                    Affected Child
                  </span>
                  <div className="text-xl font-mono font-bold text-red-700 mt-1">
                    {res.top_risks[0].child_affected_probability
                      ? `${(res.top_risks[0].child_affected_probability * 100).toFixed(2)}%`
                      : '25%'}
                  </div>
                  <span className="text-[10px] text-red-600">aa Affected</span>
                </div>
              </div>
            </div>
          )}

          {/* Top Carrier Risks Table */}
          {res.top_risks?.length > 0 && (
            <div className="p-5 rounded-xl bg-white border border-outline-variant/40 shadow-xs space-y-3">
              <h4 className="text-xs font-bold text-outline uppercase tracking-wider">
                Recessive Conditions Joint Risk Matrix
              </h4>

              <div className="overflow-x-auto rounded-lg border border-outline-variant/40">
                <table className="w-full text-left text-xs border-collapse">
                  <thead>
                    <tr className="bg-surface-container-low text-on-surface-variant border-b border-outline-variant/40 font-semibold uppercase text-[10px]">
                      <th className="p-3">Condition / Gene</th>
                      <th className="p-3 text-center">Partner A Carrier</th>
                      <th className="p-3 text-center">Partner B Carrier</th>
                      <th className="p-3 text-center">Both Carriers</th>
                      <th className="p-3 text-center">Child Affected Risk</th>
                      <th className="p-3 text-right">Population Frequency</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-outline-variant/20">
                    {res.top_risks.map((r, i) => (
                      <tr key={i} className="hover:bg-surface-container-low/40">
                        <td className="p-3">
                          <div className="font-bold text-on-surface">{r.disease_name}</div>
                          <div className="text-[10px] font-mono text-outline">
                            {r.gene || r.disease_id} · {r.inheritance || 'Autosomal Recessive'}
                          </div>
                        </td>
                        <td className="p-3 text-center font-mono">
                          {formatProb(r.carrier_probability_partner_a)}
                        </td>
                        <td className="p-3 text-center font-mono">
                          {formatProb(r.carrier_probability_partner_b)}
                        </td>
                        <td className="p-3 text-center font-mono font-semibold text-secondary">
                          {formatProb(r.both_carriers_probability)}
                        </td>
                        <td className="p-3 text-center">
                          <span className="px-2 py-0.5 rounded font-mono font-bold text-xs bg-red-50 text-red-700 border border-red-200">
                            {formatProb(r.child_affected_probability)}
                          </span>
                        </td>
                        <td className="p-3 text-right text-[11px] text-outline font-mono">
                          {r.one_in_n_children || '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Recommended Screening & Government Schemes Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Recommended Pre-conception Screening */}
            {res.recommended_screening?.length > 0 && (
              <div className="p-5 rounded-xl bg-white border border-outline-variant/40 shadow-xs space-y-3">
                <div className="flex items-center gap-2">
                  <CheckCircle2 size={16} className="text-primary" />
                  <h4 className="text-xs font-bold text-on-surface uppercase tracking-wider">
                    Recommended Pre-Conception Screening
                  </h4>
                </div>
                <div className="space-y-2">
                  {res.recommended_screening.map((s, i) => (
                    <div
                      key={i}
                      className="p-3 rounded-lg bg-surface-container-low border border-outline-variant/30 space-y-1"
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-xs text-on-surface">{s.condition}</span>
                        {s.timing && (
                          <span className="text-[10px] px-2 py-0.5 rounded bg-surface-container-high text-on-surface-variant font-medium">
                            {s.timing}
                          </span>
                        )}
                      </div>
                      <div className="text-xs text-primary font-medium">{s.test}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Indian Government Welfare Schemes */}
            {res.government_schemes?.length > 0 && (
              <div className="p-5 rounded-xl bg-white border border-outline-variant/40 shadow-xs space-y-3">
                <div className="flex items-center gap-2">
                  <Building size={16} className="text-secondary" />
                  <h4 className="text-xs font-bold text-on-surface uppercase tracking-wider">
                    Indian Government Financial Support Schemes
                  </h4>
                </div>
                <div className="space-y-2">
                  {res.government_schemes.map((sc, i) => (
                    <div
                      key={i}
                      className="p-3 rounded-lg bg-surface-container-low border border-outline-variant/30 space-y-1"
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-xs text-secondary">{sc.name}</span>
                      </div>
                      <div className="text-xs text-on-surface-variant leading-relaxed">
                        {sc.benefit}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Multilingual Counseling Letter / Narrative Prose */}
          {res.counseling_letter && (
            <ClinicalCard
              title="Family Counseling Document"
              subtitle={`Prepared in ${lang === 'hi' ? 'Hindi' : lang === 'ta' ? 'Tamil' : 'English'} for patient distribution`}
              icon={FileText}
            >
              <div className="text-xs text-on-surface leading-relaxed whitespace-pre-wrap bg-surface-container-low/50 p-4 rounded-xl border border-outline-variant/40">
                {res.counseling_letter}
              </div>
            </ClinicalCard>
          )}

          {/* Raw JSON Debug Accordion */}
          <div className="pt-2">
            <button
              onClick={() => setShowRawJson(!showRawJson)}
              className="text-xs font-mono text-outline hover:text-on-surface flex items-center gap-1.5"
            >
              <Code2 size={14} />
              <span>{showRawJson ? 'Hide Raw Reproductive Payload' : 'Inspect Raw Counseling Payload (Audit Log)'}</span>
            </button>
            {showRawJson && (
              <pre className="mt-2 p-4 rounded-xl bg-surface-container-lowest border border-outline-variant/40 text-[11px] font-mono text-on-surface-variant overflow-x-auto max-h-96">
                {JSON.stringify(res, null, 2)}
              </pre>
            )}
          </div>
        </div>
      )}

      {/* Empty State */}
      {!res && !busy && (
        <EmptyState
          icon={HeartHandshake}
          title="No Carrier Assessment Generated"
          description="Select partner communities and consanguinity kinship above, then click 'Generate Counseling Report' to assess reproductive carrier risk."
          actionText="Run Demonstration Scenario"
          onAction={() => {
            applyCouple(QUICK_COUPLES[0])
            run()
          }}
        />
      )}

      <ReproCasePanel onNavigate={onNavigate} />
      <ReproFromPedigree />
    </div>
  )
}

function formatProb(p) {
  if (typeof p === 'number') {
    if (p < 0.0001 && p > 0) return '<0.01%'
    return `${(p * 100).toFixed(2)}%`
  }
  return '—'
}
