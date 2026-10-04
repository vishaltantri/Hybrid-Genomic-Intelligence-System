import React from 'react'

export function SkeletonLine({ width = 'w-full', height = 'h-4', className = '' }) {
  return (
    <div
      className={`${width} ${height} rounded bg-surface-container-high/60 animate-pulse ${className}`}
    />
  )
}

export function SkeletonCard({ className = '' }) {
  return (
    <div className={`p-5 rounded-xl bg-white border border-outline-variant/30 space-y-3 ${className}`}>
      <div className="flex items-center justify-between">
        <SkeletonLine width="w-1/3" height="h-5" />
        <SkeletonLine width="w-16" height="h-4" />
      </div>
      <SkeletonLine width="w-full" height="h-3" />
      <SkeletonLine width="w-4/5" height="h-3" />
      <div className="pt-2 flex gap-2">
        <SkeletonLine width="w-20" height="h-6" className="rounded-full" />
        <SkeletonLine width="w-24" height="h-6" className="rounded-full" />
      </div>
    </div>
  )
}

export function SkeletonTable({ rows = 4, cols = 4, className = '' }) {
  return (
    <div className={`rounded-xl bg-white border border-outline-variant/30 overflow-hidden ${className}`}>
      <div className="p-3 bg-surface-container-low border-b border-outline-variant/30 flex gap-4">
        {Array.from({ length: cols }).map((_, i) => (
          <SkeletonLine key={i} width="w-1/4" height="h-4" />
        ))}
      </div>
      <div className="divide-y divide-outline-variant/20 p-2">
        {Array.from({ length: rows }).map((_, r) => (
          <div key={r} className="py-3 flex gap-4 items-center">
            {Array.from({ length: cols }).map((_, c) => (
              <SkeletonLine key={c} width="w-1/4" height="h-4" />
            ))}
          </div>
        ))}
      </div>
    </div>
  )
}
