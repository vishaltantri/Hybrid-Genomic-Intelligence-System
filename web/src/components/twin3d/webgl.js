// Capability checks for the 3D stage. Everything important is also available as text, so these only
// decide how the *visualisation* is drawn.
export function webglAvailable() {
  try {
    if (typeof document === 'undefined') return false
    const c = document.createElement('canvas')
    const ctx = c.getContext('webgl2') || c.getContext('webgl') || c.getContext('experimental-webgl')
    return !!ctx
  } catch {
    return false
  }
}

export function lowPowerDevice() {
  if (typeof navigator === 'undefined') return false
  return (navigator.hardwareConcurrency || 8) <= 4 || (navigator.deviceMemory || 8) <= 4
}

export function prefersReducedMotion() {
  try {
    return !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  } catch {
    return false
  }
}

// Display colours (light clinical palette; deliberately no red: highlight never means "damage").
export const TWIN_COLORS = {
  neutral: '#4b6b93',
  neutralEdge: '#2a5d8f',
  case: '#3aa8ff', // case-specific data exists for this system
  linked: '#4fe3ff', // linked to the current selection
  selected: '#33f5c4', // the selected system
  shell: '#5fc8ff',
}

export const SYSTEM_STATE = (id, { selectedSystem, linkedSystems, caseSystems }) => {
  if (selectedSystem === id) return 'selected'
  if (linkedSystems?.includes(id)) return 'linked'
  if (caseSystems?.includes(id)) return 'case'
  return 'neutral'
}

export const CAMERA_VIEWS = {
  front: { pos: [0, -0.4, 8.6], target: [0, -0.5, 0] },
  back: { pos: [0, -0.4, -8.6], target: [0, -0.5, 0] },
  left: { pos: [-8.6, -0.4, 0], target: [0, -0.5, 0] },
  right: { pos: [8.6, -0.4, 0], target: [0, -0.5, 0] },
  dna: { pos: [0, 0, 7.2], target: [0, 0, 0] },
}
