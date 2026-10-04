import React from 'react'

export function PageHeader({
  title,
  subtitle,
  badge,
  actions,
  className = '',
}) {
  // Safely render badge (string, React node, or { label, color, icon } object)
  let badgeEl = null
  if (badge) {
    if (React.isValidElement(badge)) {
      badgeEl = badge
    } else if (typeof badge === 'object' && badge.label) {
      const BadgeIcon = badge.icon
      const colorClass =
        badge.color === 'secondary'
          ? 'bg-secondary-container/20 text-secondary border-secondary/30'
          : badge.color === 'warning'
          ? 'bg-amber-100 text-amber-900 border-amber-300'
          : badge.color === 'tertiary'
          ? 'bg-tertiary-container/20 text-tertiary border-tertiary/30'
          : 'bg-primary-container/20 text-primary border-primary/30'

      badgeEl = (
        <span
          className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-semibold border ${colorClass}`}
        >
          {BadgeIcon && <BadgeIcon size={12} className="shrink-0" />}
          <span>{badge.label}</span>
        </span>
      )
    } else if (typeof badge === 'string') {
      badgeEl = (
        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-primary-container/20 text-primary border border-primary/30">
          {badge}
        </span>
      )
    }
  }

  return (
    <div
      className={`flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-outline-variant/30 ${className}`}
    >
      <div>
        <div className="flex items-center gap-2.5">
          <h2 className="text-xl font-bold font-headline-sm text-on-surface tracking-tight">
            {title}
          </h2>
          {badgeEl}
        </div>
        {subtitle && (
          <p className="text-xs text-on-surface-variant mt-1 max-w-2xl leading-relaxed">
            {subtitle}
          </p>
        )}
      </div>

      {actions && <div className="flex items-center gap-2.5 shrink-0">{actions}</div>}
    </div>
  )
}
