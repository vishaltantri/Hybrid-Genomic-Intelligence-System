import React, { useState, useEffect, useRef } from 'react'
import { api, streamAssistantChat, consumeNavContext } from '../api.js'
import {
  Bot,
  Send,
  User,
  Sparkles,
  FileText,
  Dna,
  Layers,
  Globe2,
  Mic,
  MicOff,
  Volume2,
  VolumeX,
  RotateCcw,
  ShieldCheck,
  CheckCircle2,
  AlertCircle,
  ExternalLink,
  ChevronDown,
  ChevronUp,
  Languages
} from 'lucide-react'

export default function AssistantView({ onNavigateToDiagnosis, onNavigateToVariants, onNavigateToReport }) {
  // Messages & Stream State
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      content:
        'Welcome to the Genomera AI Assistant. I am your grounded clinical genomics copilot, connected directly to your patient phenotypes, ranked differential diagnoses, Phase 3B Variant Intelligence, and the Genomera Knowledge Graph.\n\nSelect a patient case or ask a question below to begin.',
      citations: [],
      timestamp: Date.now(),
    },
  ])
  const [inputValue, setInputValue] = useState('')
  const [isGenerating, setIsGenerating] = useState(false)
  const [conversationId, setConversationId] = useState(null)
  const [errorMessage, setErrorMessage] = useState(null)

  // Context Selection State
  const [patientId, setPatientId] = useState('')
  const [patientsList, setPatientsList] = useState([])
  const [analysesList, setAnalysesList] = useState([])
  const [selectedAnalysisId, setSelectedAnalysisId] = useState('')
  const [activeContextSummary, setActiveContextSummary] = useState(null)

  // Mode & Language
  const [mode, setMode] = useState('clinical') // 'clinical' or 'patient_friendly'
  const [language, setLanguage] = useState('en') // 'en' or 'hi'
  const [includeEvidence, setIncludeEvidence] = useState(false)
  const [graphNode, setGraphNode] = useState(null)
  const [dxIntel, setDxIntel] = useState(false)
  const [pgxCtx, setPgxCtx] = useState(false)

  // Voice Input (Web Speech API SpeechRecognition)
  const [isListening, setIsListening] = useState(false)
  const [speechSupported, setSpeechSupported] = useState(false)
  const recognitionRef = useRef(null)

  // Text-To-Speech (Web Speech API SpeechSynthesis)
  const [isSpeaking, setIsSpeaking] = useState(false)

  // Auto-scroll
  const messagesEndRef = useRef(null)

  useEffect(() => {
    const ctx = consumeNavContext('ai-assistant')
    if (ctx?.graph_node) {
      setGraphNode(ctx.graph_node)
      if (ctx.prompt) setInputValue(ctx.prompt)
    }
    if (ctx?.include_pgx && ctx.patient_id) {
      setPatientId(ctx.patient_id)
      setPgxCtx(true)
      if (ctx.prompt) setInputValue(ctx.prompt)
    }
    if (ctx?.include_diagnosis_intel && ctx.patient_id) {
      setPatientId(ctx.patient_id)
      setDxIntel(true)
      if (ctx.prompt) setInputValue(ctx.prompt)
    }
  }, [])

  useEffect(() => {
    loadPatientsAndAnalyses()
    setupSpeechRecognition()
  }, [])

  useEffect(() => {
    scrollToBottom()
  }, [messages, isGenerating])

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  const loadPatientsAndAnalyses = async () => {
    try {
      const [pts, analyses] = await Promise.allSettled([
        api.listPatients(),
        api.listVariantAnalyses(),
      ])
      if (pts.status === 'fulfilled' && pts.value) {
        setPatientsList(pts.value)
        if (pts.value.length > 0) setPatientId(pts.value[0].id)
      }
      if (analyses.status === 'fulfilled' && analyses.value) {
        setAnalysesList(analyses.value)
        if (analyses.value.length > 0) setSelectedAnalysisId(analyses.value[0].analysis_id)
      }
    } catch (err) {
      console.warn('Failed to load context sources:', err)
    }
  }

  // Setup Speech Recognition
  const setupSpeechRecognition = () => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition
    if (SpeechRecognition) {
      setSpeechSupported(true)
      const rec = new SpeechRecognition()
      rec.continuous = false
      rec.interimResults = false
      rec.lang = language === 'hi' ? 'hi-IN' : 'en-US'

      rec.onresult = (event) => {
        const transcript = event.results[0][0].transcript
        setInputValue((prev) => (prev ? `${prev} ${transcript}` : transcript))
        setIsListening(false)
      }

      rec.onerror = (event) => {
        console.warn('Speech recognition error:', event.error)
        setIsListening(false)
      }

      rec.onend = () => {
        setIsListening(false)
      }

      recognitionRef.current = rec
    }
  }

  const toggleListening = () => {
    if (!speechSupported || !recognitionRef.current) {
      setErrorMessage('Speech recognition is not supported in this browser.')
      return
    }

    if (isListening) {
      recognitionRef.current.stop()
      setIsListening(false)
    } else {
      setErrorMessage(null)
      try {
        recognitionRef.current.lang = language === 'hi' ? 'hi-IN' : 'en-US'
        recognitionRef.current.start()
        setIsListening(true)
      } catch (err) {
        console.error('Speech recognition start failed:', err)
        setIsListening(false)
      }
    }
  }

  // Text-to-speech speaker
  const handleSpeak = (text) => {
    if (!('speechSynthesis' in window)) return

    if (isSpeaking) {
      window.speechSynthesis.cancel()
      setIsSpeaking(false)
      return
    }

    const cleanText = text.replace(/[*_#`]/g, '')
    const utterance = new SpeechSynthesisUtterance(cleanText)
    utterance.lang = language === 'hi' ? 'hi-IN' : 'en-US'
    utterance.onend = () => setIsSpeaking(false)
    utterance.onerror = () => setIsSpeaking(false)

    setIsSpeaking(true)
    window.speechSynthesis.speak(utterance)
  }

  // Quick Action Prompts
  const handleQuickAction = (promptText, overrideMode = null, overrideLang = null) => {
    if (overrideMode) setMode(overrideMode)
    if (overrideLang) setLanguage(overrideLang)
    sendMessage(promptText, overrideMode || mode, overrideLang || language)
  }

  // Clear Chat Session
  const handleClearChat = async () => {
    if (conversationId) {
      try {
        await api.clearAssistantConversation(conversationId)
      } catch {
        /* ignore */
      }
    }
    setMessages([
      {
        role: 'assistant',
        content: 'Conversation history reset. How can I assist you with this clinical case?',
        citations: [],
        timestamp: Date.now(),
      },
    ])
    if (isSpeaking) {
      window.speechSynthesis.cancel()
      setIsSpeaking(false)
    }
  }

  // Send message with streaming
  const sendMessage = async (userText = inputValue, activeMode = mode, activeLang = language) => {
    const textToSend = userText.trim()
    if (!textToSend || isGenerating) return

    setErrorMessage(null)
    setInputValue('')
    setIsGenerating(true)

    // Append user message
    const newMsgUser = { role: 'user', content: textToSend, timestamp: Date.now() }
    setMessages((prev) => [...prev, newMsgUser])

    // Create placeholder assistant message
    const assistantIndex = messages.length + 1
    const newMsgAssistant = {
      role: 'assistant',
      content: '',
      citations: [],
      timestamp: Date.now(),
    }
    setMessages((prev) => [...prev, newMsgAssistant])

    let accumulatedContent = ''
    let accumulatedCitations = []

    const payload = {
      message: textToSend,
      conversation_id: conversationId,
      patient_id: patientId || undefined,
      analysis_id: selectedAnalysisId || undefined,
      mode: activeMode,
      language: activeLang,
      include_evidence: includeEvidence || undefined,
      graph_node: graphNode || undefined,
      include_diagnosis_intel: dxIntel || undefined,
      include_pgx: pgxCtx || undefined,
    }

    await streamAssistantChat(
      payload,
      // onChunk
      (delta) => {
        accumulatedContent += delta
        setMessages((prev) => {
          const next = [...prev]
          const last = next[next.length - 1]
          if (last && last.role === 'assistant') {
            last.content = accumulatedContent
          }
          return next
        })
      },
      // onCitations
      (citations, summary) => {
        accumulatedCitations = citations || []
        if (summary) setActiveContextSummary(summary)
        setMessages((prev) => {
          const next = [...prev]
          const last = next[next.length - 1]
          if (last && last.role === 'assistant') {
            last.citations = accumulatedCitations
          }
          return next
        })
      },
      // onDone
      (finalCitations) => {
        setIsGenerating(false)
        if (finalCitations && finalCitations.length > 0) {
          accumulatedCitations = finalCitations
        }
        setMessages((prev) => {
          const next = [...prev]
          const last = next[next.length - 1]
          if (last && last.role === 'assistant') {
            last.content = accumulatedContent
            last.citations = accumulatedCitations
          }
          return next
        })
      },
      // onError
      (err) => {
        setIsGenerating(false)
        setErrorMessage(err.message || 'Error communicating with the assistant.')
        setMessages((prev) => {
          const next = [...prev]
          const last = next[next.length - 1]
          if (last && last.role === 'assistant' && !last.content) {
            last.content =
              'The assistant is temporarily unavailable. Your clinical case data is preserved. Please try again shortly.'
          }
          return next
        })
      }
    )
  }

  return (
    <div className="space-y-4 max-w-7xl mx-auto">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-3 border-b border-outline-variant/30">
        <div>
          <div className="flex items-center gap-2">
            <span className="p-2 rounded-xl bg-primary/10 text-primary">
              <Bot size={22} />
            </span>
            <div>
              <h1 className="text-xl font-bold font-headline-sm text-on-surface">
                Genomera AI Assistant
              </h1>
              <p className="text-xs text-on-surface-variant">
                Context-aware clinical genomics copilot grounded in patient phenotypes, differential rankings, ACMG criteria, and the Knowledge Graph.
              </p>
            </div>
          </div>
        </div>

        {/* Controls: Mode, Language, Clear */}
        <div className="flex items-center gap-2 flex-wrap">
          {/* Mode Switcher */}
          <div className="flex items-center bg-surface-container-low p-1 rounded-xl border border-outline-variant/40">
            <button
              onClick={() => setMode('clinical')}
              className={`px-3 py-1 rounded-lg text-xs font-semibold transition-all ${
                mode === 'clinical'
                  ? 'bg-primary text-white shadow-sm'
                  : 'text-on-surface-variant hover:text-on-surface'
              }`}
            >
              Clinical Mode
            </button>
            <button
              onClick={() => setMode('patient_friendly')}
              className={`px-3 py-1 rounded-lg text-xs font-semibold transition-all ${
                mode === 'patient_friendly'
                  ? 'bg-secondary text-white shadow-sm'
                  : 'text-on-surface-variant hover:text-on-surface'
              }`}
            >
              Patient-Friendly
            </button>
          </div>

          <label className="flex items-center gap-1.5 text-xs font-semibold text-on-surface-variant bg-surface-container-low px-2.5 py-1.5 rounded-xl border border-outline-variant/40" title="Retrieve real PubMed literature for this question; only retrieved PMIDs may be cited">
            <input type="checkbox" aria-label="Include literature evidence" checked={includeEvidence} onChange={(e) => setIncludeEvidence(e.target.checked)} />
            Literature
          </label>

          {graphNode && (
            <span className="flex items-center gap-1.5 text-xs font-semibold text-primary bg-primary/5 px-2.5 py-1.5 rounded-xl border border-primary/30" data-testid="graph-chip">
              Graph node: {graphNode}
              <button aria-label="Remove graph node" onClick={() => setGraphNode(null)} className="text-outline">×</button>
            </span>
          )}

          {/* Language Selector */}
          <div className="flex items-center bg-surface-container-low p-1 rounded-xl border border-outline-variant/40">
            <button
              onClick={() => setLanguage('en')}
              className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition-all ${
                language === 'en'
                  ? 'bg-surface-container-highest text-primary shadow-sm font-bold'
                  : 'text-on-surface-variant hover:text-on-surface'
              }`}
            >
              EN
            </button>
            <button
              onClick={() => setLanguage('hi')}
              className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition-all ${
                language === 'hi'
                  ? 'bg-surface-container-highest text-primary shadow-sm font-bold'
                  : 'text-on-surface-variant hover:text-on-surface'
              }`}
            >
              हिंदी
            </button>
          </div>

          <button
            onClick={handleClearChat}
            className="p-2 rounded-xl bg-surface-container-low border border-outline-variant/40 text-on-surface-variant hover:text-primary transition-colors"
            title="Reset conversation"
          >
            <RotateCcw size={16} />
          </button>
        </div>
      </div>

      {/* Case Context Indicator Bar */}
      <div className="panel p-3 bg-surface-container-lowest border-outline-variant/30 flex flex-wrap items-center justify-between gap-3 text-xs">
        <div className="flex items-center gap-3 flex-wrap">
          <div className="flex items-center gap-1.5 font-semibold text-on-surface">
            <ShieldCheck size={16} className="text-primary" />
            <span>Active Case Context:</span>
          </div>

          <div className="flex items-center gap-1.5">
            <span className="text-[11px] text-on-surface-variant">Patient:</span>
            <select
              value={patientId}
              onChange={(e) => setPatientId(e.target.value)}
              className="px-2.5 py-1 text-xs rounded-lg border border-outline bg-surface text-on-surface focus:outline-none"
            >
              <option value="">Unlinked (General Genomics)</option>
              {patientsList.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name || p.id} ({p.state || 'India'})
                </option>
              ))}
            </select>
          </div>

          <div className="flex items-center gap-1.5">
            <span className="text-[11px] text-on-surface-variant">Variant Run:</span>
            <select
              value={selectedAnalysisId}
              onChange={(e) => setSelectedAnalysisId(e.target.value)}
              className="px-2.5 py-1 text-xs rounded-lg border border-outline bg-surface text-on-surface focus:outline-none"
            >
              <option value="">Latest Session Seed / Run</option>
              {analysesList.map((a) => (
                <option key={a.analysis_id} value={a.analysis_id}>
                  {a.analysis_id} ({a.filename.slice(0, 16)})
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="flex items-center gap-2 text-[11px] text-on-surface-variant">
          <span className="inline-flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
            Grounded Retrieval Active
          </span>
          {activeContextSummary?.target_variant && (
            <span className="font-mono text-primary font-semibold">
              [{activeContextSummary.target_gene || 'Variant Target'}]
            </span>
          )}
        </div>
      </div>

      {/* Error Notice */}
      {errorMessage && (
        <div className="p-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-xs flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertCircle size={16} className="shrink-0" />
            <span>{errorMessage}</span>
          </div>
          <button onClick={() => setErrorMessage(null)} className="text-red-400 hover:text-red-600">
            ×
          </button>
        </div>
      )}

      {/* Main Chat Workspace */}
      <div className="panel p-0 flex flex-col h-[560px] overflow-hidden bg-surface">
        {/* Messages Scroll Area */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {messages.map((msg, idx) => {
            const isUser = msg.role === 'user'
            return (
              <div
                key={idx}
                className={`flex gap-3 max-w-3xl ${
                  isUser ? 'ml-auto flex-row-reverse' : 'mr-auto'
                }`}
              >
                {/* Avatar */}
                <div
                  className={`w-8 h-8 rounded-xl flex items-center justify-center shrink-0 text-white ${
                    isUser ? 'bg-primary' : 'bg-secondary'
                  }`}
                >
                  {isUser ? <User size={16} /> : <Bot size={16} />}
                </div>

                {/* Message Bubble */}
                <div
                  className={`space-y-2 rounded-2xl p-4 text-xs leading-relaxed shadow-xs ${
                    isUser
                      ? 'bg-primary text-white rounded-tr-none'
                      : 'bg-surface-container-low text-on-surface border border-outline-variant/30 rounded-tl-none'
                  }`}
                >
                  {/* Message Content */}
                  <div className="whitespace-pre-wrap">{msg.content}</div>

                  {/* Grounded Evidence Citations (if present) */}
                  {!isUser && msg.citations && msg.citations.length > 0 && (
                    <div className="mt-3 pt-3 border-t border-outline-variant/30 space-y-1.5">
                      <div className="text-[10px] font-semibold text-on-surface-variant uppercase tracking-wider flex items-center gap-1">
                        <CheckCircle2 size={12} className="text-primary" />
                        <span>Grounded Evidence Citations:</span>
                      </div>
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
                        {msg.citations.map((c, cIdx) => (
                          <div
                            key={cIdx}
                            className="p-2 rounded-lg bg-surface border border-outline-variant/30 text-[11px]"
                          >
                            <div className="font-semibold text-primary">{c.source_type}</div>
                            <div className="font-mono text-[10px] text-on-surface">{c.identifier}</div>
                            <div className="text-[10px] text-on-surface-variant truncate">
                              {c.summary}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Action Bar on Assistant Turn */}
                  {!isUser && msg.content && (
                    <div className="flex items-center justify-between pt-1 text-[10px] text-on-surface-variant">
                      <span>{new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                      <button
                        onClick={() => handleSpeak(msg.content)}
                        className="hover:text-primary transition-colors flex items-center gap-1"
                        title="Read aloud"
                      >
                        {isSpeaking ? <VolumeX size={13} /> : <Volume2 size={13} />}
                        <span>{isSpeaking ? 'Stop Audio' : 'Speak'}</span>
                      </button>
                    </div>
                  )}
                </div>
              </div>
            )
          })}

          {isGenerating && (
            <div className="flex gap-3 max-w-xl mr-auto items-center">
              <div className="w-8 h-8 rounded-xl bg-secondary text-white flex items-center justify-center shrink-0">
                <Bot size={16} />
              </div>
              <div className="p-3 rounded-2xl bg-surface-container-low border border-outline-variant/30 text-xs flex items-center gap-2 text-on-surface-variant">
                <div className="w-3.5 h-3.5 border-2 border-primary/20 border-t-primary rounded-full animate-spin"></div>
                <span>Evaluating clinical evidence and synthesizing grounded response...</span>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Quick Action Clinical Suggestions */}
        <div className="px-4 py-2 border-t border-outline-variant/20 bg-surface-container-lowest/50 flex items-center gap-1.5 overflow-x-auto text-[11px]">
          <span className="text-[10px] font-semibold text-on-surface-variant uppercase shrink-0 mr-1 flex items-center gap-1">
            <Sparkles size={11} className="text-primary" /> Suggestions:
          </span>
          <button
            onClick={() => handleQuickAction('Why is the top variant ranked first?')}
            disabled={isGenerating}
            className="px-2.5 py-1 rounded-full bg-surface border border-outline-variant/40 hover:border-primary text-on-surface shrink-0 hover:bg-surface-container-low transition-colors"
          >
            Why is the top variant ranked first?
          </button>
          <button
            onClick={() => handleQuickAction('Explain the evaluated ACMG criteria')}
            disabled={isGenerating}
            className="px-2.5 py-1 rounded-full bg-surface border border-outline-variant/40 hover:border-primary text-on-surface shrink-0 hover:bg-surface-container-low transition-colors"
          >
            Explain evaluated ACMG criteria
          </button>
          <button
            onClick={() => handleQuickAction('Why is this disease ranked top in differential diagnosis?')}
            disabled={isGenerating}
            className="px-2.5 py-1 rounded-full bg-surface border border-outline-variant/40 hover:border-primary text-on-surface shrink-0 hover:bg-surface-container-low transition-colors"
          >
            Explain differential diagnosis ranking
          </button>
          <button
            onClick={() => handleQuickAction('Explain this case in patient-friendly terms', 'patient_friendly')}
            disabled={isGenerating}
            className="px-2.5 py-1 rounded-full bg-surface border border-outline-variant/40 hover:border-secondary text-secondary shrink-0 hover:bg-secondary/5 transition-colors font-medium"
          >
            Explain for patient
          </button>
          <button
            onClick={() => handleQuickAction('इस केस के प्रमुख निष्कर्ष हिंदी में समझाएं', null, 'hi')}
            disabled={isGenerating}
            className="px-2.5 py-1 rounded-full bg-surface border border-outline-variant/40 hover:border-primary text-primary shrink-0 hover:bg-primary/5 transition-colors font-medium"
          >
            हिंदी में समझाइए
          </button>
        </div>

        {/* Input Bar */}
        <div className="p-3 border-t border-outline-variant/30 bg-surface-container-low flex items-center gap-2">
          {/* Voice Input Button */}
          <button
            onClick={toggleListening}
            className={`p-2.5 rounded-xl border transition-all ${
              isListening
                ? 'bg-rose-50 border-rose-300 text-rose-600 animate-pulse'
                : 'bg-surface border-outline-variant/50 text-on-surface-variant hover:text-primary'
            }`}
            title={speechSupported ? (isListening ? 'Stop listening' : 'Start voice input') : 'Voice input not supported'}
          >
            {isListening ? <MicOff size={16} /> : <Mic size={16} />}
          </button>

          {/* Text Input */}
          <input
            type="text"
            placeholder={
              language === 'hi'
                ? 'इस जीनोमिक केस के बारे में पूछें...'
                : mode === 'patient_friendly'
                ? 'Ask a question in patient-friendly terms...'
                : 'Ask about variants, ACMG evidence, differential diagnosis...'
            }
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                sendMessage()
              }
            }}
            disabled={isGenerating}
            className="flex-1 px-4 py-2.5 text-xs rounded-xl border border-outline bg-surface text-on-surface placeholder:text-on-surface-variant/50 focus:outline-none focus:ring-1 focus:ring-primary"
          />

          {/* Send Button */}
          <button
            onClick={() => sendMessage()}
            disabled={!inputValue.trim() || isGenerating}
            className="px-4 py-2.5 rounded-xl bg-primary text-white text-xs font-semibold hover:bg-primary-container transition-all shadow-sm disabled:opacity-50 flex items-center gap-1.5"
          >
            <Send size={14} />
            <span className="hidden sm:inline">Send</span>
          </button>
        </div>
      </div>
    </div>
  )
}
