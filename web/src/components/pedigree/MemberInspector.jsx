import React, { useEffect, useState } from 'react'
import { Trash2, UserCheck, Plus, Link2, Upload } from 'lucide-react'
import { api } from '../../api.js'

const field = 'w-full text-xs rounded-lg border border-outline-variant bg-white px-2.5 py-2'
const lbl = 'text-[11px] font-semibold text-on-surface space-y-1 block'

function Err({ msg }) {
  return msg ? <div role="alert" className="text-xs rounded-lg border border-red-200 bg-red-50 text-red-800 px-3 py-2">{msg}</div> : null
}

/** Run a backend mutation; the UI only changes (via `onChanged`) after the backend confirmed persistence. */
function useAction(onChanged) {
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const run = async (fn) => {
    setBusy(true)
    setError(null)
    try {
      const r = await fn()
      await onChanged(r)
      return r
    } catch (ex) {
      setError(ex.message)
      return null
    } finally {
      setBusy(false)
    }
  }
  return { error, busy, run, setError }
}

export function AddMemberForm({ caseId, ped, selectedId, onChanged, onCancel }) {
  const empty = !ped.members.length
  const [f, setF] = useState({ label: empty ? 'Proband' : '', sex: 'U', affected: empty ? 'affected' : 'unknown', age: '', proband: empty, relType: selectedId ? 'child' : '', deceased: false })
  const { error, busy, run } = useAction(onChanged)
  const sel = ped.members.find((m) => m.member_id === selectedId)
  const submit = (e) => {
    e.preventDefault()
    run(() => api.pedigreeAddMember(caseId, {
      label: f.label, sex: f.sex, affected: f.affected, age_years: f.age === '' ? null : Number(f.age), is_proband: f.proband, deceased: f.deceased,
      relation: f.relType && sel ? { to: sel.member_id, type: f.relType } : null,
    })).then((r) => r && onCancel())
  }
  return (
    <form onSubmit={submit} className="rounded-xl border border-primary/30 bg-white p-4 space-y-3" data-testid="add-member-form">
      <div className="text-xs font-bold text-on-surface">Add family member</div>
      <div className="grid grid-cols-2 gap-3">
        <label className={lbl}>Label (anonymised)<input aria-label="Member label" className={field} value={f.label} onChange={(e) => setF({ ...f, label: e.target.value })} placeholder="Mother, II-2…" /></label>
        <label className={lbl}>Sex
          <select aria-label="Member sex" className={field} value={f.sex} onChange={(e) => setF({ ...f, sex: e.target.value })}>
            <option value="U">Unspecified</option><option value="F">Female</option><option value="M">Male</option>
          </select>
        </label>
        <label className={lbl}>Affected status
          <select aria-label="Member affected status" className={field} value={f.affected} onChange={(e) => setF({ ...f, affected: e.target.value })}>
            <option value="unknown">Unknown</option><option value="affected">Affected</option><option value="unaffected">Unaffected</option>
          </select>
        </label>
        <label className={lbl}>Age (years, optional)<input aria-label="Member age" type="number" min="0" max="120" className={field} value={f.age} onChange={(e) => setF({ ...f, age: e.target.value })} /></label>
      </div>
      {sel && (
        <label className={lbl}>Relationship of the new member to {sel.label}
          <select aria-label="Relation to selected member" className={field} value={f.relType} onChange={(e) => setF({ ...f, relType: e.target.value })}>
            <option value="">None (connect later)</option>
            <option value="parent">Parent of {sel.label}</option>
            <option value="child">Child of {sel.label}</option>
            <option value="partner">Partner of {sel.label}</option>
          </select>
        </label>
      )}
      <div className="flex gap-4 text-xs">
        <label className="flex items-center gap-1.5"><input type="checkbox" checked={f.proband} onChange={(e) => setF({ ...f, proband: e.target.checked })} /> Proband</label>
        <label className="flex items-center gap-1.5"><input type="checkbox" checked={f.deceased} onChange={(e) => setF({ ...f, deceased: e.target.checked })} /> Deceased</label>
      </div>
      <Err msg={error} />
      <div className="flex gap-2">
        <button disabled={busy} data-testid="add-member-submit" className="px-3 py-1.5 rounded-lg bg-primary text-white text-xs font-semibold disabled:opacity-60">{busy ? 'Saving…' : 'Add member'}</button>
        <button type="button" onClick={onCancel} className="px-3 py-1.5 rounded-lg border border-outline-variant text-xs font-semibold">Cancel</button>
      </div>
    </form>
  )
}

export default function MemberInspector({ caseId, ped, member, nav, onChanged, onSelectVariant, selectedVariant }) {
  const [edit, setEdit] = useState(null)
  const [q, setQ] = useState('')
  const [hits, setHits] = useState([])
  const [gt, setGt] = useState({ variant: '', genotype: '0/1', manualKey: '', manualGene: '' })
  const [rel, setRel] = useState({ other: '', type: 'parent' })
  const [imp, setImp] = useState({ analysis: '', sample: '' })
  const { error, busy, run, setError } = useAction(onChanged)

  useEffect(() => {
    setEdit(null); setQ(''); setHits([]); setError(null)
    setRel({ other: '', type: 'parent' })
    if (member) setEdit({ label: member.label, sex: member.sex, affected: member.affected, age: member.age_years ?? '', deceased: member.deceased, notes: member.notes || '' })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [member?.member_id])

  useEffect(() => {
    if (q.trim().length < 2) { setHits([]); return undefined }
    let live = true
    const t = setTimeout(() => api.pedigreeHpoSearch(q.trim()).then((h) => live && setHits(h)).catch(() => live && setHits([])), 200)
    return () => { live = false; clearTimeout(t) }
  }, [q])

  if (!member) {
    return <div className="text-xs text-on-surface-variant" data-testid="member-inspector">Select a family member on the canvas to inspect or edit them.</div>
  }
  const others = ped.members.filter((m) => m.member_id !== member.member_id)
  const relFor = (id) => ped.members.find((m) => m.member_id === id)?.label || id
  const myRels = ped.relationships.filter((r) => r.member_a === member.member_id || r.member_b === member.member_id)
  const variantsReg = ped.variants
  const vlabel = (k) => { const v = variantsReg.find((x) => x.variant_key === k); return v ? `${v.gene} ${v.hgvs || k}` : k }
  const n = (k) => member.genotypes[k]?.genotype

  const save = (e) => {
    e.preventDefault()
    run(() => api.pedigreePatchMember(caseId, member.member_id, {
      label: edit.label, sex: edit.sex, affected: edit.affected, age_years: edit.age === '' ? null : Number(edit.age), deceased: edit.deceased, notes: edit.notes,
    }))
  }
  const addHpo = (h) => { setQ(''); setHits([]); run(() => api.pedigreeSetPhenotypes(caseId, member.member_id, [...member.hpo_ids, h.hpo_id])) }
  const rmHpo = (id) => run(() => api.pedigreeSetPhenotypes(caseId, member.member_id, member.hpo_ids.filter((x) => x !== id)))
  const analysisOpts = ped.analyses_available
  const importVcf = () => run(() => api.pedigreeImportGenotypes(caseId, member.member_id, { analysis_id: imp.analysis || analysisOpts[0]?.analysis_id, sample: imp.sample }))
  const analysisSamples = (analysisOpts.find((a) => a.analysis_id === (imp.analysis || analysisOpts[0]?.analysis_id)) || {}).samples || []

  return (
    <div className="space-y-4 text-xs" data-testid="member-inspector">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="text-base font-bold text-on-surface">{member.label} {member.is_proband && <span className="ml-1 px-2 py-0.5 rounded-full bg-primary text-white text-[10px] align-middle">Proband</span>}</div>
          <div className="text-on-surface-variant">
            {member.relation_to_proband && member.relation_to_proband !== 'self' ? `${member.relation_to_proband} of the proband · ` : ''}
            Sex: {member.sex === 'M' ? 'Male' : member.sex === 'F' ? 'Female' : 'Unspecified'} · Status: {member.affected} · Generation {member.generation + 1}
            {member.synthetic ? ' · sample' : ''}
          </div>
        </div>
      </div>
      <div className="grid grid-cols-3 gap-2" data-testid="member-counts">
        <div className="rounded-lg border border-outline-variant/40 px-2 py-1.5"><div className="text-[10px] uppercase text-outline">Phenotypes</div><b className="text-base">{member.phenotypes.length}</b></div>
        <div className="rounded-lg border border-outline-variant/40 px-2 py-1.5"><div className="text-[10px] uppercase text-outline">Variants</div><b className="text-base">{Object.keys(member.genotypes).length}</b></div>
        <div className="rounded-lg border border-outline-variant/40 px-2 py-1.5"><div className="text-[10px] uppercase text-outline">Relatives</div><b className="text-base">{member.parents.length + member.children.length + member.partners.length}</b></div>
      </div>
      <div className="flex flex-wrap gap-2">
        {!member.is_proband && <button data-testid="set-proband" disabled={busy} onClick={() => run(() => api.pedigreeSetProband(caseId, member.member_id))} className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg border border-primary text-primary font-semibold"><UserCheck size={13} /> Set as proband</button>}
        <button onClick={() => nav('digital-twin', { patient_id: caseId })} className="px-2.5 py-1.5 rounded-lg border border-outline-variant font-semibold">View Digital Twin</button>
        <button onClick={() => nav('variants', { patient_id: caseId, analysis_id: analysisOpts[0]?.analysis_id, variant_id: selectedVariant })} className="px-2.5 py-1.5 rounded-lg border border-outline-variant font-semibold">View Variants</button>
        <button onClick={() => nav('phenotypes', { patient_id: caseId })} className="px-2.5 py-1.5 rounded-lg border border-outline-variant font-semibold">View HPO</button>
      </div>

      <Err msg={error} />

      <form onSubmit={save} className="space-y-2 rounded-lg border border-outline-variant/40 p-3" data-testid="member-edit">
        <div className="font-bold text-on-surface">Edit member</div>
        <div className="grid grid-cols-2 gap-2">
          <label className={lbl}>Label<input aria-label="Edit label" className={field} value={edit?.label ?? ''} onChange={(e) => setEdit({ ...edit, label: e.target.value })} /></label>
          <label className={lbl}>Sex<select aria-label="Edit sex" className={field} value={edit?.sex ?? 'U'} onChange={(e) => setEdit({ ...edit, sex: e.target.value })}><option value="U">Unspecified</option><option value="F">Female</option><option value="M">Male</option></select></label>
          <label className={lbl}>Affected<select aria-label="Edit affected" className={field} value={edit?.affected ?? 'unknown'} onChange={(e) => setEdit({ ...edit, affected: e.target.value })}><option value="unknown">Unknown</option><option value="affected">Affected</option><option value="unaffected">Unaffected</option></select></label>
          <label className={lbl}>Age<input aria-label="Edit age" type="number" className={field} value={edit?.age ?? ''} onChange={(e) => setEdit({ ...edit, age: e.target.value })} /></label>
        </div>
        <label className="flex items-center gap-1.5"><input type="checkbox" checked={!!edit?.deceased} onChange={(e) => setEdit({ ...edit, deceased: e.target.checked })} /> Deceased</label>
        <button disabled={busy} data-testid="member-save" className="px-3 py-1.5 rounded-lg bg-primary text-white font-semibold disabled:opacity-60">Save changes</button>
      </form>

      <div className="rounded-lg border border-outline-variant/40 p-3 space-y-2" data-testid="member-phenotypes">
        <div className="font-bold text-on-surface">Phenotypes (HPO)</div>
        {member.phenotypes.length === 0 && <p className="text-on-surface-variant">None recorded.</p>}
        <ul className="space-y-1">
          {member.phenotypes.map((p) => (
            <li key={p.hpo_id} className="flex justify-between"><span>{p.name} <span className="font-mono text-outline">{p.hpo_id}</span></span>
              <button aria-label={`Remove ${p.name}`} onClick={() => rmHpo(p.hpo_id)} className="text-outline hover:text-red-700"><Trash2 size={12} /></button></li>
          ))}
        </ul>
        <input aria-label="Search HPO term" className={field} placeholder="Search HPO term (e.g. tremor)…" value={q} onChange={(e) => setQ(e.target.value)} />
        {hits.length > 0 && (
          <ul className="rounded-lg border border-outline-variant/50 divide-y divide-outline-variant/30 max-h-40 overflow-auto bg-white">
            {hits.map((h) => <li key={h.hpo_id}><button className="w-full text-left px-2.5 py-1.5 hover:bg-primary/5" onClick={() => addHpo(h)}>{h.name} <span className="font-mono text-outline">{h.hpo_id}</span></button></li>)}
          </ul>
        )}
      </div>

      <div className="rounded-lg border border-outline-variant/40 p-3 space-y-2" data-testid="member-genotypes">
        <div className="font-bold text-on-surface">Genotypes / variants</div>
        {Object.keys(member.genotypes).length === 0 && <p className="text-on-surface-variant">No genotype recorded for this member.</p>}
        <ul className="space-y-1">
          {Object.entries(member.genotypes).map(([k, g]) => (
            <li key={k} className="flex items-center justify-between gap-2">
              <button className="text-left text-primary font-semibold hover:underline" onClick={() => onSelectVariant(k)}>{vlabel(k)}</button>
              <span className="font-mono">{g.genotype} <span className="text-outline">({g.source.startsWith('vcf') ? 'VCF' : g.source})</span></span>
              <button aria-label={`Remove genotype ${k}`} onClick={() => run(() => api.pedigreeDeleteGenotype(caseId, member.member_id, k))} className="text-outline hover:text-red-700"><Trash2 size={12} /></button>
            </li>
          ))}
        </ul>
        <div className="grid grid-cols-[1fr_auto_auto] gap-2 items-end">
          <label className={lbl}>Variant
            <select aria-label="Genotype variant" className={field} value={gt.variant} onChange={(e) => setGt({ ...gt, variant: e.target.value })}>
              <option value="">Select a registered variant…</option>
              {variantsReg.map((v) => <option key={v.variant_key} value={v.variant_key}>{v.gene} {v.hgvs || v.variant_key}{n(v.variant_key) ? ` (current ${n(v.variant_key)})` : ''}</option>)}
            </select>
          </label>
          <label className={lbl}>Genotype
            <select aria-label="Genotype value" className={field} value={gt.genotype} onChange={(e) => setGt({ ...gt, genotype: e.target.value })}>
              <option value="0/0">0/0 absent</option><option value="0/1">0/1 het</option><option value="1/1">1/1 hom</option><option value="hemizygous">hemizygous</option><option value="unknown">unknown</option>
            </select>
          </label>
          <button data-testid="genotype-assign" disabled={busy || !gt.variant} onClick={() => run(() => api.pedigreeSetGenotype(caseId, member.member_id, { genotype: gt.genotype, variant_key: gt.variant }))} className="px-2.5 py-2 rounded-lg bg-primary text-white font-semibold disabled:opacity-50"><Plus size={13} /></button>
        </div>
        {analysisOpts.length > 0 && (
          <div className="rounded-lg bg-surface-container-low p-2 space-y-1.5" data-testid="vcf-import">
            <div className="font-semibold">Import from Variant Intelligence VCF</div>
            <div className="grid grid-cols-[1fr_1fr_auto] gap-2 items-end">
              <select aria-label="Analysis" className={field} value={imp.analysis || analysisOpts[0].analysis_id} onChange={(e) => setImp({ analysis: e.target.value, sample: '' })}>
                {analysisOpts.map((a) => <option key={a.analysis_id} value={a.analysis_id}>{a.analysis_id} · {a.filename}</option>)}
              </select>
              <select aria-label="VCF sample" className={field} value={imp.sample} onChange={(e) => setImp({ ...imp, sample: e.target.value })}>
                <option value="">Sample column…</option>{analysisSamples.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
              <button disabled={busy || !imp.sample} onClick={importVcf} data-testid="vcf-import-run" className="px-2.5 py-2 rounded-lg border border-primary text-primary font-semibold disabled:opacity-50"><Upload size={13} /></button>
            </div>
          </div>
        )}
        <details>
          <summary className="cursor-pointer text-primary font-semibold">Enter a variant manually</summary>
          <div className="grid grid-cols-2 gap-2 mt-2">
            <input aria-label="Manual variant key" className={field} placeholder="chr13:51943246:C>G" value={gt.manualKey} onChange={(e) => setGt({ ...gt, manualKey: e.target.value })} />
            <input aria-label="Manual gene" className={field} placeholder="Gene symbol" value={gt.manualGene} onChange={(e) => setGt({ ...gt, manualGene: e.target.value })} />
          </div>
          <button disabled={busy || !gt.manualKey || !gt.manualGene} onClick={() => run(() => api.pedigreeSetGenotype(caseId, member.member_id, { genotype: gt.genotype, variant_key: gt.manualKey, gene: gt.manualGene }))} className="mt-2 px-2.5 py-1.5 rounded-lg border border-primary text-primary font-semibold disabled:opacity-50">Assign manual variant</button>
        </details>
      </div>

      <div className="rounded-lg border border-outline-variant/40 p-3 space-y-2" data-testid="member-relationships">
        <div className="font-bold text-on-surface">Relationships</div>
        <ul className="space-y-1">
          {myRels.map((r) => {
            const text = r.rel_type === 'partner' ? `Partner of ${relFor(r.member_a === member.member_id ? r.member_b : r.member_a)}`
              : r.member_a === member.member_id ? `Parent of ${relFor(r.member_b)}` : `Child of ${relFor(r.member_a)}`
            return (
              <li key={r.rel_id} className="flex justify-between"><span>{text}</span>
                <button aria-label={`Remove relationship ${text}`} onClick={() => run(() => api.pedigreeDeleteRelationship(caseId, r.rel_id))} className="text-outline hover:text-red-700"><Trash2 size={12} /></button></li>
            )
          })}
          {myRels.length === 0 && <li className="text-on-surface-variant">No relationships recorded.</li>}
        </ul>
        <div className="grid grid-cols-[1fr_1fr_auto] gap-2 items-end">
          <label className={lbl}>{member.label} is…
            <select aria-label="Relationship type" className={field} value={rel.type} onChange={(e) => setRel({ ...rel, type: e.target.value })}>
              <option value="parent">parent of</option><option value="child">child of</option><option value="partner">partner of</option>
            </select>
          </label>
          <label className={lbl}>Member
            <select aria-label="Relationship member" className={field} value={rel.other} onChange={(e) => setRel({ ...rel, other: e.target.value })}>
              <option value="">Select…</option>{others.map((m) => <option key={m.member_id} value={m.member_id}>{m.label}</option>)}
            </select>
          </label>
          <button data-testid="connect-members" disabled={busy || !rel.other} onClick={() => run(() => api.pedigreeAddRelationship(caseId, { type: rel.type, member_a: member.member_id, member_b: rel.other }))} className="px-2.5 py-2 rounded-lg bg-primary text-white font-semibold disabled:opacity-50"><Link2 size={13} /></button>
        </div>
      </div>

      <button data-testid="delete-member" disabled={busy} onClick={() => { if (window.confirm(`Delete ${member.label}? Their relationships and genotypes are removed too.`)) run(() => api.pedigreeDeleteMember(caseId, member.member_id)) }}
        className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg border border-red-300 text-red-800 font-semibold"><Trash2 size={13} /> Delete member</button>
    </div>
  )
}
