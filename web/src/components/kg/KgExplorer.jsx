import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Search, Maximize2, RotateCcw, ZoomIn, ZoomOut, Expand, Route, Loader2, UserRound, Bot } from 'lucide-react'
import { api, setNavContext } from '../../api.js'

export const TYPE_COLOR = {
  Disease: '#00629E', Gene: '#1B6B50', Hpo: '#0284C7', Drug: '#D97706', Variant: '#B45309', Patient: '#0B3C5D',
  FamilyMember: '#7C3AED', Publication: '#475569', Ethnicity: '#9333EA', State: '#64748B', Lab: '#94A3B8',
  IndianSynonym: '#38BDF8', AF: '#A3A3A3', Doctor: '#94A3B8',
}
const colorOf = (t) => TYPE_COLOR[t] || '#64748B'
const typeName = (t) => (t === 'Hpo' ? 'Phenotype (HPO)' : t === 'FamilyMember' ? 'Family member' : t)

/** Deterministic force layout (no dependency). Runs once per graph change on <=300 nodes. */
export function layout(nodes, edges, center) {
  const pos = {}
  const n = nodes.length
  nodes.forEach((nd, i) => {
    const ring = nd.key === center ? 0 : 1 + (nd.depth || 1) * 0.6
    const a = (i / Math.max(n, 1)) * Math.PI * 2
    pos[nd.key] = { x: Math.cos(a) * 140 * ring, y: Math.sin(a) * 140 * ring, vx: 0, vy: 0 }
  })
  const links = edges.filter((e) => pos[e.source] && pos[e.target])
  for (let it = 0; it < 220; it++) {
    const cool = 1 - it / 220
    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        const a = pos[nodes[i].key], b = pos[nodes[j].key]
        let dx = a.x - b.x, dy = a.y - b.y
        let d2 = dx * dx + dy * dy || 0.01
        const f = 2600 / d2
        const d = Math.sqrt(d2)
        dx /= d; dy /= d
        a.vx += dx * f; a.vy += dy * f; b.vx -= dx * f; b.vy -= dy * f
      }
    }
    for (const e of links) {
      const a = pos[e.source], b = pos[e.target]
      const dx = b.x - a.x, dy = b.y - a.y
      const d = Math.sqrt(dx * dx + dy * dy) || 0.01
      const f = (d - 90) * 0.02
      a.vx += (dx / d) * f; a.vy += (dy / d) * f; b.vx -= (dx / d) * f; b.vy -= (dy / d) * f
    }
    for (const k in pos) {
      const p = pos[k]
      p.vx -= p.x * 0.004; p.vy -= p.y * 0.004
      p.x += Math.max(-20, Math.min(20, p.vx)) * cool; p.y += Math.max(-20, Math.min(20, p.vy)) * cool
      p.vx *= 0.6; p.vy *= 0.6
    }
  }
  return pos
}

const merge = (cur, add) => {
  const nodes = new Map(cur.nodes), edges = new Map(cur.edges)
  add.nodes.forEach((n) => { if (!nodes.has(n.key)) nodes.set(n.key, n) })
  add.edges.forEach((e) => edges.set(e.id, e))
  return { nodes, edges }
}

export default function KgExplorer({ focus, onNavigate }) {
  const [graph, setGraph] = useState({ nodes: new Map(), edges: new Map() })
  const [center, setCenter] = useState(null)
  const [mode, setMode] = useState('global')
  const [sel, setSel] = useState(null) // {kind, id}
  const [detail, setDetail] = useState(null)
  const [hidden, setHidden] = useState(new Set())
  const [view, setView] = useState({ x: 0, y: 0, k: 1 })
  const [q, setQ] = useState('')
  const [results, setResults] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [notice, setNotice] = useState(null)
  const [patients, setPatients] = useState([])
  const [pathTarget, setPathTarget] = useState('')
  const [pathHit, setPathHit] = useState(null)
  const [caseId, setCaseId] = useState('')
  const drag = useRef(null)
  const box = useRef(null)

  const nodes = useMemo(() => [...graph.nodes.values()], [graph])
  const edges = useMemo(() => [...graph.edges.values()], [graph])
  const pos = useMemo(() => layout(nodes, edges, center), [nodes, edges, center])
  const types = useMemo(() => [...new Set(nodes.map((n) => n.type))].sort(), [nodes])
  const visible = (n) => !hidden.has(n.type)
  const pathKeys = useMemo(() => new Set((pathHit?.nodes || []).map((n) => n.key)), [pathHit])
  const pathEdges = useMemo(() => new Set((pathHit?.edges || []).map((e) => e.id)), [pathHit])

  const fit = useCallback(() => {
    const ps = nodes.filter(visible).map((n) => pos[n.key]).filter(Boolean)
    if (!ps.length) { setView({ x: 0, y: 0, k: 1 }); return }
    const xs = ps.map((p) => p.x), ys = ps.map((p) => p.y)
    const w = Math.max(...xs) - Math.min(...xs) + 120, h = Math.max(...ys) - Math.min(...ys) + 120
    const k = Math.min(2, 560 / w, 380 / h)
    setView({ x: -((Math.max(...xs) + Math.min(...xs)) / 2) * k, y: -((Math.max(...ys) + Math.min(...ys)) / 2) * k, k })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes, pos, hidden])
  useEffect(() => { fit() }, [graph.nodes.size, mode]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { api.listPatients?.().then((p) => setPatients(Array.isArray(p) ? p : [])).catch(() => {}) }, [])

  const wrap = async (fn) => {
    setBusy(true); setErr(null); setNotice(null)
    try { return await fn() } catch (e) { setErr(e.message); return null } finally { setBusy(false) }
  }

  const loadNeighborhood = (key, depth = 1, replace = false) => wrap(async () => {
    const r = await api.kgNeighborhood({ key, depth, max_nodes: 60 })
    setGraph((g) => (replace ? merge({ nodes: new Map(), edges: new Map() }, r) : merge(g, r)))
    if (replace) { setCenter(key); setMode('global'); setPathHit(null) }
    if (r.truncated) setNotice(`Neighbourhood truncated at ${r.max_nodes} nodes. Narrow with the type filters or expand a specific node.`)
    return r
  })

  const select = async (kind, id) => {
    setSel({ kind, id })
    if (kind === 'node' && !id.startsWith('CaseVariant::') && !id.startsWith('FamilyMember::') && !id.startsWith('Publication::') && !id.startsWith('Patient::')) {
      try { setDetail(await api.kgNode(id)) } catch (e) { setDetail(null) }
    } else setDetail(null)
  }

  const doSearch = useCallback(async (text) => {
    if (text.trim().length < 2) { setResults(null); return }
    try { setResults(await api.kgSearch({ q: text.trim(), limit: 12 })) } catch (e) { setErr(e.message); setResults(null) }
  }, [])
  useEffect(() => { const t = setTimeout(() => doSearch(q), 300); return () => clearTimeout(t) }, [q, doSearch])

  const openCase = (pid) => wrap(async () => {
    const r = await api.kgCase(pid)
    setGraph(merge({ nodes: new Map(), edges: new Map() }, r))
    setCenter(`Patient::${pid}`); setMode('case'); setCaseId(pid); setPathHit(null); setSel(null)
    setNotice(r.notes.join(' '))
  })

  const reset = () => { setGraph({ nodes: new Map(), edges: new Map() }); setCenter(null); setSel(null); setDetail(null); setHidden(new Set()); setPathHit(null); setMode('global'); setErr(null); setNotice(null); setResults(null); setQ(''); setView({ x: 0, y: 0, k: 1 }) }

  const findPath = () => wrap(async () => {
    if (!sel || sel.kind !== 'node' || !pathTarget) return
    const r = await api.kgPath({ source: sel.id, target: pathTarget })
    setPathHit(r)
    if (r.status === 'found') setGraph((g) => merge(g, { nodes: r.paths[0].nodes, edges: r.paths[0].edges }))
    else setNotice(r.message)
  })

  // focus from other views (Variant Intelligence, Digital Twin)
  useEffect(() => {
    const gene = focus?.gene || focus?.genes?.[0]
    if (focus?.disease_id) loadNeighborhood(`Disease::${focus.disease_id}`, 1, true)
    else if (gene && /^[A-Za-z0-9-]+$/.test(gene)) loadNeighborhood(`Gene::${gene}`, 1, true)
    else if (focus?.patient_id) openCase(focus.patient_id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const onWheel = (e) => { e.preventDefault(); setView((v) => ({ ...v, k: Math.max(0.2, Math.min(4, v.k * (e.deltaY < 0 ? 1.12 : 0.89))) })) }
  const onDown = (e) => { drag.current = { x: e.clientX, y: e.clientY, vx: view.x, vy: view.y, moved: false } }
  const onMove = (e) => {
    const d = drag.current
    if (!d) return
    const dx = e.clientX - d.x, dy = e.clientY - d.y
    if (Math.abs(dx) + Math.abs(dy) > 3) d.moved = true
    setView((v) => ({ ...v, x: d.vx + dx, y: d.vy + dy }))
  }
  const onUp = () => { drag.current = null }

  const selNode = sel?.kind === 'node' ? graph.nodes.get(sel.id) : null
  const selEdge = sel?.kind === 'edge' ? graph.edges.get(sel.id) : null
  const nodeEdges = selNode ? edges.filter((e) => e.source === selNode.key || e.target === selNode.key) : []

  return (
    <div className="space-y-3" data-testid="kg-explorer">
      <div className="flex flex-wrap gap-2 items-start">
        <div className="relative flex-1 min-w-[220px]">
          <Search size={14} className="absolute left-2.5 top-2.5 text-outline" />
          <input aria-label="Search the knowledge graph" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search gene, disease, HPO term, drug, synonym…"
            className="w-full pl-8 pr-3 py-2 text-sm rounded-lg border border-outline-variant" />
          {results && (
            <div className="absolute z-20 mt-1 w-full max-h-64 overflow-auto rounded-lg border border-outline-variant bg-white shadow-lg" data-testid="kg-results">
              {results.results.length === 0 && <div className="px-3 py-2 text-xs text-on-surface-variant">No matching record in the knowledge graph.</div>}
              {results.results.map((r) => (
                <button key={r.key} onClick={() => { loadNeighborhood(r.key, 1, true); setResults(null); setQ(''); select('node', r.key) }}
                  className="w-full text-left px-3 py-1.5 text-xs hover:bg-primary/5 flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full" style={{ background: colorOf(r.type) }} />
                  <span className="font-semibold">{r.label}</span><span className="text-outline">{typeName(r.type)} · {r.id}</span>
                </button>
              ))}
            </div>
          )}
        </div>
        <select aria-label="Case graph patient" value={caseId} onChange={(e) => e.target.value && openCase(e.target.value)}
          className="text-xs rounded-lg border border-outline-variant px-2 py-2 max-w-[220px]">
          <option value="">View a case in the graph…</option>
          {patients.map((p) => <option key={p.patient_id} value={p.patient_id}>{p.patient_id}</option>)}
        </select>
        <button onClick={fit} title="Fit to view" className="p-2 rounded-lg border border-outline-variant"><Maximize2 size={14} /></button>
        <button onClick={() => setView((v) => ({ ...v, k: Math.min(4, v.k * 1.25) }))} title="Zoom in" className="p-2 rounded-lg border border-outline-variant"><ZoomIn size={14} /></button>
        <button onClick={() => setView((v) => ({ ...v, k: Math.max(0.2, v.k * 0.8) }))} title="Zoom out" className="p-2 rounded-lg border border-outline-variant"><ZoomOut size={14} /></button>
        <button onClick={reset} className="inline-flex items-center gap-1 px-3 py-2 rounded-lg border border-outline-variant text-xs font-semibold"><RotateCcw size={13} />Reset</button>
      </div>

      {err && <div role="alert" className="rounded-lg border border-red-200 bg-red-50 text-red-800 text-xs px-3 py-2">{err}</div>}
      {notice && <div className="rounded-lg border border-amber-200 bg-amber-50 text-amber-900 text-xs px-3 py-2">{notice}</div>}

      {types.length > 0 && (
        <div className="flex flex-wrap gap-1.5" data-testid="kg-filters">
          {types.map((t) => (
            <button key={t} onClick={() => setHidden((h) => { const n = new Set(h); n.has(t) ? n.delete(t) : n.add(t); return n })}
              className={`px-2.5 py-1 rounded-full text-[11px] font-semibold border flex items-center gap-1.5 ${hidden.has(t) ? 'opacity-40' : ''}`} style={{ borderColor: colorOf(t) }}>
              <span className="w-2 h-2 rounded-full" style={{ background: colorOf(t) }} />{typeName(t)}</button>
          ))}
        </div>
      )}

      <div className="grid lg:grid-cols-[1fr_320px] gap-4">
        <div ref={box} className="relative h-[420px] rounded-xl border border-outline-variant/40 bg-surface-container-lowest overflow-hidden touch-none"
          onWheel={onWheel} onMouseDown={onDown} onMouseMove={onMove} onMouseUp={onUp} onMouseLeave={onUp}>
          {nodes.length === 0 && (
            <div className="absolute inset-0 flex items-center justify-center text-xs text-on-surface-variant text-center px-6">
              {busy ? <Loader2 className="animate-spin" /> : 'Search for a gene, disease or phenotype to start exploring, or open a case from the selector. Nothing is drawn until you choose a starting point.'}
            </div>
          )}
          <svg viewBox="-300 -210 600 420" className="w-full h-full select-none" data-testid="kg-canvas">
            <g transform={`translate(${view.x} ${view.y}) scale(${view.k})`}>
              {edges.filter((e) => pos[e.source] && pos[e.target] && !hidden.has(graph.nodes.get(e.source)?.type) && !hidden.has(graph.nodes.get(e.target)?.type)).map((e) => {
                const a = pos[e.source], b = pos[e.target]
                const on = pathEdges.has(e.id) || sel?.id === e.id
                return (
                  <g key={e.id} onClick={(ev) => { ev.stopPropagation(); if (!drag.current?.moved) select('edge', e.id) }} data-testid="kg-edge" className="cursor-pointer">
                    <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="transparent" strokeWidth="8" />
                    <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={on ? '#00629E' : '#CBD5E1'} strokeWidth={on ? 2.5 : 1.2} />
                  </g>
                )
              })}
              {nodes.filter(visible).map((n) => {
                const p = pos[n.key]
                if (!p) return null
                const isSel = sel?.id === n.key
                const dim = pathHit && pathHit.status === 'found' && !pathKeys.has(n.key)
                return (
                  <g key={n.key} onClick={(ev) => { ev.stopPropagation(); if (!drag.current?.moved) select('node', n.key) }} data-testid="kg-node" data-key={n.key} className="cursor-pointer" opacity={dim ? 0.3 : 1}>
                    <circle cx={p.x} cy={p.y} r={n.key === center ? 14 : 10} fill={colorOf(n.type)} stroke={isSel ? '#001C37' : '#fff'} strokeWidth={isSel ? 3 : 1.5} />
                    {(view.k > 0.6 || isSel || n.key === center) && <text x={p.x} y={p.y + 22} fontSize="8" fontWeight="600" textAnchor="middle" fill="#0F172A">{String(n.label).slice(0, 26)}</text>}
                  </g>
                )
              })}
            </g>
          </svg>
          <div className="absolute bottom-2 left-2 text-[10px] text-outline">{nodes.length} nodes · {edges.length} edges · drag to pan, scroll to zoom</div>
        </div>

        <div className="rounded-xl bg-surface-container-low border border-outline-variant/40 p-3 space-y-2 text-xs" data-testid="kg-inspector">
          {!selNode && !selEdge && <div className="text-on-surface-variant">Select a node or an edge to inspect it.</div>}
          {selNode && (
            <>
              <div className="flex items-center justify-between">
                <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase text-white" style={{ background: colorOf(selNode.type) }}>{typeName(selNode.type)}</span>
                {selNode.case && <span className="text-[10px] text-primary font-semibold">This case</span>}
              </div>
              <h4 className="text-sm font-bold">{selNode.label}</h4>
              <div className="font-mono text-[11px] text-outline">{selNode.id}</div>
              {Object.entries(selNode.props || {}).filter(([, v]) => typeof v !== 'object').slice(0, 8).map(([k, v]) => (
                <div key={k}><span className="text-outline">{k}:</span> {String(v)}</div>
              ))}
              {detail && <div className="text-on-surface-variant">{detail.degree} relations in the graph{Object.keys(detail.degree_by_edge_type).length ? ': ' + Object.entries(detail.degree_by_edge_type).map(([k, v]) => `${k} ${v}`).join(', ') : ''}</div>}
              <div className="flex flex-wrap gap-1.5 pt-1">
                {!selNode.case && <button onClick={() => loadNeighborhood(selNode.key, 1)} className="inline-flex items-center gap-1 px-2 py-1 rounded border border-primary/40 text-primary font-semibold"><Expand size={12} />Expand</button>}
                {!selNode.case && <button onClick={() => loadNeighborhood(selNode.key, 2, true)} className="px-2 py-1 rounded border border-primary/40 text-primary font-semibold">Focus (2 hops)</button>}
                {selNode.type === 'Gene' && <button onClick={() => { setNavContext('variants', { gene: selNode.id }); onNavigate?.('variants') }} className="px-2 py-1 rounded border border-outline-variant font-semibold">Variants</button>}
                <button onClick={() => { setNavContext('ai-assistant', { graph_node: selNode.key, prompt: `Explain how ${selNode.label} relates to its neighbours in the knowledge graph.` }); onNavigate?.('ai-assistant') }}
                  className="inline-flex items-center gap-1 px-2 py-1 rounded border border-outline-variant font-semibold"><Bot size={12} />Ask AI</button>
              </div>
              <div className="pt-2 border-t border-outline-variant/30 space-y-1">
                <div className="font-bold text-[10px] uppercase tracking-wider text-outline">Relationships shown</div>
                {nodeEdges.length === 0 && <div className="text-outline">None loaded. Use Expand.</div>}
                {nodeEdges.slice(0, 12).map((e) => {
                  const other = graph.nodes.get(e.source === selNode.key ? e.target : e.source)
                  return <button key={e.id} onClick={() => select('node', other?.key)} className="w-full text-left flex justify-between rounded bg-white border border-outline-variant/30 px-1.5 py-1"><span className="font-mono text-outline">{e.type}</span><b>{other?.label}</b></button>
                })}
              </div>
              {!selNode.case && (
                <div className="pt-2 border-t border-outline-variant/30 space-y-1">
                  <div className="font-bold text-[10px] uppercase tracking-wider text-outline">Path from this node</div>
                  <select aria-label="Path target" value={pathTarget} onChange={(e) => setPathTarget(e.target.value)} className="w-full rounded border border-outline-variant px-1 py-1">
                    <option value="">Choose a loaded node…</option>
                    {nodes.filter((n) => n.key !== selNode.key && !n.case).map((n) => <option key={n.key} value={n.key}>{n.label} ({n.type})</option>)}
                  </select>
                  <button onClick={findPath} disabled={!pathTarget || busy} className="inline-flex items-center gap-1 px-2 py-1 rounded bg-primary text-white font-semibold disabled:opacity-50"><Route size={12} />Find path</button>
                  {pathHit?.status === 'found' && <div data-testid="kg-path" className="text-on-surface">{pathHit.paths[0].nodes.map((n) => n.label).join(' → ')}</div>}
                </div>
              )}
            </>
          )}
          {selEdge && (
            <div className="space-y-1" data-testid="kg-edge-detail">
              <div className="font-bold">{selEdge.type}</div>
              <div>{graph.nodes.get(selEdge.source)?.label} → {graph.nodes.get(selEdge.target)?.label}</div>
              {Object.entries(selEdge.attrs || {}).map(([k, v]) => <div key={k}><span className="text-outline">{k}:</span> {String(v)}</div>)}
            </div>
          )}
          {mode === 'case' && (
            <div className="pt-2 border-t border-outline-variant/30 text-[11px] text-on-surface-variant flex items-start gap-1"><UserRound size={12} className="mt-0.5" />Case view: only data stored for this case. Disease nodes are candidates sharing a phenotype or gene, not diagnoses.</div>
          )}
        </div>
      </div>
    </div>
  )
}
