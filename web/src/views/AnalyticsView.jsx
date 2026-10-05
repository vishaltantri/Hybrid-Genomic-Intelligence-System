import React, { useCallback, useEffect, useState } from 'react'
import { Download, RefreshCw } from 'lucide-react'
import { api, downloadAnalytics } from '../api.js'

const METRICS = [
  ['total_cases', 'Total cases'], ['active_cases', 'Active cases'], ['completed_cases', 'Completed cases'],
  ['variants_in_analyses', 'Variants analysed'], ['variants_reviewed', 'Variants reviewed'], ['diagnosis_runs', 'Diagnosis runs'],
  ['pgx_analyses', 'PGx analyses'], ['reproductive_analyses', 'Reproductive analyses'],
  ['reports_generated', 'Reports generated'], ['pending_reviews', 'Pending reviews'],
]
const SERIES = [['cases', 'Cases created'], ['reports', 'Reports generated'], ['diagnoses', 'Diagnosis runs'], ['variant_reviews', 'Variant evidence saved'],
  ['referrals', 'ASHA referrals'], ['workflow_completions', 'Cases closed']]

function Card({ title, unit, exportKey, range, children, state, note }) {
  const [err, setErr] = useState(null)
  return (
    <section className="bg-white rounded-xl border border-outline-variant/40 p-4" aria-label={title}>
      <div className="flex items-start justify-between gap-2 mb-3">
        <div><h3 className="text-sm font-bold text-on-surface">{title}</h3>{unit && <div className="text-[11px] text-outline">{unit}</div>}</div>
        {exportKey && (
          <div className="flex gap-1">
            {['csv', 'json'].map((f) => (
              <button key={f} aria-label={`Export ${title} as ${f.toUpperCase()}`} onClick={() => downloadAnalytics(exportKey, f, range).then(() => setErr(null)).catch((e) => setErr(e.message))}
                className="text-[11px] px-2 py-1 rounded-md border border-outline-variant/50 text-primary hover:bg-surface-container flex items-center gap-1"><Download size={11} />{f.toUpperCase()}</button>
            ))}
          </div>
        )}
      </div>
      {err && <div role="alert" className="text-xs text-red-800 mb-2">{err}</div>}
      {state && state !== 'ok' ? <div data-testid="empty-state" className="py-6 text-center text-xs text-outline">{state}</div> : children}
      {note && <p className="text-[11px] text-outline mt-3 leading-snug">{note}</p>}
    </section>
  )
}

export function BarList({ rows, suppressed = 0, unit = 'count' }) {
  const max = Math.max(1, ...rows.map((r) => r.count))
  return (
    <div className="space-y-1.5" role="list">
      {rows.map((r) => (
        <div key={r.label} role="listitem" className="text-xs">
          <div className="flex justify-between"><span className="text-on-surface truncate pr-2">{r.label}</span><span className="text-on-surface-variant tabular-nums">{r.count}</span></div>
          <div className="h-2 rounded bg-surface-container"><div className="h-2 rounded bg-primary" style={{ width: `${(100 * r.count) / max}%` }} aria-hidden="true" /></div>
        </div>
      ))}
      {suppressed > 0 && <div className="text-[11px] text-outline">{suppressed} observation(s) in groups smaller than the privacy threshold are hidden.</div>}
      {rows.length === 0 && suppressed === 0 && <div className="text-xs text-outline">None recorded.</div>}
      <span className="sr-only">Unit: {unit}</span>
    </div>
  )
}

export function TrendChart({ points, title }) {
  const W = 320, H = 110, P = 18
  const max = Math.max(1, ...points.map((p) => p.count))
  const bw = (W - 2 * P) / Math.max(points.length, 1)
  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${title}: ${points.map((p) => `${p.bucket} ${p.count}`).join(', ')}`} className="w-full">
      <line x1={P} y1={H - P} x2={W - P} y2={H - P} stroke="currentColor" className="text-outline-variant" />
      {points.map((p, i) => {
        const h = ((H - 2 * P) * p.count) / max
        return <g key={p.bucket}><rect x={P + i * bw + 2} y={H - P - h} width={Math.max(bw - 4, 2)} height={h} rx="2" className="fill-primary" /><title>{`${p.bucket}: ${p.count}`}</title></g>
      })}
      {points.length > 0 && <><text x={P} y={H - 4} fontSize="8" className="fill-outline">{points[0].bucket}</text><text x={W - P} y={H - 4} fontSize="8" textAnchor="end" className="fill-outline">{points[points.length - 1].bucket}</text></>}
    </svg>
  )
}

export default function AnalyticsView() {
  const [range, setRange] = useState({ from: '', to: '' })
  const [metric, setMetric] = useState('cases')
  const [interval, setIntervalV] = useState('day')
  const [data, setData] = useState({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    const p = { from: range.from, to: range.to }
    try {
      const [overview, ts, variants, phenotypes, diagnoses, pgx, repro] = await Promise.all([
        api.analytics('overview', p), api.analytics('timeseries', { ...p, metric, interval }), api.analytics('variants', p),
        api.analytics('phenotypes', p), api.analytics('diagnoses', p), api.analytics('pgx', p), api.analytics('reproductive', p)])
      setData({ overview, ts, variants, phenotypes, diagnoses, pgx, repro })
    } catch (e) { setError(e.message); setData({}) } finally { setLoading(false) }
  }, [range, metric, interval])
  useEffect(() => { load() }, [load])

  const d = data
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div><h1 className="text-xl font-bold text-on-surface">Analytics</h1>
          <p className="text-xs text-outline">Aggregates computed by the backend from stored records. No patient identifiers are shown or exported.</p></div>
        <div className="flex flex-wrap items-end gap-2 text-xs">
          <label className="flex flex-col">From<input type="date" aria-label="From date" value={range.from} onChange={(e) => setRange({ ...range, from: e.target.value })} className="border border-outline-variant/60 rounded-md px-2 py-1" /></label>
          <label className="flex flex-col">To<input type="date" aria-label="To date" value={range.to} onChange={(e) => setRange({ ...range, to: e.target.value })} className="border border-outline-variant/60 rounded-md px-2 py-1" /></label>
          <button onClick={load} aria-label="Refresh analytics" className="p-2 rounded-md border border-outline-variant/60 text-primary hover:bg-surface-container"><RefreshCw size={14} /></button>
        </div>
      </div>
      {error && <div role="alert" className="rounded-lg border border-red-200 bg-red-50 text-red-800 text-xs px-3 py-2">{error}</div>}
      {loading && <div role="status" className="text-xs text-outline">Loading analytics…</div>}

      {d.overview && (
        <Card title="Summary" unit="counts within the selected range" exportKey="overview" range={range}>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            {METRICS.map(([k, label]) => (
              <div key={k} className="rounded-lg bg-surface-container-low p-3"><div className="text-[11px] text-outline">{label}</div><div data-testid={`metric-${k}`} className="text-xl font-bold text-primary tabular-nums">{d.overview.metrics[k]}</div></div>
            ))}
          </div>
          <details className="mt-3 text-[11px] text-outline"><summary className="cursor-pointer">How these are defined</summary>
            <ul className="mt-1 space-y-0.5">{Object.entries(d.overview.definitions).map(([k, v]) => <li key={k}><b>{k.replace(/_/g, ' ')}</b>: {v}</li>)}</ul></details>
        </Card>
      )}

      {d.ts && (
        <Card title={d.ts.title} unit={`events per ${d.ts.interval}`} exportKey={`timeseries:${metric}`} range={range} state={d.ts.points.length ? 'ok' : d.ts.state} note={d.ts.state !== 'ok' && d.ts.points.length ? d.ts.note : null}>
          <div className="flex gap-2 mb-2 text-xs">
            <select aria-label="Time series metric" value={metric} onChange={(e) => setMetric(e.target.value)} className="border border-outline-variant/60 rounded-md px-2 py-1">{SERIES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
            <select aria-label="Interval" value={interval} onChange={(e) => setIntervalV(e.target.value)} className="border border-outline-variant/60 rounded-md px-2 py-1">{['day', 'week', 'month'].map((i) => <option key={i}>{i}</option>)}</select>
          </div>
          <TrendChart points={d.ts.points} title={d.ts.title} />
        </Card>
      )}
      {!d.ts && !loading && !error && null}

      <div className="grid md:grid-cols-2 gap-4">
        {d.variants && (<>
          <Card title="ACMG classification" unit="variants" exportKey="variants" range={range} state={d.variants.state} note={d.variants.note}><BarList rows={d.variants.acmg} suppressed={d.variants.acmg_suppressed} unit="variants" /></Card>
          <Card title="Variant review status" unit="variants" state={d.variants.state}><BarList rows={[{ label: 'Reviewed', count: d.variants.reviewed }, { label: 'Not reviewed', count: d.variants.unreviewed }]} unit="variants" /></Card>
          <Card title="Top genes" unit="variants" state={d.variants.state}><BarList rows={d.variants.genes} suppressed={d.variants.genes_suppressed} unit="variants" /></Card>
          <Card title="Associated diseases" unit="variants" state={d.variants.state}><BarList rows={d.variants.diseases} suppressed={d.variants.diseases_suppressed} unit="variants" /></Card>
        </>)}
        {d.phenotypes && (
          <Card title="Phenotype (HPO) frequency" unit="cases" exportKey="phenotypes" range={range} state={d.phenotypes.state} note={d.phenotypes.note}>
            <div className="text-xs text-on-surface-variant mb-2">Coverage: {d.phenotypes.coverage_pct === null ? 'Not available' : `${d.phenotypes.coverage_pct}% of cases (${d.phenotypes.cases_with_phenotypes} of ${d.phenotypes.cases})`}</div>
            <BarList rows={d.phenotypes.frequencies} suppressed={d.phenotypes.frequencies_suppressed} unit="cases" />
            <div className="text-[11px] text-outline mt-2">Co-occurrence: {d.phenotypes.cooccurrence ? `${d.phenotypes.cooccurrence.length} frequent pair(s)` : d.phenotypes.cooccurrence_state}</div>
          </Card>
        )}
        {d.diagnoses && (<>
          <Card title="Model score: top-ranked disease" unit="cases (latest run per case)" exportKey="diagnoses" range={range} state={d.diagnoses.state} note={d.diagnoses.note}>
            <BarList rows={d.diagnoses.top_diagnosis} suppressed={d.diagnoses.top_diagnosis_suppressed} unit="cases" />
            <div className="text-[11px] text-outline mt-2">Mean top-1 model score: {d.diagnoses.model_score.mean_top1 ?? 'Not available'} (n={d.diagnoses.model_score.n})</div>
          </Card>
          <Card title="Clinical diagnosis status" unit="cases">
            <BarList rows={[{ label: 'No diagnosis run', count: d.diagnoses.unresolved.no_diagnosis_run }, { label: 'Model run, no final report', count: d.diagnoses.unresolved.diagnosed_no_final_report }, { label: 'Final report issued', count: d.diagnoses.unresolved.with_final_report }]} unit="cases" />
            <p className="text-[11px] text-outline mt-2">A clinical diagnosis is only the clinician&apos;s finalized report, never the model score.</p>
          </Card>
        </>)}
        {d.pgx && (
          <Card title="Pharmacogenomics" unit="analyses and variants" exportKey="pgx" range={range} state={d.pgx.state} note={d.pgx.note}>
            <BarList rows={Object.entries(d.pgx.analyses_run).map(([label, count]) => ({ label, count }))} unit="analyses" />
            <div className="text-xs text-on-surface-variant my-2">PGx-relevant variants: {d.pgx.pgx_relevant_variants}</div>
            <BarList rows={d.pgx.genes} suppressed={d.pgx.genes_suppressed} unit="variants" />
          </Card>
        )}
        {d.repro && (
          <Card title="Reproductive analyses" unit="analyses" exportKey="reproductive" range={range} state={d.repro.state} note={d.repro.note}>
            <div className="text-xs text-on-surface-variant mb-2">Analyses run: {d.repro.analyses_run}</div>
            <BarList rows={d.repro.risk_bands} suppressed={d.repro.risk_bands_suppressed} unit="analyses" />
          </Card>
        )}
      </div>
    </div>
  )
}
