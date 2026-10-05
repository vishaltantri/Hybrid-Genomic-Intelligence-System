// Pure helpers that turn the Twin payload + the current selection into highlight sets and an entity record.
// Only relationships present in twin.anatomy (built server-side from the KG and the patient's own data) are used.

export function systemById(twin, id) {
  return twin?.anatomy?.systems?.find((s) => s.id === id) || null
}

export function variantById(twin, id) {
  return twin?.genomic?.variants?.find((v) => v.variant_id === id) || null
}

export function geneRecord(twin, gene) {
  return twin?.anatomy?.genes?.find((g) => g.gene === gene) || null
}

/** Highlight sets for the body: selectedSystem, linkedSystems (from the selection) and caseSystems (data exists). */
export function highlightFor(twin, selection) {
  const systems = twin?.anatomy?.systems || []
  const caseSystems = systems.filter((s) => s.has_case_data).map((s) => s.id)
  let selectedSystem = null
  let linkedSystems = []
  if (selection?.kind === 'system') selectedSystem = selection.id
  else if (selection?.kind === 'variant') {
    linkedSystems = systems.filter((s) => s.variant_ids.includes(selection.id)).map((s) => s.id)
  } else if (selection?.kind === 'gene') {
    linkedSystems = systems.filter((s) => s.genes.includes(selection.id)).map((s) => s.id)
  } else if (selection?.kind === 'diagnosis') {
    linkedSystems = systems.filter((s) => s.diseases.some((d) => d.disease_id === selection.id)).map((s) => s.id)
  }
  return { selectedSystem, linkedSystems, caseSystems }
}

/** Helix markers: the selected gene's analysed variants, positioned by fraction of their chromosome. */
export function dnaMarkersFor(twin, selection) {
  if (!twin?.genomic?.available || !selection) return []
  let gene = null
  if (selection.kind === 'variant') gene = variantById(twin, selection.id)?.gene_symbol
  else if (selection.kind === 'gene') gene = selection.id
  if (!gene) return []
  const out = []
  twin.anatomy.chromosomes.forEach((c) =>
    c.variants.forEach((v) => {
      if (v.gene === gene) out.push({ variant_id: v.variant_id, fraction: v.pos / c.length_bp, ref: v.ref, alt: v.alt, hgvs: v.hgvs, gene })
    }),
  )
  return out
}

export function chromOfVariant(twin, id) {
  return twin?.anatomy?.chromosomes?.find((c) => c.variants.some((v) => v.variant_id === id))?.chrom || null
}
