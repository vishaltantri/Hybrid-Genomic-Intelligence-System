import React, { useCallback, useEffect, useState } from 'react'
import { Bell } from 'lucide-react'
import { api } from '../api.js'

export default function NotificationBell({ pollMs = 60000 }) {
  const [open, setOpen] = useState(false)
  const [items, setItems] = useState([])
  const [unread, setUnread] = useState(0)
  const [error, setError] = useState(null)

  const refresh = useCallback(async () => {
    try {
      const [c, list] = await Promise.all([api.notifCount(), api.notifList()])
      setUnread(c.unread); setItems(list); setError(null)
    } catch (e) { setError(e.message) }
  }, [])

  useEffect(() => {
    refresh()
    const t = pollMs > 0 ? setInterval(refresh, pollMs) : null
    return () => t && clearInterval(t)
  }, [refresh, pollMs])

  const markOne = async (n) => { if (!n.read_utc) { try { await api.notifRead(n.id); await refresh() } catch (e) { setError(e.message) } } }
  const markAll = async () => { try { await api.notifReadAll(); await refresh() } catch (e) { setError(e.message) } }

  return (
    <div className="relative" onKeyDown={(e) => e.key === 'Escape' && setOpen(false)}>
      <button
        aria-label={`Notifications, ${unread} unread`}
        aria-expanded={open}
        onClick={() => { setOpen(!open); if (!open) refresh() }}
        className="relative p-2 rounded-lg text-outline hover:text-on-surface hover:bg-surface-container-low transition-colors"
      >
        <Bell size={18} />
        {unread > 0 && (
          <span data-testid="notif-badge" className="absolute -top-0.5 -right-0.5 min-w-[16px] h-4 px-1 rounded-full bg-secondary text-white text-[10px] font-bold flex items-center justify-center">{unread}</span>
        )}
      </button>
      {open && (
        <div role="dialog" aria-label="Notifications" className="absolute right-0 mt-2 w-80 max-h-96 overflow-y-auto rounded-xl bg-white border border-outline-variant/40 shadow-lg p-3 text-xs space-y-2 z-40">
          <div className="flex items-center justify-between">
            <b>Notifications</b>
            <button onClick={markAll} disabled={unread === 0} className="text-primary underline disabled:opacity-40">Mark all as read</button>
          </div>
          {error && <div role="alert" className="text-red-700">{error}</div>}
          {items.length === 0 ? <p className="text-on-surface-variant">No notifications.</p> : (
            <ul className="space-y-2">{items.map((n) => (
              <li key={n.id}>
                <button onClick={() => markOne(n)} className={`text-left w-full rounded-lg p-2 border ${n.read_utc ? 'border-outline-variant/30 text-on-surface-variant' : 'border-primary/30 bg-surface-container-low font-semibold'}`}>
                  <div>{n.title}</div>
                  {n.body && <div className="font-normal">{n.body}</div>}
                  <div className="font-normal text-outline">{n.created_utc}{n.case_id ? ` · ${n.case_id}` : ''}</div>
                </button>
              </li>))}</ul>)}
        </div>
      )}
    </div>
  )
}
