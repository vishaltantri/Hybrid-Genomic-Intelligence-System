// indiaMapData.js - Real India Geographic Centroids, Zones & Color Scales

export const STATE_CENTROIDS = {
  an: { id: 'an', name: 'Andaman and Nicobar Islands', x: 521, y: 609, width: 36, height: 174, zone: 'East' },
  ap: { id: 'ap', name: 'Andhra Pradesh', x: 263, y: 500, width: 167, height: 143, zone: 'South' },
  ar: { id: 'ar', name: 'Arunachal Pradesh', x: 550, y: 224, width: 123, height: 67, zone: 'North-East' },
  as: { id: 'as', name: 'Assam', x: 516, y: 271, width: 132, height: 90, zone: 'North-East' },
  br: { id: 'br', name: 'Bihar', x: 369, y: 275, width: 104, height: 75, zone: 'East' },
  ch: { id: 'ch', name: 'Chandigarh', x: 179, y: 160, width: 3, height: 3, zone: 'North' },
  ct: { id: 'ct', name: 'Chhattisgarh', x: 296, y: 388, width: 87, height: 142, zone: 'Central' },
  dn: { id: 'dn', name: 'Dadra and Nagar Haveli', x: 102, y: 405, width: 6, height: 7, zone: 'West' },
  dd: { id: 'dd', name: 'Daman and Diu', x: 54, y: 391, width: 5, height: 7, zone: 'West' },
  dl: { id: 'dl', name: 'Delhi', x: 186, y: 210, width: 11, height: 11, zone: 'North' },
  ga: { id: 'ga', name: 'Goa', x: 122, y: 512, width: 14, height: 20, zone: 'West' },
  gj: { id: 'gj', name: 'Gujarat', x: 66, y: 355, width: 132, height: 104, zone: 'West' },
  hr: { id: 'hr', name: 'Haryana', x: 164, y: 195, width: 65, height: 79, zone: 'North' },
  hp: { id: 'hp', name: 'Himachal Pradesh', x: 191, y: 133, width: 72, height: 71, zone: 'North' },
  jk: { id: 'jk', name: 'Jammu and Kashmir', x: 173, y: 61, width: 160, height: 122, zone: 'North' },
  jh: { id: 'jh', name: 'Jharkhand', x: 366, y: 327, width: 97, height: 77, zone: 'East' },
  ka: { id: 'ka', name: 'Karnataka', x: 171, y: 519, width: 94, height: 149, zone: 'South' },
  kl: { id: 'kl', name: 'Kerala', x: 166, y: 615, width: 53, height: 96, zone: 'South' },
  ld: { id: 'ld', name: 'Lakshadweep', x: 99, y: 627, width: 34, height: 73, zone: 'South' },
  mp: { id: 'mp', name: 'Madhya Pradesh', x: 214, y: 319, width: 184, height: 133, zone: 'Central' },
  mh: { id: 'mh', name: 'Maharashtra', x: 180, y: 435, width: 173, height: 142, zone: 'West' },
  mn: { id: 'mn', name: 'Manipur', x: 537, y: 301, width: 37, height: 43, zone: 'North-East' },
  ml: { id: 'ml', name: 'Meghalaya', x: 484, y: 283, width: 62, height: 25, zone: 'North-East' },
  mz: { id: 'mz', name: 'Mizoram', x: 516, y: 337, width: 25, height: 59, zone: 'North-East' },
  nl: { id: 'nl', name: 'Nagaland', x: 546, y: 270, width: 40, height: 43, zone: 'North-East' },
  or: { id: 'or', name: 'Odisha', x: 340, y: 405, width: 128, height: 106, zone: 'East' },
  py: { id: 'py', name: 'Puducherry', x: 268, y: 546, width: 56, height: 128, zone: 'South' },
  pb: { id: 'pb', name: 'Punjab', x: 151, y: 152, width: 64, height: 74, zone: 'North' },
  rj: { id: 'rj', name: 'Rajasthan', x: 119, y: 257, width: 184, height: 168, zone: 'North' },
  sk: { id: 'sk', name: 'Sikkim', x: 425, y: 235, width: 19, height: 25, zone: 'North-East' },
  tn: { id: 'tn', name: 'Tamil Nadu', x: 211, y: 609, width: 86, height: 117, zone: 'South' },
  tg: { id: 'tg', name: 'Telangana', x: 237, y: 457, width: 95, height: 90, zone: 'South' },
  tr: { id: 'tr', name: 'Tripura', x: 493, y: 325, width: 25, height: 36, zone: 'North-East' },
  up: { id: 'up', name: 'Uttar Pradesh', x: 265, y: 245, width: 158, height: 154, zone: 'North' },
  ut: { id: 'ut', name: 'Uttarakhand', x: 232, y: 175, width: 72, height: 67, zone: 'North' },
  wb: { id: 'wb', name: 'West Bengal', x: 412, y: 310, width: 85, height: 131, zone: 'East' },
}

export const REGIONAL_ZONES = {
  North: { name: 'North Zone', x: 185, y: 190, states: ['jk', 'hp', 'pb', 'ch', 'ut', 'hr', 'dl', 'rj', 'up'] },
  South: { name: 'South Zone', x: 210, y: 535, states: ['ap', 'tg', 'ka', 'kl', 'tn', 'py', 'ld'] },
  West: { name: 'West Zone', x: 120, y: 395, states: ['gj', 'mh', 'ga', 'dn', 'dd'] },
  Central: { name: 'Central Zone', x: 255, y: 350, states: ['mp', 'ct'] },
  East: { name: 'East Zone', x: 370, y: 330, states: ['br', 'jh', 'or', 'wb', 'an'] },
  'North-East': { name: 'North-East Zone', x: 520, y: 275, states: ['as', 'sk', 'ar', 'nl', 'mn', 'mz', 'tr', 'ml'] },
}

export function normalizeStateName(name) {
  if (!name) return ''
  const s = String(name).toLowerCase().replace(/[^a-z0-9]/g, '')
  if (s.includes('orissa') || s.includes('odisha')) return 'odisha'
  if (s.includes('uttaranchal') || s.includes('uttarakhand')) return 'uttarakhand'
  if (s.includes('chhatisgarh') || s.includes('chhattisgarh')) return 'chhattisgarh'
  if (s.includes('pondicherry') || s.includes('puducherry')) return 'puducherry'
  if (s.includes('daman') || s.includes('diu') || s.includes('dadra') || s.includes('haveli')) return 'dnhdd'
  if (s.includes('jammu') || s.includes('kashmir')) return 'jammukashmir'
  return s
}

export const MAP_METRICS = {
  cases: {
    id: 'cases',
    label: 'Case Burden',
    unit: 'cases',
    description: 'Estimated rare disease patient volume',
    scale: ['#e0f2fe', '#7dd3fc', '#0284c7', '#0369a1', '#004a7c'],
    getValue: (s) => (s && typeof s.cases === 'number' ? s.cases : null),
    format: (v) => (v != null ? v.toLocaleString('en-IN') : 'Unavailable'),
  },
  confirmed: {
    id: 'confirmed',
    label: 'Confirmed Cases',
    unit: 'confirmed',
    description: 'Molecularly & clinically verified diagnoses',
    scale: ['#ccfbf1', '#5eead4', '#0d9488', '#0f766e', '#115e59'],
    getValue: (s) => (s && typeof s.confirmed === 'number' ? s.confirmed : null),
    format: (v) => (v != null ? v.toLocaleString('en-IN') : 'Unavailable'),
  },
  access_gap: {
    id: 'access_gap',
    label: 'Access Deficit',
    unit: 'ratio',
    description: 'Cases per diagnostic facility (specialist + NABL lab)',
    scale: ['#fef3c7', '#fde047', '#f59e0b', '#ea580c', '#b91c1c'],
    getValue: (s) => (s && typeof s.access_gap_score === 'number' ? s.access_gap_score : null),
    format: (v) => (v != null ? `${v.toFixed(1)}:1` : 'Unavailable'),
  },
  consanguinity: {
    id: 'consanguinity',
    label: 'Consanguinity Rate',
    unit: '%',
    description: 'Regional endogamy & kinship rate (NFHS-5)',
    scale: ['#ede9fe', '#c4b5fd', '#8b5cf6', '#6d28d9', '#4c1d95'],
    getValue: (s) => (s && typeof s.consanguinity_rate === 'number' ? s.consanguinity_rate : null),
    format: (v) => (v != null ? `${v.toFixed(1)}%` : 'Unavailable'),
  },
}

export function getChoroplethColor(value, min, max, scale) {
  if (value == null || isNaN(value)) {
    return '#e2e8f0' // Clear, crisp neutral slate for unreported states
  }
  if (min === max || max <= min) {
    return scale[2]
  }
  const t = Math.max(0, Math.min(1, (value - min) / (max - min)))
  const idx = Math.min(scale.length - 1, Math.floor(t * (scale.length - 1)))
  return scale[idx]
}
