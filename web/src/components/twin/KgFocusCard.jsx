import React, { useEffect, useState } from 'react'
import { Cpu } from 'lucide-react'
import { api } from '../../api.js'

/**
 * Shown on the Knowledge Graph page when the user arrives from the Digital Twin.
 * Reads the existing /diseases/{id} KG endpoint: gene -> disease -> phenotype, plus the
 * patient's variant ids that the Twin linked to this disease.
 */
export default function KgFocusCard({ focus }) {
  const [detail, setDetail] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!focus?.disease_id) return
    api.diseaseDetail(focus.disease_id).then(setDetail).catch((ex) => setError(ex.message))
  }, [focus])

  if (!focus?.disease_id) return null
  return (
    <div className="rounded-xl border border-primary/30 bg-white p-4 text-xs space-y-2" data-testid="kg-focus">
      <div className="flex items-center gap-2 font-bold text-on-surface">
        <Cpu size={14} className="text-primary" /> From the Digital Twin: {detail?.disease?.name || focus.disease_id}
      </div>
      {error && <div role="alert" className="text-red-700">{error}</div>}
      {detail && (
        <>
          <div><b>Genes:</b> {detail.genes.join(', ') || '-'}</div>
          <div><b>Phenotypes:</b> {detail.phenotypes.map((p) => `${p.name} (${p.hpo_id})`).join('; ') || '-'}</div>
          {detail.founder_risk.length > 0 && (
            <div><b>Founder risk:</b> {detail.founder_risk.map((f) => f.community).join(', ')}</div>
          )}
        </>
      )}
      {focus.variant_ids?.length > 0 && <div><b>Patient variants linked:</b> {focus.variant_ids.join(', ')}</div>}
    </div>
  )
}
