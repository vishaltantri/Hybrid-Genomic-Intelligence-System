import React, { useEffect, useMemo, useRef, useState } from 'react'
import { Search, X, ArrowRight } from 'lucide-react'
import { api, setNavContext } from '../../api.js'

const GROUPS = [
  ['commands', 'Go to'], ['cases', 'Cases'], ['variants', 'Variants'], ['diseases', 'Diseases'],
  ['genes', 'Genes'], ['phenotypes', 'Phenotypes'], ['reports', 'Reports'], ['referrals', 'Referrals'],
]

export function GlobalSearchModal({ isOpen, onClose, onNavigate, debounceMs = 200 }) {
  const [query, setQuery] = useState('')
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)
  const [active, setActive] = useState(0)
  const seq = useRef(0)

  useEffect(() => { if (!isOpen) { setQuery(''); setData(null); setError(null); setActive(0) } }, [isOpen])

  useEffect(() => {
    const q = query.trim()
    if (!isOpen || q.length < 2) { setData(null); setError(null); setLoading(false); return }
    const id = ++seq.current
    setLoading(true)
    const t = setTimeout(async () => {
      try {
        const r = await api.searchGlobal(q)
        if (id === seq.current) { setData(r); setError(null); setActive(0) }
      } catch (e) {
        if (id === seq.current) { setError(e.message); setData(null) }
      } finally { if (id === seq.current) setLoading(false) }
    }, debounceMs)
    return () => clearTimeout(t)
  }, [query, isOpen, debounceMs])

  const flat = useMemo(() => (data ? GROUPS.flatMap(([k]) => data.results[k] || []) : []), [data])

  if (!isOpen) return null

  const choose = (h) => {
    setNavContext(h.route, { ...h.context, type: h.type, id: h.id, ...(h.type === 'gene' ? { gene: h.id } : {}) })
    onNavigate(h.route)
    onClose()
  }
  const onKeyDown = (e) => {
    if (e.key === 'Escape') onClose()
    else if (e.key === 'ArrowDown') { e.preventDefault(); setActive((a) => Math.min(a + 1, Math.max(flat.length - 1, 0))) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)) }
    else if (e.key === 'Enter' && flat[active]) { e.preventDefault(); choose(flat[active]) }
  }

  let idx = -1
  const q = query.trim()
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-20 p-4 bg-slate-900/30" onKeyDown={onKeyDown}>
      <div role="dialog" aria-modal="true" aria-label="Command palette" className="w-full max-w-xl bg-white rounded-2xl shadow-2xl overflow-hidden border border-outline-variant/40 flex flex-col max-h-[80vh]">
        <div className="p-4 border-b border-outline-variant/30 flex items-center gap-3">
          <Search size={20} className="text-primary shrink-0" />
          <input autoFocus aria-label="Search" value={query} onChange={(e) => setQuery(e.target.value)}
            placeholder="Search cases, variants, diseases, genes, reports, or go to a page"
            className="w-full bg-transparent border-none outline-none text-sm text-on-surface focus:ring-0 p-0" />
          <button aria-label="Close search" onClick={onClose} className="p-1.5 rounded-lg text-outline hover:text-on-surface hover:bg-surface-container"><X size={18} /></button>
        </div>
        <div className="p-3 overflow-y-auto space-y-3 text-xs">
          {error && <div role="alert" className="rounded-lg border border-red-200 bg-red-50 text-red-800 px-3 py-2">{error}</div>}
          {q.length < 2 && !error && <div className="py-6 text-center text-outline">Type at least 2 characters. Results only include what your role may access.</div>}
          {loading && <div className="text-outline">Searching…</div>}
          {data && data.total === 0 && !loading && (
            <div data-testid="no-match" className="py-6 text-center text-outline">{data.state === 'Not available' ? 'Search is not available for these sources right now.' : `No matching result for "${data.query}".`}</div>
          )}
          {data && data.unavailable?.length > 0 && <div className="text-amber-800">Not available: {data.unavailable.join(', ')}.</div>}
          {data && GROUPS.map(([key, title]) => (data.results[key] || []).length > 0 && (
            <div key={key}>
              <div className="text-[10px] font-bold text-outline uppercase tracking-wider mb-1">{title}</div>
              <div className="space-y-1" role="listbox" aria-label={title}>
                {data.results[key].map((h) => {
                  idx += 1
                  const mine = idx
                  return (
                    <div key={`${key}-${h.id}-${mine}`} role="option" aria-selected={mine === active} onMouseEnter={() => setActive(mine)} onClick={() => choose(h)}
                      className={`p-2 rounded-lg border flex items-center justify-between cursor-pointer ${mine === active ? 'bg-surface-container border-primary/40' : 'border-outline-variant/30'}`}>
                      <div><span className="font-semibold text-on-surface">{h.label}</span>{h.sub && <span className="text-on-surface-variant ml-2">{h.sub}</span>}</div>
                      <ArrowRight size={14} className="text-outline" />
                    </div>
                  )
                })}
              </div>
            </div>
          ))}
        </div>
        <div className="px-4 py-2 bg-surface-container-low border-t border-outline-variant/30 text-[11px] text-outline flex justify-between">
          <span>Up/Down to move, Enter to open</span><span>Esc to close</span>
        </div>
      </div>
    </div>
  )
}
