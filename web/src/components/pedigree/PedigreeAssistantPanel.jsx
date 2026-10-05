import React, { useEffect, useState } from 'react'
import { Bot, Send } from 'lucide-react'
import { api } from '../../api.js'

const QUESTIONS = [
  'What inheritance pattern does this family show?',
  'Why is this variant consistent with autosomal dominant inheritance?',
  'Could this variant be de novo?',
  'Which family members support segregation?',
]

/** Questions go to the existing AI Assistant backend with the case's pedigree analysis attached server-side. */
export default function PedigreeAssistantPanel({ caseId, variantKey }) {
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [reply, setReply] = useState(null)
  useEffect(() => { setMessage(''); setReply(null); setError(null) }, [caseId])

  const send = async () => {
    if (!message.trim()) return
    setBusy(true)
    setError(null)
    try {
      setReply(await api.assistantChat({ message: message.trim(), patient_id: caseId, include_pedigree: true, pedigree_variant_key: variantKey || undefined }))
    } catch (ex) {
      setReply(null)
      setError(ex.message)
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="rounded-xl border border-outline-variant/40 bg-white p-4 space-y-3" data-testid="pedigree-assistant">
      <div className="flex items-center gap-2 text-xs font-bold text-on-surface"><Bot size={15} className="text-primary" /> Ask the AI Assistant about this family
        {variantKey && <span className="text-[10px] font-mono text-outline">variant {variantKey}</span>}</div>
      <div className="flex flex-wrap gap-2">
        {QUESTIONS.map((q) => <button key={q} onClick={() => setMessage(q)} className="px-2.5 py-1 rounded-full bg-surface-container text-[11px] hover:bg-primary/10">{q}</button>)}
      </div>
      <div className="flex gap-2">
        <input aria-label="Question about this pedigree" className="flex-1 text-xs rounded-lg border border-outline-variant px-3 py-2" value={message}
          onChange={(e) => setMessage(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && send()} placeholder="Ask about inheritance, segregation, de novo status…" />
        <button onClick={send} disabled={busy || !message.trim()} className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-primary text-white text-xs font-semibold disabled:opacity-60"><Send size={13} /> {busy ? 'Asking…' : 'Ask'}</button>
      </div>
      {error && <div role="alert" className="text-xs rounded-lg border border-red-200 bg-red-50 text-red-800 px-3 py-2">{error}</div>}
      {reply && (
        <div className="space-y-2" data-testid="pedigree-assistant-reply">
          <div className="text-xs rounded-lg bg-surface-container-low p-3 whitespace-pre-wrap">{reply.response}</div>
          <p className="text-[11px] text-on-surface-variant">Grounded in the recorded pedigree{reply.context_summary?.pedigree_variant ? ` and the analysis of ${reply.context_summary.pedigree_variant}` : ''}. Sources: {reply.citations.map((c) => `${c.source_type} ${c.identifier}`).join('; ')}</p>
        </div>
      )}
    </div>
  )
}
