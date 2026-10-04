import React from 'react'
import { AlertCircle, RefreshCw } from 'lucide-react'

export function ErrorAlert({
  title = 'Operation Error',
  message,
  onRetry,
  className = '',
}) {
  if (!message) return null

  return (
    <div
      className={`p-4 rounded-xl bg-red-50/80 border border-red-200 text-red-900 text-xs flex items-start justify-between gap-3 ${className}`}
      role="alert"
    >
      <div className="flex items-start gap-2.5">
        <AlertCircle size={18} className="text-red-600 shrink-0 mt-0.5" />
        <div>
          {title && <div className="font-bold text-red-800 mb-0.5">{title}</div>}
          <div className="leading-relaxed text-red-700">{message}</div>
        </div>
      </div>

      {onRetry && (
        <button
          onClick={onRetry}
          className="shrink-0 px-2.5 py-1 rounded bg-white border border-red-300 text-red-800 text-[11px] font-semibold hover:bg-red-100/50 transition-colors flex items-center gap-1"
        >
          <RefreshCw size={12} />
          <span>Retry</span>
        </button>
      )}
    </div>
  )
}
