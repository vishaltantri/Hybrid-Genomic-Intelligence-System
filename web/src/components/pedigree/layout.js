// Deterministic generation layout for a pedigree. Positions come from the recorded structure only:
//  - generation (row) is computed by the backend from parent-child links (partners share a row);
//  - partners are kept adjacent; sibships are centred under their parents;
//  - a member's saved drag position (layout_x / layout_y) overrides the computed one.
export const SYMBOL = 46
export const H_GAP = 124
export const V_GAP = 156

export function layoutPedigree(members) {
  const byId = Object.fromEntries(members.map((m) => [m.member_id, m]))
  const gens = [...new Set(members.map((m) => m.generation))].sort((a, b) => a - b)
  const pos = {}

  for (const g of gens) {
    const row = members.filter((m) => m.generation === g)
    // units = connected partner chains within the row
    const seen = new Set()
    const units = []
    for (const m of row) {
      if (seen.has(m.member_id)) continue
      const comp = []
      const stack = [m.member_id]
      while (stack.length) {
        const id = stack.pop()
        if (seen.has(id) || !byId[id] || byId[id].generation !== g) continue
        seen.add(id)
        comp.push(id)
        byId[id].partners.forEach((p) => stack.push(p))
      }
      // members that have parents on the left so the sibship line reaches them without crossing the couple
      comp.sort((a, b) => (byId[b].parents.length > 0) - (byId[a].parents.length > 0) || members.indexOf(byId[a]) - members.indexOf(byId[b]))
      const desired = comp
        .filter((id) => byId[id].parents.length && byId[id].parents.every((p) => pos[p]))
        .map((id) => byId[id].parents.reduce((s, p) => s + pos[p].x, 0) / byId[id].parents.length)
      units.push({ ids: comp, desired: desired.length ? desired.reduce((a, b) => a + b, 0) / desired.length : null, order: units.length })
    }
    units.sort((a, b) => (a.desired ?? Infinity) - (b.desired ?? Infinity) || a.order - b.order)
    let cursor = -Infinity
    for (const u of units) {
      const width = (u.ids.length - 1) * H_GAP
      let x0 = u.desired == null ? (cursor === -Infinity ? 0 : cursor + H_GAP * 0.9) : u.desired - width / 2
      if (cursor !== -Infinity) x0 = Math.max(x0, cursor + H_GAP * 0.9)
      u.ids.forEach((id, i) => { pos[id] = { x: x0 + i * H_GAP, y: g * V_GAP } })
      cursor = x0 + width
    }
  }
  const xs = Object.values(pos).map((p) => p.x)
  const shift = xs.length ? 80 - Math.min(...xs) : 0
  for (const id of Object.keys(pos)) pos[id] = { x: pos[id].x + shift, y: pos[id].y + 70 }
  for (const m of members) {
    if (m.layout_x != null && m.layout_y != null) pos[m.member_id] = { x: m.layout_x, y: m.layout_y }
  }
  return pos
}

/** Lines of the pedigree: partner links and sibship (descent) lines, as plain segments in canvas coordinates. */
export function pedigreeEdges(members, pos) {
  const byId = Object.fromEntries(members.map((m) => [m.member_id, m]))
  const segs = []
  const drawn = new Set()
  for (const m of members) {
    for (const p of m.partners) {
      const key = [m.member_id, p].sort().join('|')
      if (drawn.has(key) || !pos[p]) continue
      drawn.add(key)
      segs.push({ kind: 'partner', key: `p-${key}`, x1: pos[m.member_id].x, y1: pos[m.member_id].y, x2: pos[p].x, y2: pos[p].y })
    }
  }
  const groups = {}
  for (const m of members) {
    if (!m.parents.length) continue
    const k = [...m.parents].sort().join('|')
    ;(groups[k] ||= { parents: [...m.parents].sort(), children: [] }).children.push(m.member_id)
  }
  for (const [k, g] of Object.entries(groups)) {
    const ps = g.parents.filter((p) => pos[p])
    if (!ps.length) continue
    const arePartners = ps.length === 2 && byId[ps[0]].partners.includes(ps[1])
    const ox = ps.reduce((s, p) => s + pos[p].x, 0) / ps.length
    const oy = arePartners ? (pos[ps[0]].y + pos[ps[1]].y) / 2 : Math.max(...ps.map((p) => pos[p].y)) + SYMBOL / 2
    const cy = Math.min(...g.children.map((c) => pos[c].y))
    const busY = cy - SYMBOL / 2 - 26
    const cxs = g.children.map((c) => pos[c].x)
    const minX = Math.min(ox, ...cxs)
    const maxX = Math.max(ox, ...cxs)
    segs.push({ kind: 'descent', key: `d-${k}-drop`, x1: ox, y1: oy, x2: ox, y2: busY })
    if (maxX > minX) segs.push({ kind: 'descent', key: `d-${k}-bus`, x1: minX, y1: busY, x2: maxX, y2: busY })
    for (const c of g.children) segs.push({ kind: 'descent', key: `d-${k}-${c}`, x1: pos[c].x, y1: busY, x2: pos[c].x, y2: pos[c].y - SYMBOL / 2 })
    if (!arePartners) {
      for (const p of ps) segs.push({ kind: 'descent', key: `d-${k}-from-${p}`, x1: pos[p].x, y1: pos[p].y + SYMBOL / 2, x2: pos[p].x, y2: oy })
    }
  }
  return segs
}

export function bounds(pos) {
  const v = Object.values(pos)
  if (!v.length) return { x: 0, y: 0, w: 400, h: 300 }
  const pad = 80
  const x1 = Math.min(...v.map((p) => p.x)) - pad
  const x2 = Math.max(...v.map((p) => p.x)) + pad
  const y1 = Math.min(...v.map((p) => p.y)) - pad
  const y2 = Math.max(...v.map((p) => p.y)) + pad + 30
  return { x: x1, y: y1, w: x2 - x1, h: y2 - y1 }
}
