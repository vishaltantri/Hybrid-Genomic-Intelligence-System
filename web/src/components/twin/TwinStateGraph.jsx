import React from 'react'

/**
 * Clinical state map of the Digital Twin.
 * Each node is one section of the computed Twin state. Its label and count are read from the
 * Twin payload; a section with no underlying data is drawn dashed and says "Insufficient data".
 * Nothing here is animated or decorative - nodes only change when the Twin data changes.
 */
export const TWIN_SECTIONS = [
  { id: 'phenotype', label: 'Phenotype', x: 130, y: 50 },
  { id: 'genomic', label: 'Genomic', x: 430, y: 50 },
  { id: 'diagnosis', label: 'Diagnosis', x: 490, y: 150 },
  { id: 'pgx', label: 'PGx', x: 430, y: 250 },
  { id: 'family', label: 'Family', x: 130, y: 250 },
  { id: 'timeline', label: 'Timeline', x: 70, y: 150 },
]

export function sectionSummary(twin, id) {
  if (!twin) return { available: false, detail: '' }
  switch (id) {
    case 'phenotype':
      return { available: twin.phenotype.available, detail: `${twin.phenotype.count} HPO terms` }
    case 'genomic':
      return {
        available: twin.genomic.available,
        detail: `${twin.genomic.counts.total} variants`,
      }
    case 'diagnosis': {
      const top = twin.diagnosis.top_diagnosis
      return { available: twin.diagnosis.available, detail: top ? top.disease_name : '' }
    }
    case 'pgx':
      return { available: twin.pgx.available, detail: `${twin.pgx.findings.length} findings` }
    case 'family':
      return { available: twin.family.available, detail: 'record fields' }
    case 'timeline':
      return { available: twin.timeline.available, detail: `${twin.timeline.events.length} events` }
    default:
      return { available: false, detail: '' }
  }
}

export default function TwinStateGraph({ twin, active, onSelect }) {
  return (
    <svg
      viewBox="0 0 560 300"
      className="w-full h-auto"
      role="group"
      aria-label="Digital Twin state sections"
      data-testid="twin-state-graph"
    >
      {TWIN_SECTIONS.map((s) => (
        <line
          key={`l-${s.id}`}
          x1="280"
          y1="150"
          x2={s.x}
          y2={s.y}
          stroke="#c1c7d2"
          strokeWidth="1.5"
        />
      ))}
      <circle cx="280" cy="150" r="44" fill="#00629E" />
      <text x="280" y="146" textAnchor="middle" fontSize="12" fontWeight="700" fill="#fff">
        Twin
      </text>
      <text x="280" y="162" textAnchor="middle" fontSize="9" fill="#c0dcff">
        {twin ? twin.identity.patient_id : '-'}
      </text>
      {TWIN_SECTIONS.map((s) => {
        const info = sectionSummary(twin, s.id)
        const isActive = active === s.id
        const stroke = isActive ? '#00629E' : info.available ? '#1B6B50' : '#9ca3af'
        const detail = info.available ? info.detail : 'Insufficient data'
        return (
          <g
            key={s.id}
            role="button"
            tabIndex={0}
            aria-label={`${s.label}: ${detail}`}
            aria-pressed={isActive}
            data-testid={`twin-node-${s.id}`}
            onClick={() => onSelect(s.id)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault()
                onSelect(s.id)
              }
            }}
            style={{ cursor: 'pointer' }}
          >
            <rect
              x={s.x - 56}
              y={s.y - 24}
              width="112"
              height="48"
              rx="10"
              fill={isActive ? '#e8f1fb' : '#ffffff'}
              stroke={stroke}
              strokeWidth={isActive ? 2.5 : 1.5}
              strokeDasharray={info.available ? undefined : '4 3'}
            />
            <text x={s.x} y={s.y - 5} textAnchor="middle" fontSize="11" fontWeight="700" fill="#19324d">
              {s.label}
            </text>
            <text
              x={s.x}
              y={s.y + 12}
              textAnchor="middle"
              fontSize="9"
              fill={info.available ? '#1B6B50' : '#6b7280'}
            >
              {detail.length > 20 ? `${detail.slice(0, 19)}…` : detail}
            </text>
          </g>
        )
      })}
    </svg>
  )
}
