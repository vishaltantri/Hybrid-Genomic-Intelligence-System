import React, { useEffect, useState } from 'react'
import { api } from '../../api.js'
import {
  Search,
  Users,
  Stethoscope,
  Pill,
  Network,
  X,
  ArrowRight,
  Command,
} from 'lucide-react'

export function GlobalSearchModal({ isOpen, onClose, onNavigate }) {
  const [query, setQuery] = useState('')
  const [patients, setPatients] = useState([])
  const [reference, setReference] = useState({ drugs: [], communities: [], states: [] })
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (isOpen) {
      setLoading(true)
      Promise.all([
        api.listPatients().catch(() => []),
        api.reference().catch(() => ({ drugs: [], communities: [], states: [] })),
      ])
        .then(([pts, ref]) => {
          setPatients(pts || [])
          setReference(ref || { drugs: [], communities: [], states: [] })
        })
        .finally(() => setLoading(false))
    }
  }, [isOpen])

  // Listen for Escape key
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && isOpen) {
        onClose()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, onClose])

  if (!isOpen) return null

  const q = query.trim().toLowerCase()

  // Filter patients
  const matchedPatients = q
    ? patients.filter(
        (p) =>
          p.patient_id?.toLowerCase().includes(q) ||
          p.state?.toLowerCase().includes(q) ||
          p.community?.toLowerCase().includes(q) ||
          p.extra?.notes?.toLowerCase().includes(q)
      ).slice(0, 4)
    : []

  // Filter drugs
  const matchedDrugs = q
    ? (reference.drugs || [])
        .filter((d) => (typeof d === 'string' ? d : d.name || '').toLowerCase().includes(q))
        .slice(0, 4)
    : []

  // Static common rare diseases recognized by the system
  const commonDiseases = [
    { id: 'ORPHA:90', name: 'Wilson Disease', gene: 'ATP7B' },
    { id: 'ORPHA:231', name: 'Spinal Muscular Atrophy', gene: 'SMN1' },
    { id: 'ORPHA:98909', name: 'Duchenne Muscular Dystrophy', gene: 'DMD' },
    { id: 'ORPHA:2312', name: 'Beta-Thalassemia', gene: 'HBB' },
    { id: 'ORPHA:58', name: 'Alkaptonuria', gene: 'HGD' },
  ]
  const matchedDiseases = q
    ? commonDiseases.filter(
        (d) =>
          d.name.toLowerCase().includes(q) ||
          d.id.toLowerCase().includes(q) ||
          d.gene.toLowerCase().includes(q)
      )
    : []

  const hasResults =
    matchedPatients.length > 0 || matchedDrugs.length > 0 || matchedDiseases.length > 0

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-20 p-4 bg-black/40 backdrop-blur-sm animate-in fade-in duration-150">
      <div
        className="w-full max-w-xl bg-white rounded-2xl shadow-2xl overflow-hidden border border-outline-variant/40 animate-in zoom-in-95 duration-150 flex flex-col max-h-[80vh]"
        role="dialog"
        aria-modal="true"
      >
        {/* Search Input Bar */}
        <div className="p-4 border-b border-outline-variant/30 flex items-center gap-3 bg-surface-container-low/30">
          <Search size={20} className="text-primary shrink-0" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search patients, diseases (Wilson, Thalassemia), drugs (Clopidogrel)..."
            className="w-full bg-transparent border-none outline-none text-sm font-body-md text-on-surface focus:ring-0 p-0"
            autoFocus
          />
          {query && (
            <button
              onClick={() => setQuery('')}
              className="p-1 rounded text-outline hover:text-on-surface text-xs"
            >
              Clear
            </button>
          )}
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-outline hover:text-on-surface hover:bg-surface-container transition-colors"
          >
            <X size={18} />
          </button>
        </div>

        {/* Search Results Area */}
        <div className="p-4 overflow-y-auto space-y-4">
          {!q ? (
            <div className="py-8 text-center text-xs text-outline space-y-2">
              <Command size={28} className="mx-auto text-outline/60 mb-1" />
              <div>Type to query the clinical intelligence registry.</div>
              <div className="flex flex-wrap justify-center gap-1.5 pt-2">
                <span className="px-2 py-0.5 rounded bg-surface-container-low text-[11px] font-mono">Wilson Disease</span>
                <span className="px-2 py-0.5 rounded bg-surface-container-low text-[11px] font-mono">Clopidogrel</span>
                <span className="px-2 py-0.5 rounded bg-surface-container-low text-[11px] font-mono">Reddy</span>
                <span className="px-2 py-0.5 rounded bg-surface-container-low text-[11px] font-mono">PT-</span>
              </div>
            </div>
          ) : !hasResults ? (
            <div className="py-8 text-center text-xs text-outline">
              No matching clinical entities found for "{query}".
            </div>
          ) : (
            <>
              {/* Matched Patients */}
              {matchedPatients.length > 0 && (
                <div>
                  <div className="text-[10px] font-bold text-outline uppercase font-mono tracking-wider mb-1.5">
                    Patients ({matchedPatients.length})
                  </div>
                  <div className="space-y-1.5">
                    {matchedPatients.map((p) => (
                      <div
                        key={p.patient_id}
                        onClick={() => {
                          onNavigate('patients')
                          onClose()
                        }}
                        className="p-2.5 rounded-lg bg-surface-container-low/60 hover:bg-surface-container border border-outline-variant/30 flex items-center justify-between cursor-pointer transition-colors"
                      >
                        <div className="flex items-center gap-2.5">
                          <Users size={16} className="text-primary shrink-0" />
                          <div>
                            <span className="font-mono font-bold text-xs text-primary">{p.patient_id}</span>
                            <span className="text-xs text-on-surface-variant ml-2">
                              {p.age_years ? `${p.age_years}y` : ''} · {p.state || 'India'} {p.community ? `(${p.community})` : ''}
                            </span>
                          </div>
                        </div>
                        <ArrowRight size={14} className="text-outline" />
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Matched Diseases */}
              {matchedDiseases.length > 0 && (
                <div>
                  <div className="text-[10px] font-bold text-outline uppercase font-mono tracking-wider mb-1.5">
                    Rare Diseases ({matchedDiseases.length})
                  </div>
                  <div className="space-y-1.5">
                    {matchedDiseases.map((d) => (
                      <div
                        key={d.id}
                        onClick={() => {
                          onNavigate('diagnosis')
                          onClose()
                        }}
                        className="p-2.5 rounded-lg bg-surface-container-low/60 hover:bg-surface-container border border-outline-variant/30 flex items-center justify-between cursor-pointer transition-colors"
                      >
                        <div className="flex items-center gap-2.5">
                          <Stethoscope size={16} className="text-secondary shrink-0" />
                          <div>
                            <span className="font-bold text-xs text-on-surface">{d.name}</span>
                            <span className="text-[11px] text-outline font-mono ml-2">
                              {d.id} · Gene: {d.gene}
                            </span>
                          </div>
                        </div>
                        <span className="text-[11px] font-semibold text-primary">Open in Diagnosis</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Matched Medications */}
              {matchedDrugs.length > 0 && (
                <div>
                  <div className="text-[10px] font-bold text-outline uppercase font-mono tracking-wider mb-1.5">
                    Pharmacogenomic Drugs ({matchedDrugs.length})
                  </div>
                  <div className="space-y-1.5">
                    {matchedDrugs.map((d, i) => {
                      const drugName = typeof d === 'string' ? d : d.name || ''
                      return (
                        <div
                          key={i}
                          onClick={() => {
                            onNavigate('pgx')
                            onClose()
                          }}
                          className="p-2.5 rounded-lg bg-surface-container-low/60 hover:bg-surface-container border border-outline-variant/30 flex items-center justify-between cursor-pointer transition-colors"
                        >
                          <div className="flex items-center gap-2.5">
                            <Pill size={16} className="text-tertiary shrink-0" />
                            <span className="font-bold text-xs text-on-surface capitalize">{drugName}</span>
                          </div>
                          <span className="text-[11px] font-semibold text-tertiary">Check PGx Risk</span>
                        </div>
                      )
                    })}
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer info */}
        <div className="px-4 py-2.5 bg-surface-container-low border-t border-outline-variant/30 text-[11px] text-outline flex items-center justify-between">
          <span>Navigate with mouse or keyboard</span>
          <kbd className="px-1.5 py-0.5 rounded bg-white border border-outline-variant/40 font-mono text-[10px]">ESC to close</kbd>
        </div>
      </div>
    </div>
  )
}
