import React, { useState } from 'react'
import { api } from '../api.js'
import { FileText, Sparkles, CheckCircle2, AlertCircle, ArrowRight } from 'lucide-react'

export default function PhenotypesView({ onNavigateToDiagnosis }) {
  const [text, setText] = useState('Bachhe ka vajan nahi badh raha, chalne mein dikkat, muscle kamzor hai, piliya ho gaya')
  const [loading, setLoading] = useState(false)
  const [nerResult, setNerResult] = useState(null)
  const [hpoResult, setHpoResult] = useState(null)
  const [error, setError] = useState(null)

  const handleAnalyze = async () => {
    if (!text.trim()) return
    setLoading(true)
    setError(null)
    setNerResult(null)
    setHpoResult(null)
    try {
      const [ner, hpo] = await Promise.all([
        api.ner({ text }),
        api.mapHpo({ text }),
      ])
      setNerResult(ner)
      setHpoResult(hpo)
    } catch (ex) {
      setError(ex.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold font-headline-sm text-on-surface">Phenotype & HPO Intelligence</h2>
        <p className="text-xs text-on-surface-variant mt-0.5">
          Multilingual clinical NLP engine with token-level language identification (Hindi, Hinglish, Tamil, English).
        </p>
      </div>

      {error && (
        <div className="p-3.5 rounded-lg bg-red-50 border border-red-200 text-red-700 text-xs">
          {error}
        </div>
      )}

      {/* Input Panel */}
      <div className="panel">
        <label>Clinical Note / Patient Observations (English, Hindi, or Hinglish)</label>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Enter symptoms, patient complaints, or consultation notes..."
        />
        <div className="mt-3 flex items-center justify-between">
          <div className="text-[11px] text-outline">
            Supports code-mixed terms: e.g. "vajan nahi badh raha", "daure", "piliya", "brown ring"
          </div>
          <button
            onClick={handleAnalyze}
            disabled={loading || !text.trim()}
            className="primary text-xs flex items-center gap-2"
          >
            {loading ? 'Analyzing Tokens...' : 'Extract Phenotypes'}
          </button>
        </div>
      </div>

      {/* Results */}
      {hpoResult && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Mapped HPO Profile */}
          <div className="panel">
            <h3 className="flex items-center justify-between">
              <span>Mapped HPO Terms ({hpoResult.hpo_profile?.length || 0})</span>
              {hpoResult.hpo_ids?.length > 0 && (
                <button
                  onClick={() => onNavigateToDiagnosis(text)}
                  className="text-xs font-semibold text-primary hover:underline flex items-center gap-1"
                >
                  <span>Use in Diagnosis</span>
                  <ArrowRight size={14} />
                </button>
              )}
            </h3>

            {hpoResult.hpo_profile?.length === 0 ? (
              <p className="text-xs text-outline italic">No standard HPO terms mapped from this text.</p>
            ) : (
              <div className="space-y-2">
                {hpoResult.hpo_profile.map((h, idx) => (
                  <div
                    key={idx}
                    className="p-3 rounded-lg bg-surface-container-low border border-outline-variant/30 flex items-center justify-between"
                  >
                    <div>
                      <div className="font-semibold text-xs text-on-surface">
                        {h.hpo_name || h.hpo_id}
                      </div>
                      <div className="text-[11px] text-primary font-mono">{h.hpo_id}</div>
                    </div>
                    <div className="text-right">
                      <span className="pill green text-xs">
                        {Math.round((h.confidence || 0) * 100)}% Match
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {hpoResult.unmapped_symptoms?.length > 0 && (
              <div className="mt-4 pt-3 border-t border-outline-variant/30">
                <span className="text-[11px] font-semibold text-amber-700 block mb-1">
                  Unmapped Phrasing (Queued for Active Learning):
                </span>
                <div className="flex flex-wrap gap-1.5">
                  {hpoResult.unmapped_symptoms.map((s, idx) => (
                    <span key={idx} className="pill amber text-[11px] font-mono">
                      {s}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* NLP Entity Extraction */}
          <div className="panel">
            <h3>Language ID & Clinical Entities</h3>
            {nerResult?.entities && (
              <div className="space-y-2">
                {nerResult.entities.map((ent, idx) => (
                  <div
                    key={idx}
                    className="p-2.5 rounded-lg bg-white border border-outline-variant/30 flex items-center justify-between text-xs"
                  >
                    <div>
                      <span className="font-medium text-on-surface">"{ent.text}"</span>
                      <span className="ml-2 pill tag text-[10px] font-mono">{ent.label}</span>
                    </div>
                    <span className="text-outline text-[11px] font-mono">
                      Lang: {ent.language || 'hi'}
                    </span>
                  </div>
                ))}
              </div>
            )}

            {hpoResult.lid_counts && (
              <div className="mt-4 pt-3 border-t border-outline-variant/30">
                <span className="text-[11px] font-semibold text-on-surface-variant block mb-1">
                  Token Language Distribution:
                </span>
                <div className="flex gap-4 text-xs font-mono">
                  {Object.entries(hpoResult.lid_counts).map(([lang, cnt]) => (
                    <div key={lang} className="text-on-surface-variant">
                      <b className="text-primary uppercase">{lang}:</b> {cnt} tokens
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
