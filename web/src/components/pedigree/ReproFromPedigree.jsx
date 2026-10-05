import React, { useEffect, useState } from 'react'
import { api } from '../../api.js'
import { ReproTab } from './AnalysisPanel.jsx'

/** Reproductive module entry: feed a case's recorded pedigree (parents' genotypes) into the existing counselling engine. */
export default function ReproFromPedigree() {
  const [patients, setPatients] = useState([])
  const [cid, setCid] = useState('')
  const [st, setSt] = useState({ data: null, error: null, busy: false })
  useEffect(() => { api.listPatients().then((p) => setPatients(p || [])).catch(() => {}) }, [])
  useEffect(() => setSt({ data: null, error: null, busy: false }), [cid])
  const run = async () => {
    setSt({ data: null, error: null, busy: true })
    try { setSt({ data: await api.pedigreeReproductive(cid), error: null, busy: false }) } catch (ex) { setSt({ data: null, error: ex.message, busy: false }) }
  }
  return (
    <div className="panel space-y-3" data-testid="repro-from-pedigree">
      <div className="text-xs font-bold text-on-surface">FAMILY INHERITANCE DATA (from the Pedigree module)</div>
      <p className="text-xs text-on-surface-variant">Uses the recorded genotypes of a case's parents (or two chosen partners) as known carrier / affected status, then runs the same reproductive risk engine.</p>
      <select aria-label="Pedigree case" value={cid} onChange={(e) => setCid(e.target.value)} className="text-xs rounded-lg border border-outline-variant px-2.5 py-2">
        <option value="">Select a case with a pedigree…</option>
        {patients.map((p) => <option key={p.patient_id} value={p.patient_id}>{p.patient_id}</option>)}
      </select>
      {cid && <ReproTab data={st.data} error={st.error} busy={st.busy} onRun={run} />}
    </div>
  )
}
