import React from 'react'
import { Inbox, ArrowRight } from 'lucide-react'

export function EmptyState({
  title = 'No Data Available',
  description = 'No clinical records found for the requested criteria.',
  icon: Icon = Inbox,
  actionText,
  onAction,
  className = '',
}) {
  return (
    <div className={`p-10 rounded-xl bg-white border border-outline-variant/40 text-center flex flex-col items-center justify-center ${className}`}>
      <div className="w-12 h-12 rounded-xl bg-surface-container flex items-center justify-center text-outline mb-3">
        <Icon size={24} />
      </div>
      <h4 className="text-sm font-bold text-on-surface">{title}</h4>
      <p className="text-xs text-on-surface-variant max-w-sm mt-1 mb-4 leading-relaxed">
        {description}
      </p>
      {actionText && onAction && (
        <button
          onClick={onAction}
          className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-primary text-white text-xs font-semibold hover:bg-primary-container transition-colors shadow-xs"
        >
          <span>{actionText}</span>
          <ArrowRight size={14} />
        </button>
      )}
    </div>
  )
}
