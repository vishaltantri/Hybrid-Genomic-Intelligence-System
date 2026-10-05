import React, { useEffect, useState } from 'react'
import { api } from '../api.js'

const OUTCOMES = [['improved', 'Improved'], ['unchanged', 'Unchanged'], ['worse', 'Worse'], ['visited_facility', 'Visited facility'], ['unreachable', 'Could not be reached']]
const COLOR = { red: 'text-red-700', yellow: 'text-amber-700', green: 'text-emerald-700' }

export default function ReferralsPanel() {
  const [rows, setRows] = useState([])
  const [summary, setSummary] = useState(null)
  const [open, setOpen] = useState(null)
  const [form, setForm] = useState({ transcript: '', age: '', village: '', district: '', state: '' })
  const [outcome, setOutcome] = useState('improved')
  const [note, setNote] = useState('')
  const [error, setError] = useState(null)
  const [info, setInfo] = useState(null)
  const [busy, setBusy] = useState(false)

  const reload = async () => { setRows(await api.refList()); setSummary(await api.refSummary()) }
  const guard = async (fn) => { setError(null); setInfo(null); setBusy(true); try { await fn() } catch (e) { setError(e.message) } finally { setBusy(false) } }
  useEffect(() => { guard(reload) }, [])

  const create = () => guard(async () => {
    const body = { transcript: form.transcript, state: form.state || undefined, district: form.district || undefined, village: form.village || undefined, age: form.age ? Number(form.age) : undefined }
    const r = await api.refCreateText(body)
    setOpen(r); setForm({ ...form, transcript: '' }); await reload()
  })
  const followUp = () => guard(async () => { setOpen(await api.refFollowUp(open.referral_id, { outcome, note })); setNote(''); await reload() })
  const handoff = () => guard(async () => {
    const r = await api.refHandoff(open.referral_id, {})
    setOpen(r.referral); setInfo(`Case ${r.case_id} created. ASHA-reported symptoms were attached as an event and were not confirmed as phenotypes.`); await reload()
  })
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })
  const inp = 'rounded-lg border border-outline-variant p-2 text-sm'

  return (
    <section className="panel p-4 space-y-3" data-testid="referrals">
      <h3 className="text-base font-bold">Referrals and follow-up</h3>
      {error && <div role="alert" className="rounded-lg border border-red-200 bg-red-50 text-red-800 text-xs px-3 py-2">{error}</div>}
      {info && <div role="status" className="text-xs text-primary">{info}</div>}
      {summary && <p data-testid="ref-summary" className="text-xs">Total {summary.total} · Red {summary.by_color.red} · Yellow {summary.by_color.yellow} · Green {summary.by_color.green} · Overdue follow-up {summary.overdue} · Needs review {summary.needs_review}</p>}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        <input aria-label="Referral age" placeholder="Age (years)" value={form.age} onChange={set('age')} className={inp} />
        <input aria-label="Referral village" placeholder="Village" value={form.village} onChange={set('village')} className={inp} />
        <input aria-label="Referral district" placeholder="District" value={form.district} onChange={set('district')} className={inp} />
        <input aria-label="Referral state" placeholder="State" value={form.state} onChange={set('state')} className={inp} />
      </div>
      <textarea aria-label="Referral transcript" rows={2} placeholder="Describe the symptoms" value={form.transcript} onChange={set('transcript')} className={`${inp} w-full`} />
      <button onClick={create} disabled={busy || !form.transcript.trim()} className="px-3 py-2 rounded-lg bg-primary text-white text-xs font-semibold disabled:opacity-50">Create referral</button>
      <div data-testid="ref-list" className="text-xs">
        {rows.length === 0 ? <p className="text-on-surface-variant">No referrals yet.</p> : (
          <ul className="space-y-1">{rows.map((r) => (
            <li key={r.referral_id}>
              <button onClick={() => setOpen(r)} className="text-primary underline">{r.referral_id}</button>{' '}
              <span className={`font-semibold uppercase ${COLOR[r.triage_color]}`}>{r.triage_color}</span> · {r.village || 'Village not documented'} · {r.status}
              {r.overdue && <span className="text-red-700"> · Follow-up overdue</span>}
            </li>))}</ul>)}
      </div>
      {open && (
        <div data-testid="ref-detail" className="rounded-lg border border-outline-variant/40 p-3 text-xs space-y-2">
          <div><b>{open.referral_id}</b> · {open.status}{open.case_id ? ` · Case ${open.case_id}` : ''}</div>
          <div>{open.action.en}</div>
          <div lang="hi">{open.action.hi}</div>
          <div>Facility: {open.facility || 'Not documented'} · Follow-up due {open.follow_up_due}</div>
          <div>Reported: {(open.triage.reported_symptoms || []).join(', ') || 'No symptoms extracted'}</div>
          <ul>{(open.followups || []).map((f) => <li key={f.id}>{f.created_utc} · {f.outcome}{f.note ? ` — ${f.note}` : ''}</li>)}</ul>
          {!['closed', 'handed_off'].includes(open.status) && (
            <div className="flex flex-wrap gap-2 items-center">
              <select aria-label="Follow-up outcome" value={outcome} onChange={(e) => setOutcome(e.target.value)} className={inp}>{OUTCOMES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
              <input aria-label="Follow-up note" placeholder="Note" value={note} onChange={(e) => setNote(e.target.value)} className={inp} />
              <button onClick={followUp} disabled={busy} className="px-3 py-1.5 rounded-lg border border-primary/30 text-primary font-semibold">Record follow-up</button>
              <button onClick={handoff} disabled={busy} className="px-3 py-1.5 rounded-lg bg-primary text-white font-semibold">Hand off to clinician (creates case)</button>
            </div>)}
        </div>
      )}
    </section>
  )
}
