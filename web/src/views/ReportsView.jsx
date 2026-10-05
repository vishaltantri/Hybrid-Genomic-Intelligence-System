import React, { useState } from 'react'
import { api } from '../api.js'
import { FileCheck, Download, Printer, RefreshCw } from 'lucide-react'
import CaseWorkflowPanel from '../components/CaseWorkflowPanel.jsx'
import CaseReportPanel from '../components/CaseReportPanel.jsx'
import CaseBundlesPanel from '../components/twin/CaseBundlesPanel.jsx'

export default function ReportsView() {
  const [brief, setBrief] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const generateReport = async () => {
    setBusy(true)
    setError(null)
    try {
      const res = await api.policyBrief()
      setBrief(res?.brief || res?.markdown || JSON.stringify(res, null, 2))
    } catch (ex) {
      setError(ex.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold font-headline-sm text-on-surface">Clinical & Policy Reports</h2>
          <p className="text-xs text-on-surface-variant mt-0.5">
            Structured summaries for rare disease diagnosis, pharmacogenomic warnings, and National Health Policy briefings.
          </p>
        </div>
        <button
          onClick={generateReport}
          disabled={busy}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-white text-xs font-semibold hover:bg-primary-container transition-all shadow-sm disabled:opacity-60"
        >
          <RefreshCw size={14} className={busy ? 'animate-spin' : ''} />
          <span>{busy ? 'Synthesizing...' : 'Generate National Policy Brief'}</span>
        </button>
      </div>

      {error && (
        <div className="p-3.5 rounded-lg bg-red-50 border border-red-200 text-red-700 text-xs">
          {error}
        </div>
      )}

      {/* Generated Report Display */}
      <div className="panel">
        <div className="flex items-center justify-between pb-3 mb-4 border-b border-outline-variant/30">
          <div className="flex items-center gap-2 text-xs font-bold text-on-surface">
            <FileCheck size={18} className="text-primary" />
            <span>EXECUTIVE EPIDEMIOLOGICAL BRIEF (MODULE 11)</span>
          </div>
          {brief && (
            <button
              onClick={() => window.print()}
              className="px-3 py-1 rounded bg-surface-container-low text-xs font-semibold text-primary hover:bg-surface-container transition-colors flex items-center gap-1.5"
            >
              <Printer size={14} />
              <span>Print / Save PDF</span>
            </button>
          )}
        </div>

        {brief ? (
          <div className="p-5 rounded-xl bg-surface-container-low/50 border border-outline-variant/30 text-xs font-mono whitespace-pre-wrap leading-relaxed text-on-surface overflow-x-auto">
            {brief}
          </div>
        ) : (
          <div className="py-12 text-center text-outline">
            <FileCheck size={36} className="mx-auto mb-2 opacity-50" />
            <p className="text-xs">No active report generated. Click "Generate National Policy Brief" above to compile data.</p>
          </div>
        )}
      </div>

      <CaseWorkflowPanel />
      <CaseReportPanel />
      <CaseBundlesPanel />
    </div>
  )
}
