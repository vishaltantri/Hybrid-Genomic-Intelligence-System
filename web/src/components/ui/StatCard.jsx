import React from 'react'

export function StatCard({
  title,
  value,
  subtitle,
  icon: Icon,
  color = 'primary',
  badge,
  className = '',
  onClick,
}) {
  let iconBg = 'bg-primary/10 text-primary'
  let valColor = 'text-primary'

  if (color === 'secondary') {
    iconBg = 'bg-secondary/10 text-secondary'
    valColor = 'text-secondary'
  } else if (color === 'tertiary') {
    iconBg = 'bg-tertiary/10 text-tertiary'
    valColor = 'text-tertiary'
  } else if (color === 'amber' || color === 'warning') {
    iconBg = 'bg-amber-100 text-amber-800'
    valColor = 'text-amber-800'
  } else if (color === 'red' || color === 'danger') {
    iconBg = 'bg-red-100 text-red-800'
    valColor = 'text-red-800'
  }

  return (
    <div
      onClick={onClick}
      className={`p-4 rounded-xl bg-white border border-outline-variant/40 shadow-xs flex flex-col justify-between transition-all ${
        onClick ? 'cursor-pointer hover:shadow-md hover:border-primary/40' : ''
      } ${className}`}
    >
      <div className="flex items-center justify-between text-outline mb-2">
        <span className="text-xs font-semibold text-on-surface-variant uppercase tracking-wider truncate">
          {title}
        </span>
        {Icon && (
          <div className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${iconBg}`}>
            <Icon size={16} />
          </div>
        )}
      </div>

      <div className={`text-2xl font-bold font-mono tracking-tight ${valColor}`}>
        {value != null ? value : '—'}
      </div>

      {(subtitle || badge) && (
        <div className="mt-2 pt-2 border-t border-outline-variant/20 flex items-center justify-between text-[11px] text-on-surface-variant">
          {subtitle && <span className="truncate">{subtitle}</span>}
          {badge && <span className="shrink-0">{badge}</span>}
        </div>
      )}
    </div>
  )
}
