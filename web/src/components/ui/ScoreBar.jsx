import React from 'react'

export function ScoreBar({
  value = 0,
  max = 1,
  label,
  valueText,
  color = 'primary',
  size = 'md',
  className = '',
}) {
  const numVal = typeof value === 'number' ? value : parseFloat(value) || 0
  const numMax = typeof max === 'number' ? max : 1
  const pct = Math.min(100, Math.max(0, (numVal / numMax) * 100))

  const heightClass = size === 'sm' ? 'h-1.5' : size === 'lg' ? 'h-3' : 'h-2'

  let barColor = 'bg-primary'
  if (color === 'secondary') barColor = 'bg-secondary'
  else if (color === 'amber' || color === 'warning') barColor = 'bg-amber-500'
  else if (color === 'red' || color === 'danger') barColor = 'bg-red-600'
  else if (color === 'emerald' || color === 'good') barColor = 'bg-emerald-600'
  else if (color === 'tertiary') barColor = 'bg-tertiary'

  return (
    <div className={`w-full ${className}`}>
      {(label || valueText) && (
        <div className="flex items-center justify-between text-xs mb-1">
          {label && <span className="text-on-surface-variant font-medium truncate">{label}</span>}
          {valueText && <span className="font-mono font-semibold text-on-surface shrink-0">{valueText}</span>}
        </div>
      )}
      <div
        className={`w-full ${heightClass} rounded-full bg-surface-container-high/60 overflow-hidden border border-outline-variant/30`}
        role="progressbar"
        aria-valuenow={Math.round(pct)}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div
          className={`${heightClass} rounded-full ${barColor} transition-all duration-300 ease-out`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}
