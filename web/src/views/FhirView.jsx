import React, { useEffect, useState } from 'react'
import { api } from '../api.js'
import { Server, CheckCircle2, ShieldCheck, FileCode } from 'lucide-react'

export default function FhirView() {
  const [metadata, setMetadata] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.fhirMetadata()
      .then((data) => setMetadata(data))
      .catch((ex) => setError(ex.message))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold font-headline-sm text-on-surface">HL7 FHIR Interoperability Suite</h2>
        <p className="text-xs text-on-surface-variant mt-0.5">
          EHR & EMR integration endpoint adhering to HL7 FHIR Release 4 and ABDM (Ayushman Bharat Digital Mission) guidelines.
        </p>
      </div>

      {error && (
        <div className="p-3.5 rounded-lg bg-red-50 border border-red-200 text-red-700 text-xs">
          {error}
        </div>
      )}

      {/* Integration Badges */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="p-4 rounded-xl bg-white border border-outline-variant/40 shadow-xs flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-surface-container flex items-center justify-center text-primary">
            <Server size={20} />
          </div>
          <div>
            <div className="text-xs font-bold text-on-surface">FHIR R4 Gateway</div>
            <div className="text-[11px] text-secondary font-mono font-semibold">Active & Conforming</div>
          </div>
        </div>

        <div className="p-4 rounded-xl bg-white border border-outline-variant/40 shadow-xs flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-surface-container flex items-center justify-center text-secondary">
            <ShieldCheck size={20} />
          </div>
          <div>
            <div className="text-xs font-bold text-on-surface">ABDM Compliance</div>
            <div className="text-[11px] text-outline font-mono">M1 / M2 Ready</div>
          </div>
        </div>

        <div className="p-4 rounded-xl bg-white border border-outline-variant/40 shadow-xs flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-surface-container flex items-center justify-center text-tertiary">
            <FileCode size={20} />
          </div>
          <div>
            <div className="text-xs font-bold text-on-surface">Bundle Exporter</div>
            <div className="text-[11px] text-primary font-mono">JSON / NDJSON</div>
          </div>
        </div>
      </div>

      {/* Capability Statement */}
      <div className="panel">
        <h3>FHIR CapabilityStatement (`/api/v1/emr/fhir/metadata`)</h3>
        {loading ? (
          <div className="text-xs text-outline">Loading FHIR conformance statement...</div>
        ) : (
          <pre className="p-4 rounded-lg bg-surface-container-low text-xs font-mono text-on-surface overflow-x-auto max-h-96">
            {JSON.stringify(metadata, null, 2)}
          </pre>
        )}
      </div>
    </div>
  )
}
