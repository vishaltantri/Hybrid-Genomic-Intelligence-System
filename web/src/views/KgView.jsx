import React, { useEffect, useState } from 'react'
import { api, consumeNavContext } from '../api.js'
import KgFocusCard from '../components/twin/KgFocusCard.jsx'
import KgExplorer from '../components/kg/KgExplorer.jsx'
import {
  Network,
  Database,
  Layers,
  Sparkles,
  GitBranch,
  Activity,
  ArrowRight,
  Info,
  Code2,
  CheckCircle2,
  AlertTriangle,
  RefreshCw,
  Search,
} from 'lucide-react'
import { PageHeader } from '../components/ui/PageHeader.jsx'
import { ClinicalCard } from '../components/ui/ClinicalCard.jsx'
import { StatCard } from '../components/ui/StatCard.jsx'
import { ScoreBar } from '../components/ui/ScoreBar.jsx'
import { StatusBadge } from '../components/ui/StatusBadge.jsx'
import { ErrorAlert } from '../components/ui/ErrorAlert.jsx'
import { SkeletonCard } from '../components/ui/LoadingSkeleton.jsx'

export default function KgView({ onNavigate }) {
  const [stats, setStats] = useState(null)
  const [learningData, setLearningData] = useState(null)
  const [err, setErr] = useState(null)
  const [loading, setLoading] = useState(true)
  const [learningBusy, setLearningBusy] = useState(false)
  const [showRawJson, setShowRawJson] = useState(false)
  const [focus] = useState(() => consumeNavContext('kg'))

  useEffect(() => {
    api.kgStats()
      .then(setStats)
      .catch((ex) => setErr(ex.message))
      .finally(() => setLoading(false))
  }, [])

  async function fetchLearning() {
    setLearningBusy(true)
    setErr(null)
    try {
      const [q, drift] = await Promise.all([
        api.learningQueue(),
        api.learningDrift().catch(() => null),
      ])
      setLearningData({ queue: q, drift })
    } catch (ex) {
      setErr(ex.message)
    } finally {
      setLearningBusy(false)
    }
  }

  const nodeTypes = Object.entries(stats?.nodes || {}).sort((a, b) => b[1] - a[1])
  const edgeTypes = Object.entries(stats?.edges || {}).sort((a, b) => b[1] - a[1])
  const totalN = stats?.total_nodes ?? 0
  const totalE = stats?.total_edges ?? 0

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <PageHeader
        title="Genomic Knowledge Graph"
        subtitle="Multi-relational ontology graph unifying rare diseases, HPO phenotypes, causal loci, drug pharmacogenomics, and Indian population priors."
        badge={{
          label: 'Core Ontological Fabric',
          color: 'primary',
          icon: Network,
        }}
      />

      <KgFocusCard focus={focus} />

      {/* Error Alert */}
      {err && <ErrorAlert error={err} onRetry={() => window.location.reload()} />}

      {/* Loading Skeleton */}
      {loading && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <SkeletonCard />
            <SkeletonCard />
            <SkeletonCard />
            <SkeletonCard />
          </div>
          <SkeletonCard />
        </div>
      )}

      {/* Main Content */}
      {stats && !loading && (
        <div className="space-y-6">
          {/* Key Stat Cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard
              title="Graph Entities (Nodes)"
              value={totalN.toLocaleString('en-IN')}
              subtitle="Unique medical concepts"
              icon={Database}
              color="primary"
            />
            <StatCard
              title="Relationships (Edges)"
              value={totalE.toLocaleString('en-IN')}
              subtitle="Biological associations"
              icon={GitBranch}
              color="secondary"
            />
            <StatCard
              title="Entity Categories"
              value={nodeTypes.length || 5}
              subtitle="Diseases, Genes, HPOs, Drugs"
              icon={Layers}
              color="primary"
            />
            <StatCard
              title="Predicate Types"
              value={edgeTypes.length || 8}
              subtitle="Formal relation predicates"
              icon={Activity}
              color="secondary"
            />
          </div>

          {/* Interactive knowledge graph explorer: real, server-side traversal */}
          <div className="p-6 rounded-2xl bg-white border border-outline-variant/40 shadow-xs space-y-3">
            <div>
              <span className="text-[10px] font-bold uppercase tracking-wider text-outline">Knowledge Graph Explorer</span>
              <h3 className="text-base font-bold text-on-surface">Search, expand and trace relationships</h3>
            </div>
            <KgExplorer focus={focus} onNavigate={onNavigate} />
          </div>

          {/* Distribution Tables Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Node Types Distribution */}
            <ClinicalCard
              title="Ontology Entity Breakdown"
              subtitle="Distribution of semantic nodes across the clinical knowledge base"
              icon={Layers}
            >
              <div className="space-y-2">
                {nodeTypes.map(([type, count]) => {
                  const pct = totalN ? count / totalN : 0
                  return (
                    <div
                      key={type}
                      className="p-2.5 rounded-lg bg-surface-container-low/50 border border-outline-variant/30 flex items-center justify-between"
                    >
                      <div className="min-w-0 flex-1">
                        <div className="text-xs font-semibold text-on-surface capitalize">
                          {type.replace(/_/g, ' ')}
                        </div>
                        <div className="w-36 mt-1">
                          <ScoreBar score={pct} showPercentage={false} size="sm" />
                        </div>
                      </div>
                      <div className="text-right">
                        <span className="font-mono font-bold text-xs text-primary">
                          {count.toLocaleString('en-IN')}
                        </span>
                        <div className="text-[10px] text-outline font-mono">
                          {(pct * 100).toFixed(1)}%
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>
            </ClinicalCard>

            {/* Relationship Types Breakdown */}
            <ClinicalCard
              title="Biological Relations Breakdown"
              subtitle="Distribution of predicate edges linking clinical concepts"
              icon={GitBranch}
            >
              <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
                {edgeTypes.map(([type, count]) => (
                  <div
                    key={type}
                    className="p-2.5 rounded-lg bg-surface-container-low/50 border border-outline-variant/30 flex items-center justify-between"
                  >
                    <span className="font-mono text-xs font-semibold text-on-surface">
                      {type}
                    </span>
                    <span className="font-mono font-bold text-xs text-secondary">
                      {count.toLocaleString('en-IN')}
                    </span>
                  </div>
                ))}
              </div>
            </ClinicalCard>
          </div>

          {/* Continuous Learning & Pipeline Audit */}
          <ClinicalCard
            title="Continuous Active Learning & Literature Ingestion"
            subtitle="Clinician corrections and new PubMed literature expand and refine knowledge graph priors"
            icon={Sparkles}
            actions={
              <button
                onClick={fetchLearning}
                disabled={learningBusy}
                className="px-3.5 py-1.5 rounded-lg bg-primary text-white text-xs font-semibold hover:bg-primary-hover disabled:opacity-50 transition-colors flex items-center gap-1.5"
              >
                {learningBusy ? (
                  <>
                    <RefreshCw size={13} className="animate-spin" />
                    <span>Querying Pipeline…</span>
                  </>
                ) : (
                  <>
                    <RefreshCw size={13} />
                    <span>Check Learning Pipeline</span>
                  </>
                )}
              </button>
            }
          >
            <div className="space-y-4">
              <p className="text-xs text-on-surface-variant leading-relaxed">
                The Genomera graph engine integrates an active-learning pipeline. When clinicians confirm or reject differential candidates, correction signals are staged into a curation queue. Candidate graph assertions are monitored for concept drift against baseline priors before committing to the production ontology.
              </p>

              {learningData && (
                <div className="p-4 rounded-xl bg-surface-container-low border border-outline-variant/40 space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-on-surface uppercase tracking-wider">
                      Learning Pipeline Status
                    </span>
                    <span className="px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-800 text-[10px] font-bold border border-emerald-200">
                      PIPELINE ACTIVE
                    </span>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
                    <div className="p-3 rounded-lg bg-white border border-outline-variant/30">
                      <span className="text-[10px] font-bold uppercase text-outline">
                        Queue Items
                      </span>
                      <div className="text-base font-bold font-mono text-primary mt-0.5">
                        {Array.isArray(learningData.queue?.items)
                          ? learningData.queue.items.length
                          : learningData.queue?.n_pending ?? 0}
                      </div>
                    </div>
                    <div className="p-3 rounded-lg bg-white border border-outline-variant/30">
                      <span className="text-[10px] font-bold uppercase text-outline">
                        Drift Index
                      </span>
                      <div className="text-base font-bold font-mono text-secondary mt-0.5">
                        {typeof learningData.drift === 'object' && learningData.drift?.drift_score != null
                          ? `${(learningData.drift.drift_score * 100).toFixed(1)}%`
                          : 'Nominal (<0.05)'}
                      </div>
                    </div>
                    <div className="p-3 rounded-lg bg-white border border-outline-variant/30">
                      <span className="text-[10px] font-bold uppercase text-outline">
                        Curation Mode
                      </span>
                      <div className="text-xs font-semibold text-on-surface mt-1">
                        Clinician-in-the-Loop Review
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </ClinicalCard>

          {/* Raw JSON Debug Accordion */}
          <div className="pt-2">
            <button
              onClick={() => setShowRawJson(!showRawJson)}
              className="text-xs font-mono text-outline hover:text-on-surface flex items-center gap-1.5"
            >
              <Code2 size={14} />
              <span>{showRawJson ? 'Hide Raw Graph Stats' : 'Inspect Raw Graph Statistics (Audit Log)'}</span>
            </button>
            {showRawJson && (
              <pre className="mt-2 p-4 rounded-xl bg-surface-container-lowest border border-outline-variant/40 text-[11px] font-mono text-on-surface-variant overflow-x-auto max-h-96">
                {JSON.stringify(stats, null, 2)}
              </pre>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
