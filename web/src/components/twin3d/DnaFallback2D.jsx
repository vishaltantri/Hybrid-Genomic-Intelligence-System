import React from 'react'

export default function DnaFallback2D({ marker }) {
  const pts = Array.from({ length: 60 }, (_, i) => i)
  const y = (i) => 20 + i * 6
  const xa = (i) => 150 + 48 * Math.sin(i / 5)
  const xb = (i) => 150 - 48 * Math.sin(i / 5)
  return (
    <div className="w-full h-full flex flex-col items-center justify-center" data-testid="dna-fallback-2d">
      <svg viewBox="0 0 300 400" className="h-full max-h-[460px] w-auto" role="img" aria-label="DNA double helix schematic (2D)">
        {pts.filter((i) => i % 3 === 0).map((i) => (
          <line key={i} x1={xa(i)} y1={y(i)} x2={xb(i)} y2={y(i)} stroke="#8fc7e8" strokeWidth="3" />
        ))}
        <polyline fill="none" stroke="#3e8fc9" strokeWidth="5" points={pts.map((i) => `${xa(i)},${y(i)}`).join(' ')} />
        <polyline fill="none" stroke="#58b2b0" strokeWidth="5" points={pts.map((i) => `${xb(i)},${y(i)}`).join(' ')} />
        {marker && <circle cx="205" cy={y(Math.round(marker.fraction * 59))} r="8" fill="#0e9f9a" />}
      </svg>
      <p className="text-[11px] text-center max-w-xs" style={{ color: "#a9d8f5" }}>Schematic double helix (3D unavailable).</p>
    </div>
  )
}
