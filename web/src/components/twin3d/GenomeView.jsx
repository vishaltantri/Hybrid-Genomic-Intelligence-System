import React from 'react'

const CLASS_COLOR = {
  Pathogenic: '#12497a',
  'Likely pathogenic': '#2f78b5',
  'Uncertain significance': '#7d8fa0',
  'Likely benign': '#b4c3d0',
  Benign: '#c9d5df',
}
const W = 330

/**
 * Chromosome view. Bars are scaled by GRCh38 chromosome length; each marker sits at the position reported in the
 * uploaded VCF. No gene loci are drawn (none are stored). Selecting a marker opens the same evidence panel as the body.
 */
export default function GenomeView({ chromosomes, selectedVariantId, selectedChrom, onSelectVariant, onSelectChrom, ghostIds = [], compact = false }) {
  const max = Math.max(...chromosomes.map((c) => c.length_bp))
  const ghost = new Set(ghostIds)
  const rowH = compact ? 15 : 24
  const half = Math.ceil(chromosomes.length / 2)
  const label = (c) => c.chrom.replace('chr', '')
  const press = (fn) => (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      fn()
    }
  }
  const column = (list, x0) =>
    list.map((c, k) => {
      const y = 16 + k * rowH
      const w = (c.length_bp / max) * W
      return (
        <g key={c.chrom} data-testid={`chrom-${c.chrom}`}>
          <text x={x0 - 6} y={y + 4} textAnchor="end" fontSize={compact ? 8 : 10} fill="#425a70" fontWeight={selectedChrom === c.chrom ? 700 : 500}>
            {label(c)}
          </text>
          <rect
            x={x0} y={y - 4} width={w} height={compact ? 7 : 9} rx="4.5"
            fill={selectedChrom === c.chrom ? '#d4e8f7' : '#e6eef6'} stroke="#a9bccd" strokeWidth="1"
            role="button" tabIndex={0}
            aria-label={`Chromosome ${label(c)}, ${c.variants.length} analysed variants`}
            style={{ cursor: 'pointer' }}
            onClick={() => onSelectChrom && onSelectChrom(c.chrom)}
            onKeyDown={press(() => onSelectChrom && onSelectChrom(c.chrom))}
          />
          {c.variants.map((v) => {
            const cx = x0 + (v.pos / c.length_bp) * w
            const sel = v.variant_id === selectedVariantId
            const gone = ghost.has(v.variant_id)
            return (
              <g key={v.variant_id}>
                {sel && <circle cx={cx} cy={y} r="9" fill="none" stroke="#0e9f9a" strokeWidth="2" />}
                <circle
                  cx={cx} cy={y} r={compact ? 3.5 : 5.2}
                  fill={gone ? 'none' : CLASS_COLOR[v.classification] || '#7d8fa0'}
                  stroke={gone ? '#7d8fa0' : '#fff'} strokeWidth={gone ? 1.5 : 1}
                  strokeDasharray={gone ? '2 2' : undefined}
                  role="button" tabIndex={0}
                  data-testid={`genome-variant-${v.variant_id}`}
                  aria-label={`${v.gene || 'Unknown gene'} ${v.hgvs || ''} on chromosome ${label(c)}, ${v.classification}${gone ? ', excluded in scenario' : ''}`}
                  style={{ cursor: 'pointer' }}
                  onClick={() => onSelectVariant && onSelectVariant(v.variant_id)}
                  onKeyDown={press(() => onSelectVariant && onSelectVariant(v.variant_id))}
                />
                {!compact && <text x={cx + 8} y={y - 7} fontSize="9" fill="#12497a" fontWeight="600">{v.gene}</text>}
              </g>
            )
          })}
        </g>
      )
    })
  return (
    <div className="w-full h-full overflow-auto" data-testid="genome-view">
      <svg viewBox={`0 0 ${W * 2 + 110} ${16 + half * rowH + 8}`} className="w-full min-w-[560px]" role="group" aria-label="Chromosome view">
        {column(chromosomes.slice(0, half), 28)}
        {column(chromosomes.slice(half), W + 78)}
      </svg>
      {!compact && (
        <p className="text-[11px] text-outline px-3 pb-2">
          Marker position = VCF position scaled to the chromosome (GRCh38 lengths). Gene loci are not drawn: no gene coordinates are stored.
        </p>
      )}
    </div>
  )
}
