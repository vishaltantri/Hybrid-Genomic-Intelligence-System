import React, { useEffect, useState } from 'react'
import { CheckCircle2, Loader2, Circle } from 'lucide-react'
import GenomeView from './GenomeView.jsx'
import { prefersReducedMotion } from './webgl.js'
import { fmt } from '../twin/TwinSections.jsx'

/**
 * Stage player. While the request is in flight only "Applying scenario" is shown as active and the rest wait on the
 * server (no percentage). When the response arrives, the stages that the server actually executed are revealed in
 * order with their measured durations. Nothing here is a fake progress bar.
 */
export function StagePlayer({ computing, result }) {
  const stages = result?.stages || [
    { id: 'apply', label: 'Applying scenario' },
    { id: 'genomic', label: 'Recomputing variant and genomic relevance' },
    { id: 'phenotype', label: 'Recomputing phenotype relevance and diagnosis' },
    { id: 'compare', label: 'Comparing scenario Twin with baseline' },
  ]
  const [shown, setShown] = useState(0)
  useEffect(() => {
    if (!result) {
      setShown(0)
      return undefined
    }
    if (prefersReducedMotion()) {
      setShown(stages.length)
      return undefined
    }
    setShown(0)
    let i = 0
    const id = setInterval(() => {
      i += 1
      setShown(i)
      if (i >= stages.length) clearInterval(id)
    }, 380)
    return () => clearInterval(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [result])
  return (
    <ol className="space-y-1.5" data-testid="stage-player" aria-live="polite">
      <li className="text-[10px] uppercase tracking-wider text-outline font-semibold">Current Twin</li>
      {stages.map((s, i) => {
        const done = result && i < shown
        const active = computing ? i === 0 : result && i === shown
        return (
          <li key={s.id} data-testid={`stage-${s.id}`} data-state={done ? 'done' : active ? 'active' : 'pending'}
            className={`flex items-start gap-2 text-xs transition-opacity duration-300 ${done || active ? 'opacity-100' : 'opacity-45'}`}>
            {done ? <CheckCircle2 size={14} className="text-secondary mt-0.5" /> : active ? <Loader2 size={14} className="animate-spin text-primary mt-0.5" /> : <Circle size={14} className="text-outline mt-0.5" />}
            <span>
              <span className="font-semibold text-on-surface">{s.label}</span>
              {done && s.detail && <span className="block text-[11px] text-on-surface-variant">{s.detail}{s.ms != null ? ` · ${s.ms} ms (server)` : ''}</span>}
              {computing && i > 0 && <span className="block text-[11px] text-outline">waiting for server</span>}
            </span>
          </li>
        )
      })}
      <li className="text-[10px] uppercase tracking-wider text-outline font-semibold">{result && shown >= stages.length ? 'Scenario Twin ready' : 'Scenario Twin'}</li>
    </ol>
  )
}

function chromosomesFor(twin, ranking) {
  const byId = new Map(ranking.map((v) => [v.variant_id, v]))
  return twin.anatomy.chromosomes.map((c) => ({
    ...c,
    variants: c.variants.filter((v) => byId.has(v.variant_id)).map((v) => ({ ...v, classification: byId.get(v.variant_id).classification })),
  }))
}

function Side({ title, tone, children }) {
  return (
    <div className={`rounded-xl border p-3 space-y-3 ${tone === 'scenario' ? 'border-primary/40 bg-primary/[0.03]' : 'border-outline-variant/50 bg-white'}`}>
      <div className="text-[10px] uppercase tracking-wider font-bold text-primary">{title}</div>
      {children}
    </div>
  )
}

export default function ScenarioCompare({ twin, result }) {
  if (!result) return null
  const b = result.baseline
  const s = result.scenario
  const hasGenome = !!b.variant_ranking
  const impact = new Map((result.system_impact || []).map((i) => [i.system, i]))
  const systems = twin.anatomy.systems.filter((x) => x.has_case_data || impact.has(x.id))
  const excluded = hasGenome ? b.variant_ranking.filter((v) => !s.variant_ranking.some((x) => x.variant_id === v.variant_id)).map((v) => v.variant_id) : []
  const changedRows = result.comparison.filter((r) => fmt(r.baseline) !== fmt(r.scenario))
  const dx = (side) => (side.differential || []).slice(0, 4)
  const rankIn = (list, id) => (list.find((d) => d.disease_id === id) || {}).rank

  return (
    <div className="space-y-3" data-testid="scenario-compare">
      <div className="text-xs font-bold text-on-surface">Simulation mode — baseline vs scenario: <span className="text-primary">{result.name}</span></div>
      <div className="grid md:grid-cols-2 gap-3">
        <Side title="Baseline — patient's current Twin">
          {hasGenome && <GenomeView compact chromosomes={chromosomesFor(twin, b.variant_ranking)} />}
          {systems.length > 0 && (
            <div className="flex flex-wrap gap-1" aria-label="Body systems with case data">
              {systems.map((x) => <span key={x.id} className="px-2 py-0.5 rounded-full bg-surface-container text-[10px]">{x.label}</span>)}
            </div>
          )}
          {b.differential && (
            <ol className="text-xs space-y-0.5" data-testid="compare-baseline-dx">
              {dx(b).map((d) => <li key={d.disease_id}>{d.rank}. {d.disease_name} <span className="font-mono text-outline">{(d.probability * 100).toFixed(1)}% · P/LP {d.pathogenic_or_likely_variants}</span></li>)}
            </ol>
          )}
        </Side>
        <Side title={`Scenario — ${result.name}`} tone="scenario">
          {hasGenome && <GenomeView compact chromosomes={chromosomesFor(twin, b.variant_ranking.map((v) => s.variant_ranking.find((x) => x.variant_id === v.variant_id) || v))} ghostIds={excluded} />}
          {systems.length > 0 && (
            <div className="flex flex-wrap gap-1" aria-label="Body systems, changed ones outlined">
              {systems.map((x) => {
                const im = impact.get(x.id)
                return (
                  <span key={x.id} data-testid={`impact-${x.id}`} data-changed={!!im}
                    className={`px-2 py-0.5 rounded-full text-[10px] ${im ? 'border-2 border-primary bg-primary/10 font-semibold' : 'bg-surface-container'}`}>
                    {x.label}{im ? ` · variants ${im.variants_before}→${im.variants_after}${im.phenotypes_before !== im.phenotypes_after ? `, phenotypes ${im.phenotypes_before}→${im.phenotypes_after}` : ''}` : ''}
                  </span>
                )
              })}
            </div>
          )}
          {s.differential && (
            <ol className="text-xs space-y-0.5" data-testid="compare-scenario-dx">
              {dx(s).map((d) => {
                const before = rankIn(b.differential || [], d.disease_id)
                return <li key={d.disease_id}>{d.rank}. {d.disease_name} <span className="font-mono text-outline">{(d.probability * 100).toFixed(1)}% · P/LP {d.pathogenic_or_likely_variants}</span>{before && before !== d.rank ? <span className="text-primary font-semibold"> (was {before})</span> : null}</li>
              })}
            </ol>
          )}
        </Side>
      </div>
      <div className="rounded-xl border border-outline-variant/50 bg-white p-3" data-testid="compare-diff">
        <div className="text-[10px] uppercase tracking-wider font-bold text-outline mb-1">Differences computed by the backend</div>
        {changedRows.length ? (
          <table className="w-full text-xs"><tbody>
            {changedRows.map((r) => <tr key={r.label} className="border-t border-outline-variant/30"><td className="py-1 pr-3 text-on-surface-variant">{r.label}</td><td className="py-1 pr-3 font-mono">{fmt(r.baseline)}</td><td className="py-1 font-mono font-bold text-primary">→ {fmt(r.scenario)}</td></tr>)}
          </tbody></table>
        ) : <p className="text-xs text-on-surface-variant">No measured difference between baseline and scenario.</p>}
      </div>
    </div>
  )
}
