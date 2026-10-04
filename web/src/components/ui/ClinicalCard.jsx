import React, { useState } from 'react'
import { ChevronDown, ChevronUp } from 'lucide-react'

export function ClinicalCard({
  title,
  subtitle,
  icon: Icon,
  badge,
  headerBadge,
  action,
  collapsible = false,
  defaultExpanded = true,
  children,
  footer,
  className = '',
  highlight = false,
}) {
  const [expanded, setExpanded] = useState(defaultExpanded)

  const activeBadge = badge || headerBadge
  let badgeEl = null
  if (activeBadge) {
    if (React.isValidElement(activeBadge)) {
      badgeEl = activeBadge
    } else if (typeof activeBadge === 'object' && activeBadge.label) {
      const BadgeIcon = activeBadge.icon
      const colorClass =
        activeBadge.color === 'secondary'
          ? 'bg-secondary-container/20 text-secondary border-secondary/30'
          : activeBadge.color === 'warning'
          ? 'bg-amber-100 text-amber-900 border-amber-300'
          : activeBadge.color === 'tertiary'
          ? 'bg-tertiary-container/20 text-tertiary border-tertiary/30'
          : 'bg-primary-container/20 text-primary border-primary/30'

      badgeEl = (
        <span
          className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-semibold border ${colorClass}`}
        >
          {BadgeIcon && <BadgeIcon size={12} className="shrink-0" />}
          <span>{activeBadge.label}</span>
        </span>
      )
    } else if (typeof activeBadge === 'string') {
      badgeEl = (
        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-primary-container/20 text-primary border border-primary/30">
          {activeBadge}
        </span>
      )
    }
  }

  return (
    <div
      className={`rounded-xl bg-white border transition-all overflow-hidden ${
        highlight
          ? 'border-primary shadow-sm ring-1 ring-primary/20'
          : 'border-outline-variant/40 shadow-xs'
      } ${className}`}
    >
      {/* Card Header */}
      {(title || Icon || badgeEl || action) && (
        <div
          className={`p-4 flex items-center justify-between gap-3 border-b border-outline-variant/30 ${
            highlight ? 'bg-primary/5' : 'bg-surface-container-low/40'
          }`}
        >
          <div className="flex items-center gap-3 min-w-0">
            {Icon && (
              <div className="w-8 h-8 rounded-lg bg-surface-container flex items-center justify-center text-primary shrink-0">
                <Icon size={18} />
              </div>
            )}
            <div className="min-w-0">
              {title && (
                <h3 className="text-sm font-bold font-headline-sm text-on-surface truncate">
                  {title}
                </h3>
              )}
              {subtitle && (
                <p className="text-xs text-on-surface-variant truncate">{subtitle}</p>
              )}
            </div>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            {badgeEl && <div>{badgeEl}</div>}
            {action && <div>{action}</div>}
            {collapsible && (
              <button
                onClick={() => setExpanded(!expanded)}
                className="p-1 rounded text-outline hover:text-on-surface transition-colors"
                aria-label={expanded ? 'Collapse section' : 'Expand section'}
              >
                {expanded ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
              </button>
            )}
          </div>
        </div>
      )}

      {/* Card Body */}
      {(!collapsible || expanded) && <div className="p-5">{children}</div>}

      {/* Card Footer */}
      {(!collapsible || expanded) && footer && (
        <div className="px-5 py-3 bg-surface-container-low/30 border-t border-outline-variant/30 text-xs text-on-surface-variant flex items-center justify-between">
          {footer}
        </div>
      )}
    </div>
  )
}
