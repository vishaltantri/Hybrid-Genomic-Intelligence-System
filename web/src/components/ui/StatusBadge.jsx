import React from 'react'
import {
  AlertOctagon,
  AlertTriangle,
  CheckCircle2,
  Info,
  ShieldAlert,
  ShieldCheck,
  Activity,
} from 'lucide-react'

export function SeverityBadge({ severity, className = '' }) {
  const s = (severity || '').toLowerCase()

  if (s === 'critical' || s === 'severe' || s === 'red') {
    return (
      <span
        className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-bold uppercase tracking-wider bg-red-100 text-red-800 border border-red-300 font-mono ${className}`}
      >
        <AlertOctagon size={13} className="text-red-700 shrink-0" />
        <span>CRITICAL RISK</span>
      </span>
    )
  }

  if (s === 'warning' || s === 'high' || s === 'yellow' || s === 'amber') {
    return (
      <span
        className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-bold uppercase tracking-wider bg-amber-100 text-amber-900 border border-amber-300 font-mono ${className}`}
      >
        <AlertTriangle size={13} className="text-amber-700 shrink-0" />
        <span>ELEVATED RISK</span>
      </span>
    )
  }

  if (s === 'moderate' || s === 'info' || s === 'carrier') {
    return (
      <span
        className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-bold uppercase tracking-wider bg-blue-100 text-blue-900 border border-blue-300 font-mono ${className}`}
      >
        <Info size={13} className="text-blue-700 shrink-0" />
        <span>MODERATE / CARRIER</span>
      </span>
    )
  }

  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-bold uppercase tracking-wider bg-emerald-100 text-emerald-900 border border-emerald-300 font-mono ${className}`}
    >
      <CheckCircle2 size={13} className="text-emerald-700 shrink-0" />
      <span>LOW RISK / STANDARD</span>
    </span>
  )
}

export function ConfidenceBadge({ confidence, score, className = '' }) {
  if (typeof confidence === 'number') {
    score = confidence
    confidence = ''
  }
  let level = typeof confidence === 'string' ? confidence.toLowerCase() : ''
  if (!level && typeof score === 'number') {
    if (score >= 0.75) level = 'high'
    else if (score >= 0.4) level = 'medium'
    else level = 'low'
  }

  if (level === 'high') {
    return (
      <span
        className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-800 border border-emerald-200 ${className}`}
      >
        <ShieldCheck size={13} className="text-emerald-600" />
        <span>High Confidence</span>
      </span>
    )
  }

  if (level === 'medium' || level === 'moderate') {
    return (
      <span
        className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-blue-50 text-blue-800 border border-blue-200 ${className}`}
      >
        <Activity size={13} className="text-blue-600" />
        <span>Moderate Confidence</span>
      </span>
    )
  }

  return (
    <span
      className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-slate-100 text-slate-700 border border-slate-300 ${className}`}
    >
      <Info size={13} className="text-slate-500" />
      <span>Low / Exploratory</span>
    </span>
  )
}

export function EvidenceBadge({ level, source, className = '' }) {
  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded bg-surface-container text-on-surface text-[11px] font-mono font-medium border border-outline-variant/40 ${className}`}
    >
      <span className="text-primary font-bold">{level || 'CPIC'}</span>
      {source && <span className="text-outline">· {source}</span>}
    </span>
  )
}

export function StatusBadge({ status, label, color = 'neutral', className = '' }) {
  const colorMap = {
    primary: 'bg-primary-container/20 text-primary border-primary/20',
    secondary: 'bg-secondary-container/20 text-secondary border-secondary/20',
    success: 'bg-emerald-50 text-emerald-800 border-emerald-200',
    warning: 'bg-amber-50 text-amber-800 border-amber-200',
    danger: 'bg-red-50 text-red-800 border-red-200',
    neutral: 'bg-surface-container-high text-on-surface-variant border-outline-variant/40',
  }
  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold border ${colorMap[color] || colorMap.neutral} ${className}`}
    >
      {label || status}
    </span>
  )
}

