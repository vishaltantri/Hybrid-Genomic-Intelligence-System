import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Maximize, Minus, Plus, RotateCcw } from 'lucide-react'
import { SYMBOL, bounds, layoutPedigree, pedigreeEdges } from './layout.js'

const NAVY = '#12497a'
const TEAL = '#0e9f9a'
const R = SYMBOL / 2

/**
 * Interactive pedigree canvas (SVG): pan (drag background), zoom (wheel / buttons), fit-to-screen, node selection and
 * node dragging (persisted through onMove). Standard clinical symbols: square = male, circle = female, diamond =
 * unspecified; filled = affected, open = unaffected; half-filled = carrier (only drawn when a variant is analysed and the
 * recorded genotype shows a carrier); arrow = proband; slash = deceased.
 *
 * `variantStates` (member_id -> 'het' | 'hom' | 'hemi' | 'absent' | 'unknown') switches on variant-focused mode.
 */
function Shape({ sex, clipId, ...rest }) {
  if (sex === 'M') return <rect x={-R} y={-R} width={SYMBOL} height={SYMBOL} {...rest} />
  if (sex === 'F') return <circle r={R} {...rest} />
  return <polygon points={`0,${-R * 1.25} ${R * 1.25},0 0,${R * 1.25} ${-R * 1.25},0`} {...rest} />
}

function Node({ m, p, selected, state, variantMode, onPointerDown }) {
  const affected = m.affected === 'affected'
  const carrier = variantMode && (state === 'het' || state === 'hom' || state === 'hemi')
  const unknownGt = variantMode && state === 'unknown'
  let fill = '#ffffff'
  if (!variantMode) fill = affected ? NAVY : '#ffffff'
  else if (state === 'hom' || state === 'hemi') fill = NAVY
  else if (state === 'het') fill = '#ffffff'
  const stroke = selected ? TEAL : NAVY
  const clipId = `half-${m.member_id}`
  const stateLabel = { het: 'het', hom: 'hom', hemi: 'hemi', absent: 'absent', unknown: 'unknown' }[state]
  const aria = `${m.label}, ${m.sex === 'M' ? 'male' : m.sex === 'F' ? 'female' : 'sex unspecified'}, ${m.affected}${m.is_proband ? ', proband' : ''}${variantMode ? `, genotype ${stateLabel}` : ''}`
  return (
    <g
      transform={`translate(${p.x},${p.y})`}
      data-testid={`ped-node-${m.member_id}`}
      data-label={m.label}
      data-selected={selected ? 'true' : 'false'}
      data-genotype={variantMode ? state : undefined}
      role="button" tabIndex={0} aria-label={aria}
      style={{ cursor: 'grab', opacity: unknownGt ? 0.45 : 1, outline: 'none' }}
      onPointerDown={(e) => onPointerDown(e, m)}
      onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && (e.preventDefault(), onPointerDown({ ...e, keyboard: true, stopPropagation: () => {} }, m))}
    >
      {selected && <circle r={R + 9} fill="none" stroke={TEAL} strokeWidth="2" strokeDasharray="4 3" />}
      <Shape sex={m.sex} fill={fill} stroke={stroke} strokeWidth={selected ? 3 : 2} strokeDasharray={unknownGt ? '5 3' : undefined} />
      {variantMode && state === 'het' && (
        <>
          <defs><clipPath id={clipId}><rect x={-R * 1.3} y={-R * 1.3} width={R * 1.3} height={R * 2.6} /></clipPath></defs>
          <g clipPath={`url(#${clipId})`}><Shape sex={m.sex} fill={NAVY} stroke="none" /></g>
        </>
      )}
      {variantMode && carrier && affected && <circle r={R + 5} fill="none" stroke={NAVY} strokeWidth="1.5" />}
      {m.affected === 'unknown' && !variantMode && <text textAnchor="middle" dy="5" fontSize="15" fontWeight="700" fill={NAVY}>?</text>}
      {m.deceased && <line x1={-R - 8} y1={R + 8} x2={R + 8} y2={-R - 8} stroke="#334155" strokeWidth="2" />}
      {m.is_proband && (
        <g aria-hidden>
          <line x1={-R - 26} y1={R + 22} x2={-R - 6} y2={R + 4} stroke={NAVY} strokeWidth="2.2" />
          <polygon points={`${-R - 6},${R + 4} ${-R - 15},${R + 5} ${-R - 7},${R + 13}`} fill={NAVY} />
          <text x={-R - 30} y={R + 34} fontSize="9" fontWeight="700" fill={NAVY} textAnchor="middle">P</text>
        </g>
      )}
      <text y={R + 18} textAnchor="middle" fontSize="11" fontWeight="600" fill="#19324d"><title>{m.label}</title>{m.label.length > 17 ? `${m.label.slice(0, 16)}…` : m.label}</text>
      <text y={R + 31} textAnchor="middle" fontSize="9" fill="#5b7186">
        {[m.relation_to_proband && m.relation_to_proband !== 'self' ? m.relation_to_proband : m.is_proband ? 'proband' : null, m.age_years != null ? `${m.age_years}y` : null].filter(Boolean).join(' · ')}
      </text>
      {variantMode && (
        <text y={R + 43} textAnchor="middle" fontSize="9.5" fontWeight="700" fill={state === 'unknown' ? '#7d8fa0' : TEAL}>
          {stateLabel}{m.affected === 'affected' ? ' · affected' : m.affected === 'unaffected' ? ' · unaffected' : ' · status ?'}
        </text>
      )}
    </g>
  )
}

export default function PedigreeCanvas({ members, selectedId, onSelect, onMove, variantStates, ariaLabel = 'Pedigree canvas' }) {
  const wrap = useRef(null)
  const [view, setView] = useState({ x: 0, y: 0, k: 1 })
  const [drag, setDrag] = useState(null) // {id, x, y}
  const base = useMemo(() => layoutPedigree(members), [members])
  const pos = useMemo(() => (drag ? { ...base, [drag.id]: { x: drag.x, y: drag.y } } : base), [base, drag])
  const edges = useMemo(() => pedigreeEdges(members, pos), [members, pos])
  const variantMode = !!variantStates
  const interaction = useRef(null)

  const size = () => {
    const r = wrap.current?.getBoundingClientRect()
    return { w: r && r.width > 0 ? r.width : 900, h: r && r.height > 0 ? r.height : 520 }
  }
  const fit = useCallback(() => {
    const b = bounds(base)
    const { w, h } = size()
    const k = Math.min(w / b.w, h / b.h, 1.4)
    setView({ k, x: (w - b.w * k) / 2 - b.x * k, y: (h - b.h * k) / 2 - b.y * k })
  }, [base])
  // refit when the structure (not merely a selection) changes
  const structureKey = members.map((m) => `${m.member_id}:${m.generation}:${m.layout_x ?? ''}`).join('|')
  useEffect(() => { fit() }, [structureKey]) // eslint-disable-line react-hooks/exhaustive-deps

  const zoom = (factor, cx, cy) => setView((v) => {
    const { w, h } = size()
    const px = cx ?? w / 2
    const py = cy ?? h / 2
    const k = Math.max(0.25, Math.min(3, v.k * factor))
    return { k, x: px - ((px - v.x) / v.k) * k, y: py - ((py - v.y) / v.k) * k }
  })

  useEffect(() => {
    const el = wrap.current
    if (!el) return undefined
    const onWheel = (e) => {
      e.preventDefault()
      const r = el.getBoundingClientRect()
      zoom(e.deltaY < 0 ? 1.1 : 0.9, e.clientX - r.left, e.clientY - r.top)
    }
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => el.removeEventListener('wheel', onWheel)
  }, [])

  const toCanvas = (clientX, clientY) => {
    const r = wrap.current.getBoundingClientRect()
    return { x: (clientX - r.left - view.x) / view.k, y: (clientY - r.top - view.y) / view.k }
  }

  const onBackgroundDown = (e) => {
    if (e.button != null && e.button !== 0) return
    interaction.current = { type: 'pan', sx: e.clientX, sy: e.clientY, vx: view.x, vy: view.y, moved: false }
    e.currentTarget.setPointerCapture?.(e.pointerId)
  }
  const onNodeDown = (e, m) => {
    e.stopPropagation()
    if (e.keyboard) return onSelect(m.member_id)
    interaction.current = { type: 'node', id: m.member_id, sx: e.clientX, sy: e.clientY, orig: pos[m.member_id], moved: false }
    wrap.current?.setPointerCapture?.(e.pointerId)
  }
  const onMoveEvt = (e) => {
    const it = interaction.current
    if (!it) return
    const dx = e.clientX - it.sx
    const dy = e.clientY - it.sy
    if (!it.moved && Math.hypot(dx, dy) < 4) return
    it.moved = true
    if (it.type === 'pan') setView((v) => ({ ...v, x: it.vx + dx, y: it.vy + dy }))
    else if (onMove) setDrag({ id: it.id, x: it.orig.x + dx / view.k, y: it.orig.y + dy / view.k })
  }
  const onUp = () => {
    const it = interaction.current
    interaction.current = null
    if (!it) return
    if (it.type === 'node') {
      if (!it.moved) onSelect(it.id)
      else if (drag && onMove) onMove(it.id, Math.round(drag.x), Math.round(drag.y))
      setDrag(null)
    } else if (!it.moved) onSelect(null)
  }

  return (
    <div className="relative w-full rounded-2xl border border-outline-variant/40 bg-gradient-to-b from-[#f7fbff] to-[#eaf3fb] overflow-hidden touch-none select-none"
      style={{ height: 'clamp(380px, 56vh, 620px)' }} ref={wrap} data-testid="pedigree-canvas"
      onPointerMove={onMoveEvt} onPointerUp={onUp} onPointerCancel={onUp}>
      <div className="absolute inset-0 opacity-50 pointer-events-none" style={{ backgroundImage: 'linear-gradient(#d5e5f3 1px, transparent 1px), linear-gradient(90deg, #d5e5f3 1px, transparent 1px)', backgroundSize: '28px 28px' }} />
      <svg width="100%" height="100%" role="group" aria-label={ariaLabel} onPointerDown={onBackgroundDown} style={{ cursor: 'grab' }}>
        <g transform={`translate(${view.x},${view.y}) scale(${view.k})`} data-testid="pedigree-viewport" data-zoom={view.k.toFixed(3)}>
          {edges.map((s) => (
            <line key={s.key} x1={s.x1} y1={s.y1} x2={s.x2} y2={s.y2} stroke={s.kind === 'partner' ? '#334155' : '#5b7186'} strokeWidth={s.kind === 'partner' ? 2 : 1.6} data-kind={s.kind} />
          ))}
          {members.map((m) => (
            <Node key={m.member_id} m={m} p={pos[m.member_id]} selected={selectedId === m.member_id}
              state={variantMode ? (variantStates[m.member_id] || 'unknown') : null} variantMode={variantMode} onPointerDown={onNodeDown} />
          ))}
        </g>
      </svg>
      {!members.length && (
        <div className="absolute inset-0 flex items-center justify-center text-xs text-on-surface-variant pointer-events-none">
          No family members yet. Add the proband to start the pedigree.
        </div>
      )}
      <div className="absolute top-3 right-3 flex flex-col gap-1.5">
        {[['zoom-in', Plus, 'Zoom in', () => zoom(1.2)], ['zoom-out', Minus, 'Zoom out', () => zoom(1 / 1.2)], ['fit', Maximize, 'Fit to screen', fit]].map(([id, Icon, label, fn]) => (
          <button key={id} data-testid={`ped-${id}`} aria-label={label} onClick={fn}
            className="p-1.5 rounded-lg bg-white/90 border border-outline-variant/60 text-on-surface hover:bg-white shadow-sm"><Icon size={15} /></button>
        ))}
        <button data-testid="ped-reset-layout" aria-label="Reset dragged positions" onClick={() => onMove && onMove(null)} className="p-1.5 rounded-lg bg-white/90 border border-outline-variant/60 text-on-surface hover:bg-white shadow-sm"><RotateCcw size={15} /></button>
      </div>
    </div>
  )
}

export function PedigreeLegend({ variantMode }) {
  const S = ({ children }) => <svg width="26" height="22" viewBox="-13 -11 26 22" aria-hidden>{children}</svg>
  const st = { stroke: NAVY, strokeWidth: 1.6 }
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[11px] text-on-surface-variant" data-testid="pedigree-legend">
      <span className="flex items-center gap-1"><S><rect x="-8" y="-8" width="16" height="16" fill="#fff" {...st} /></S>Male</span>
      <span className="flex items-center gap-1"><S><circle r="8" fill="#fff" {...st} /></S>Female</span>
      <span className="flex items-center gap-1"><S><polygon points="0,-10 10,0 0,10 -10,0" fill="#fff" {...st} /></S>Unspecified sex</span>
      <span className="flex items-center gap-1"><S><circle r="8" fill={NAVY} {...st} /></S>Affected</span>
      <span className="flex items-center gap-1"><S><circle r="8" fill="#fff" {...st} /></S>Unaffected</span>
      <span className="flex items-center gap-1"><span className="font-bold text-primary">?</span>Status unknown</span>
      <span className="flex items-center gap-1"><S><circle r="8" fill="#fff" {...st} /><path d="M0,-8 A8,8 0 0 0 0,8 Z" fill={NAVY} /></S>Carrier (heterozygous; variant mode only)</span>
      <span className="flex items-center gap-1"><S><line x1="-12" y1="9" x2="-3" y2="2" stroke={NAVY} strokeWidth="2" /><polygon points="-3,2 -8,2 -3,7" fill={NAVY} /></S>Proband</span>
      <span className="flex items-center gap-1"><S><circle r="8" fill="#fff" {...st} /><line x1="-10" y1="10" x2="10" y2="-10" stroke="#334155" strokeWidth="1.6" /></S>Deceased</span>
      {variantMode && <span className="flex items-center gap-1"><S><circle r="8" fill="#fff" stroke={NAVY} strokeDasharray="3 2" opacity=".5" /></S>Genotype unknown</span>}
    </div>
  )
}
