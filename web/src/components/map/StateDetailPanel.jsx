import React from 'react'
import {
  X,
  Building2,
  Stethoscope,
  TestTube,
  AlertTriangle,
  CheckCircle2,
  Users,
  Activity,
  Layers,
  ArrowRight,
  ShieldCheck,
  TrendingUp,
} from 'lucide-react'
import { ScoreBar } from '../ui/ScoreBar.jsx'
import { SeverityBadge, StatusBadge } from '../ui/StatusBadge.jsx'

export default function StateDetailPanel({
  state,
  onClose,
  onViewInTable,
}) {
  if (!state) return null

  const isUnavailable = state.is_unavailable || (state.cases == null && state.confirmed == null)

  const byDisease = state.by_disease || {}
  const diseaseEntries = Object.entries(byDisease).sort((a, b) => b[1] - a[1])
  const totalDiseaseCases = diseaseEntries.reduce((sum, [, count]) => sum + count, 0)

  return (
    <div className="rounded-2xl bg-white border border-outline-variant/40 shadow-xs overflow-hidden flex flex-col h-full">
      {/* Panel Header */}
      <div className="p-4 bg-gradient-to-r from-surface-container-low to-white border-b border-outline-variant/30 flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-mono font-bold uppercase tracking-wider text-outline">
              STATE SURVEILLANCE PROFILE
            </span>
            <span
              className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider border ${
                isUnavailable
                  ? 'bg-slate-100 text-slate-700 border-slate-300'
                  : 'bg-primary-container/20 text-primary border-primary/20'
              }`}
            >
              {isUnavailable ? 'UNREPORTED' : 'ACTIVE CYCLE'}
            </span>
          </div>
          <h3 className="text-lg lg:text-xl font-bold text-on-surface mt-1">
            {state.state || state.name}
          </h3>
        </div>

        <button
          onClick={onClose}
          className="p-1.5 rounded-lg text-outline hover:text-on-surface hover:bg-surface-container transition-colors"
          title="Close details"
          aria-label="Close details"
        >
          <X size={16} />
        </button>
      </div>

      {/* Scrollable Content Area */}
      <div className="flex-1 overflow-y-auto p-4 space-y-5">
        {isUnavailable ? (
          <div className="p-4 rounded-xl bg-surface-container-low border border-outline-variant/30 text-center space-y-2">
            <Activity size={24} className="text-outline mx-auto" />
            <h4 className="text-xs font-bold text-on-surface">
              No Surveillance Submissions
            </h4>
            <p className="text-[11px] text-outline leading-relaxed">
              No state-level surveillance records were submitted for {state.state || state.name} in the active reporting period.
            </p>
            {state.consanguinity_rate != null && (
              <div className="pt-2 border-t border-outline-variant/20 text-xs">
                <span className="text-outline">Regional Consanguinity (NFHS-5): </span>
                <span className="font-mono font-bold text-secondary">
                  {state.consanguinity_rate}%
                </span>
              </div>
            )}
          </div>
        ) : (
          <>
            {/* Primary Metrics Grid */}
            <div className="grid grid-cols-2 gap-3">
              <div className="p-3 rounded-xl bg-surface-container-low border border-outline-variant/30">
                <span className="text-[10px] font-bold uppercase tracking-wider text-outline block">
                  Estimated Cases
                </span>
                <div className="text-xl font-bold font-mono text-primary mt-0.5">
                  {state.cases != null ? state.cases.toLocaleString('en-IN') : '—'}
                </div>
                <span className="text-[10px] text-outline">Model-derived</span>
              </div>

              <div className="p-3 rounded-xl bg-surface-container-low border border-outline-variant/30">
                <span className="text-[10px] font-bold uppercase tracking-wider text-outline block">
                  Confirmed Cases
                </span>
                <div className="text-xl font-bold font-mono text-secondary mt-0.5">
                  {state.confirmed != null ? state.confirmed.toLocaleString('en-IN') : '—'}
                </div>
                <span className="text-[10px] text-outline">Molecular verification</span>
              </div>

              <div className="p-3 rounded-xl bg-surface-container-low border border-outline-variant/30">
                <span className="text-[10px] font-bold uppercase tracking-wider text-outline block">
                  Access Deficit Ratio
                </span>
                <div className="text-xl font-bold font-mono text-on-surface mt-0.5">
                  {state.access_gap_score != null ? `${state.access_gap_score}:1` : '—'}
                </div>
                <span
                  className={`text-[10px] font-bold uppercase tracking-wider ${
                    state.gap_label === 'critical'
                      ? 'text-red-700'
                      : state.gap_label === 'high'
                      ? 'text-amber-700'
                      : 'text-emerald-700'
                  }`}
                >
                  {state.gap_label || 'Standard'} Deficit
                </span>
              </div>

              <div className="p-3 rounded-xl bg-surface-container-low border border-outline-variant/30">
                <span className="text-[10px] font-bold uppercase tracking-wider text-outline block">
                  Consanguinity Rate
                </span>
                <div className="text-xl font-bold font-mono text-on-surface mt-0.5">
                  {state.consanguinity_rate != null ? `${state.consanguinity_rate}%` : '—'}
                </div>
                <span className="text-[10px] text-outline">NFHS-5 Survey</span>
              </div>
            </div>

            {/* Disease Distribution Breakdown */}
            {diseaseEntries.length > 0 && (
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-on-surface uppercase tracking-wider">
                    Disease Distribution
                  </span>
                  <span className="text-[10px] font-mono text-outline">
                    {diseaseEntries.length} mapped loci
                  </span>
                </div>

                <div className="space-y-2 p-3 rounded-xl bg-surface-container-low/60 border border-outline-variant/30">
                  {diseaseEntries.map(([diseaseId, count]) => {
                    const pct = totalDiseaseCases ? count / totalDiseaseCases : 0
                    return (
                      <div key={diseaseId} className="space-y-1">
                        <div className="flex items-center justify-between text-xs">
                          <span className="font-mono text-on-surface font-semibold">
                            {diseaseId}
                          </span>
                          <span className="font-mono font-bold text-primary">
                            {count.toLocaleString('en-IN')} cases ({(pct * 100).toFixed(0)}%)
                          </span>
                        </div>
                        <ScoreBar score={pct} showPercentage={false} size="sm" />
                      </div>
                    )
                  })}
                </div>
              </div>
            )}

            {/* Clinical Infrastructure & Workforce */}
            <div className="space-y-2">
              <span className="text-xs font-bold text-on-surface uppercase tracking-wider block">
                Clinical Access Infrastructure
              </span>

              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="p-2.5 rounded-lg bg-surface-container-low border border-outline-variant/30 flex items-center justify-between">
                  <div className="flex items-center gap-1.5 text-on-surface-variant">
                    <Stethoscope size={14} className="text-primary" />
                    <span>Specialists</span>
                  </div>
                  <span className="font-mono font-bold text-on-surface">
                    {state.specialists ?? 0}
                  </span>
                </div>

                <div className="p-2.5 rounded-lg bg-surface-container-low border border-outline-variant/30 flex items-center justify-between">
                  <div className="flex items-center gap-1.5 text-on-surface-variant">
                    <TestTube size={14} className="text-secondary" />
                    <span>NABL Labs</span>
                  </div>
                  <span className="font-mono font-bold text-on-surface">
                    {state.labs ?? 0}
                  </span>
                </div>

                <div className="p-2.5 rounded-lg bg-surface-container-low border border-outline-variant/30 flex items-center justify-between">
                  <div className="flex items-center gap-1.5 text-on-surface-variant">
                    <Users size={14} className="text-outline" />
                    <span>ASHA Reports</span>
                  </div>
                  <span className="font-mono font-bold text-on-surface">
                    {state.asha_reports ?? 0}
                  </span>
                </div>

                <div className="p-2.5 rounded-lg bg-surface-container-low border border-outline-variant/30 flex items-center justify-between">
                  <div className="flex items-center gap-1.5 text-on-surface-variant">
                    <AlertTriangle size={14} className="text-amber-700" />
                    <span>Red-Flagged</span>
                  </div>
                  <span className="font-mono font-bold text-amber-800">
                    {state.red_flagged ?? 0}
                  </span>
                </div>
              </div>
            </div>

            {/* Quick Action to Table */}
            {onViewInTable && (
              <button
                onClick={() => onViewInTable(state.state || state.name)}
                className="w-full py-2 px-3 rounded-lg bg-surface-container hover:bg-surface-container-high text-xs font-semibold text-primary transition-colors flex items-center justify-center gap-1.5"
              >
                <span>Highlight in Surveillance Table</span>
                <ArrowRight size={13} />
              </button>
            )}
          </>
        )}
      </div>

      {/* Footer Disclosure */}
      <div className="p-2.5 bg-surface-container-low/60 border-t border-outline-variant/30 text-[10px] text-outline text-center italic">
        Model-derived estimates based on KG prevalence & NFHS-5 data
      </div>
    </div>
  )
}
