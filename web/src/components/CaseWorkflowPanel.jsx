import React, { useEffect, useState } from 'react'
import { api } from '../api.js'

const LABEL = { new: 'New', in_review: 'In review', awaiting_results: 'Awaiting results', report_ready: 'Report ready', closed: 'Closed' }

export default function CaseWorkflowPanel() {
  const [patients, setPatients] = useState([])
  const [pid, setPid] = useState('')
  const [wf, setWf] = useState(null)
  const [assignee, setAssignee] = useState('')
  const [note, setNote] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => { api.listPatients().then((p) => setPatients(Array.isArray(p) ? p : p?.patients || [])).catch(() => {}) }, [])
  const guard = async (fn) => { setError(null); setBusy(true); try { await fn() } catch (e) { setError(e.message) } finally { setBusy(false) } }
  const load = (id) => guard(async () => { setPid(id); setWf(null); if (id) setWf(await api.wfGet(id)) })
  const move = (status) => guard(async () => { await api.wfStatus(pid, { status, note }); setNote(''); setWf(await api.wfGet(pid)) })
  const assign = () => guard(async () => { await api.wfAssign(pid, { assignee, note }); setAssignee(''); setNote(''); setWf(await api.wfGet(pid)) })
  const inp = 'rounded-lg border border-outline-variant p-2 text-sm'

  return (
    <section className="panel p-4 space-y-3" data-testid="case-workflow">
      <div>
        <h3 className="text-base font-bold text-on-surface">Case workflow</h3>
        <p className="text-xs text-on-surface-variant">Status, assignment and an audit trail of every change. Assignees are notified.</p>
      </div>
      {error && <div role="alert" className="rounded-lg border border-red-200 bg-red-50 text-red-800 text-xs px-3 py-2">{error}</div>}
      <select aria-label="Workflow case" value={pid} onChange={(e) => load(e.target.value)} className={`${inp} block w-full max-w-sm`}>
        <option value="">No case selected</option>
        {patients.map((p) => <option key={p.patient_id} value={p.patient_id}>{p.patient_id}{p.name ? ` — ${p.name}` : ''}</option>)}
      </select>
      {wf && (
        <div className="text-xs space-y-2">
          <div data-testid="wf-state">Status: <b>{LABEL[wf.status]}</b> · Assigned to: <b>{wf.assignee || 'Not assigned'}</b></div>
          <input aria-label="Workflow note" placeholder="Note (optional)" value={note} onChange={(e) => setNote(e.target.value)} className={`${inp} w-full max-w-sm`} />
          <div className="flex flex-wrap gap-2">
            {wf.allowed_next.map((s) => <button key={s} onClick={() => move(s)} disabled={busy} className="px-3 py-1.5 rounded-lg border border-primary/30 text-primary font-semibold">Move to {LABEL[s]}</button>)}
          </div>
          <div className="flex flex-wrap gap-2 items-center">
            <input aria-label="Assignee username" placeholder="Clinician username" value={assignee} onChange={(e) => setAssignee(e.target.value)} className={inp} />
            <button onClick={assign} disabled={busy || !assignee.trim()} className="px-3 py-1.5 rounded-lg bg-primary text-white font-semibold disabled:opacity-50">Assign</button>
          </div>
          <ul data-testid="wf-history">
            {wf.history.length === 0 ? <li className="text-on-surface-variant">No changes recorded.</li> : wf.history.map((h) => (
              <li key={h.id}>{h.utc} · {h.actor} · {h.action}: {h.from_value || 'none'} → {h.to_value}{h.note ? ` — ${h.note}` : ''}</li>))}
          </ul>
        </div>
      )}
    </section>
  )
}
