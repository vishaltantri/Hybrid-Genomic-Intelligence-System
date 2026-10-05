import React from 'react'
import { ORGANS } from './bodyModel.js'
import { SYSTEM_STATE, TWIN_COLORS } from './webgl.js'

const sx = (x) => 120 + x * 150
const sy = (y) => 200 - y * 95

/**
 * 2D anatomical schematic (anterior view). Used when WebGL is unavailable or fails, and always reachable by
 * assistive tech through the system list in the clinical panel. Same data, same selection behaviour.
 */
export default function BodyFallback2D({ selectedSystem, linkedSystems, caseSystems, onSelectSystem, notice }) {
  const stateOf = (sys) => SYSTEM_STATE(sys, { selectedSystem, linkedSystems, caseSystems })
  return (
    <div className="w-full h-full flex flex-col items-center justify-center" data-testid="body-fallback-2d">
      <svg viewBox="0 0 240 440" className="h-full max-h-[460px] w-auto" role="group" aria-label="Anatomical schematic (2D)">
        <defs>
          <linearGradient id="bodyfill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#12305a" />
            <stop offset="1" stopColor="#0a1c38" />
          </linearGradient>
        </defs>
        <g fill="url(#bodyfill)" stroke="#4fc3ff" strokeWidth="1.2" opacity="0.95">
          <ellipse cx="120" cy="38" rx="28" ry="32" />
          <rect x="108" y="66" width="24" height="22" rx="8" />
          <path d="M72 92 Q120 78 168 92 L176 230 Q172 262 160 270 L80 270 Q68 262 64 230 Z" />
          <rect x="30" y="96" width="30" height="130" rx="14" transform="rotate(6 45 96)" />
          <rect x="180" y="96" width="30" height="130" rx="14" transform="rotate(-6 195 96)" />
          <rect x="80" y="268" width="34" height="150" rx="16" />
          <rect x="126" y="268" width="34" height="150" rx="16" />
        </g>
        {ORGANS.filter((o) => o.shape !== 'cyl' || o.id === 'spine').map((o) => {
          const st = stateOf(o.system)
          const fill = TWIN_COLORS[st]
          const rx = Math.max(3, o.s[0] * 150)
          const ry = o.shape === 'cyl' ? (o.s[1] * 95) / 2 : Math.max(3, o.s[1] * 95)
          const common = {
            role: 'button',
            tabIndex: 0,
            'aria-label': `${o.label} (${o.system})`,
            'data-testid': `organ-${o.id}`,
            onClick: () => onSelectSystem(o.system),
            onKeyDown: (e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault()
                onSelectSystem(o.system)
              }
            },
            style: { cursor: 'pointer' },
          }
          if (o.shape === 'torus') {
            return <ellipse key={o.id} {...common} cx={sx(o.p[0])} cy={sy(o.p[1])} rx={rx} ry={ry * 0.8} fill="none" stroke={fill} strokeWidth="5" opacity="0.9" />
          }
          if (o.shape === 'box') {
            return <rect key={o.id} {...common} x={sx(o.p[0]) - rx} y={sy(o.p[1]) - ry} width={rx * 2} height={ry * 2} fill={fill} opacity="0.95" />
          }
          return (
            <ellipse key={o.id} {...common} cx={sx(o.p[0])} cy={sy(o.p[1])} rx={rx} ry={ry} fill={fill}
              opacity={st === 'neutral' ? 0.8 : 1} stroke={st === 'selected' ? '#dfffff' : 'none'} strokeWidth="2" />
          )
        })}
      </svg>
      {notice && <p className="text-[11px] mt-2 text-center max-w-xs" style={{ color: "#a9d8f5" }}>{notice}</p>}
    </div>
  )
}
