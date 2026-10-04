import React, { useEffect, useState } from 'react'
import { api } from '../api.js'
import { ShieldAlert, CheckCircle2, AlertTriangle, AlertOctagon } from 'lucide-react'

export default function AshaView() {
  const [questionnaire, setQuestionnaire] = useState([])
  const [loading, setLoading] = useState(true)
  const [transcript, setTranscript] = useState('Bachhe ko 3 mahine se bukhar hai, achanak daure aane lage, vajan nahi badh raha')
  const [triageResult, setTriageResult] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.triageQuestionnaire()
      .then((data) => setQuestionnaire(data?.questions || []))
      .catch((ex) => setError(ex.message))
      .finally(() => setLoading(false))
  }, [])

  const handleTriageText = async () => {
    setBusy(true)
    setError(null)
    setTriageResult(null)
    try {
      const res = await api.triageText({ transcript, state: 'Uttar Pradesh' })
      setTriageResult(res)
    } catch (ex) {
      setError(ex.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold font-headline-sm text-on-surface">ASHA Community Triage Module</h2>
        <p className="text-xs text-on-surface-variant mt-0.5">
          Offline-first rural health screening protocol for frontline health workers (ASHA / ANM).
        </p>
      </div>

      {error && (
        <div className="p-3.5 rounded-lg bg-red-50 border border-red-200 text-red-700 text-xs">
          {error}
        </div>
      )}

      {/* Triage Simulation Panel */}
      <div className="panel">
        <h3>Transcript / Symptom Triage (Module 9)</h3>
        <label>ASHA Worker Voice Transcript or Clinical Observations</label>
        <textarea
          value={transcript}
          onChange={(e) => setTranscript(e.target.value)}
          placeholder="Enter village symptom report in Hindi / Hinglish..."
        />
        <div className="mt-3 flex justify-end">
          <button
            onClick={handleTriageText}
            disabled={busy || !transcript.trim()}
            className="primary text-xs"
          >
            {busy ? 'Triaging...' : 'Run Triage Engine'}
          </button>
        </div>
      </div>

      {/* Triage Outcome */}
      {triageResult && (
        <div className="panel">
          <div className="flex items-center gap-3 mb-4">
            {triageResult.triage_level === 'red' && (
              <div className="p-2 rounded-lg bg-red-100 text-red-700 flex items-center gap-2">
                <AlertOctagon size={24} />
                <span className="font-bold text-sm uppercase">RED FLAG — IMMEDIATE REFERRAL</span>
              </div>
            )}
            {triageResult.triage_level === 'yellow' && (
              <div className="p-2 rounded-lg bg-amber-100 text-amber-700 flex items-center gap-2">
                <AlertTriangle size={24} />
                <span className="font-bold text-sm uppercase">YELLOW — DISTRICT CLINIC FOLLOW-UP</span>
              </div>
            )}
            {triageResult.triage_level === 'green' && (
              <div className="p-2 rounded-lg bg-green-100 text-green-700 flex items-center gap-2">
                <CheckCircle2 size={24} />
                <span className="font-bold text-sm uppercase">GREEN — ROUTINE MONITORING</span>
              </div>
            )}
          </div>

          <div className="text-xs space-y-2">
            <div><b>Triage Summary:</b> {triageResult.explanation || 'Evaluated against rare disease pediatric red flags.'}</div>
            {triageResult.triggers?.length > 0 && (
              <div>
                <b>Triggers Identified:</b>{' '}
                {triageResult.triggers.map((t, idx) => (
                  <span key={idx} className="pill red text-xs mr-1 font-mono">{t}</span>
                ))}
              </div>
            )}
            {triageResult.recommendation && (
              <div className="p-3 rounded-lg bg-surface-container-low text-on-surface mt-2">
                <b>Actionable Directive:</b> {triageResult.recommendation}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Structured Questionnaire Schema Preview */}
      <div className="panel">
        <h3>Standardized RBSK / ASHA Questionnaire Schema ({questionnaire.length} questions)</h3>
        {loading ? (
          <div className="text-xs text-outline">Loading questionnaire schema...</div>
        ) : (
          <div className="space-y-2 max-h-72 overflow-y-auto pr-2">
            {questionnaire.slice(0, 10).map((q, idx) => (
              <div key={idx} className="p-3 rounded-lg bg-surface-container-low text-xs border border-outline-variant/30 flex justify-between items-center">
                <div>
                  <div className="font-semibold text-on-surface">{q.prompt_hi || q.prompt_en || q.text}</div>
                  {q.prompt_en && <div className="text-[11px] text-outline">{q.prompt_en}</div>}
                </div>
                <span className="pill tag text-[10px] uppercase font-mono">{q.category || 'General'}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
