import React, { useEffect, useState } from 'react'
import { Bot, Send } from 'lucide-react'
import { api } from '../../api.js'
import { Note } from './TwinSections.jsx'

/**
 * Asks the existing AI Assistant backend a question grounded in the selected patient's Twin
 * (and optionally one scenario). The Twin context is built server-side from live data; nothing
 * is assembled in the browser.
 */
export default function TwinAssistantPanel({ patientId, analysisId, scenario, prefill, selectedVariantId }) {
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [reply, setReply] = useState(null)

  // Different patient => no answer or draft carried over.
  useEffect(() => {
    setMessage('')
    setReply(null)
    setError(null)
  }, [patientId])

  useEffect(() => {
    if (prefill && prefill.text) setMessage(prefill.text)
  }, [prefill])

  const send = async (text) => {
    const q = (text ?? message).trim()
    if (!q) return
    setBusy(true)
    setError(null)
    try {
      const res = await api.assistantChat({
        message: q,
        patient_id: patientId,
        analysis_id: analysisId || undefined,
        include_twin: true,
        twin_scenario_id: scenario?.scenario_id || undefined,
        selected_variant_id: selectedVariantId || undefined,
      })
      setReply({ question: q, ...res })
    } catch (ex) {
      setReply(null)
      setError(ex.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div id="twin-assistant-anchor" className="rounded-xl border border-outline-variant/40 bg-white p-4 space-y-3" data-testid="twin-assistant">
      <div className="flex items-center gap-2 text-xs font-bold text-on-surface">
        <Bot size={15} className="text-primary" /> Ask the AI Assistant about this Twin
        {scenario && <span className="text-[10px] font-mono text-outline">+ scenario {scenario.scenario_id}</span>}
      </div>
      <div className="flex flex-wrap gap-2">
        <button className="px-2.5 py-1 rounded-full bg-surface-container text-[11px] hover:bg-primary/10" onClick={() => setMessage("Explain this patient's Digital Twin.")}>
          Explain this Twin
        </button>
        {selectedVariantId && (
          <button className="px-2.5 py-1 rounded-full bg-surface-container text-[11px] hover:bg-primary/10" onClick={() => setMessage("Why is this patient's selected variant important?")}>
            Why is the selected variant important?
          </button>
        )}
        <button
          disabled={!scenario}
          className="px-2.5 py-1 rounded-full bg-surface-container text-[11px] hover:bg-primary/10 disabled:opacity-50"
          onClick={() => setMessage('Why did the scenario change the diagnosis ranking?')}
        >
          Why did the scenario change the ranking?
        </button>
        <button
          disabled={!scenario}
          className="px-2.5 py-1 rounded-full bg-surface-container text-[11px] hover:bg-primary/10 disabled:opacity-50"
          onClick={() => setMessage('What changed between baseline and this scenario?')}
        >
          What changed vs baseline?
        </button>
      </div>
      <div className="flex gap-2">
        <input
          aria-label="Question for the AI Assistant"
          className="flex-1 text-xs rounded-lg border border-outline-variant px-3 py-2"
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && send()}
          placeholder="Ask about phenotypes, variants, diagnosis or the selected scenario…"
        />
        <button onClick={() => send()} disabled={busy || !message.trim()} className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-primary text-white text-xs font-semibold disabled:opacity-60">
          <Send size={13} /> {busy ? 'Asking…' : 'Ask'}
        </button>
      </div>
      {error && <div role="alert" className="text-xs rounded-lg border border-red-200 bg-red-50 text-red-800 px-3 py-2">{error}</div>}
      {reply && (
        <div className="space-y-2" data-testid="twin-assistant-reply">
          <div className="text-xs rounded-lg bg-surface-container-low p-3 whitespace-pre-wrap">{reply.response}</div>
          <Note>
            Grounded in Twin snapshot <span className="font-mono">{reply.context_summary?.twin_snapshot || 'n/a'}</span>
            {reply.context_summary?.twin_scenario && <> and scenario <span className="font-mono">{reply.context_summary.twin_scenario}</span></>}.
            Sources: {reply.citations.map((c) => `${c.source_type} ${c.identifier}`).join('; ')}
          </Note>
        </div>
      )}
    </div>
  )
}
