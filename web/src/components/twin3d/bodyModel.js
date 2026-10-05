// Procedural anatomical reference (no external asset): primitives positioned in a standing anterior view.
// +x is the viewer's right (the patient's left), +z faces the viewer. Body height is about 4 units.
// Each organ belongs to one display system. `tint` is a muted reference colour used only when the system has
// no data and is not selected; it carries no clinical meaning (and is never red). See PLAN.md section 29/30.
export const ORGANS = [
  { id: 'brain-l', label: 'Brain', system: 'nervous', shape: 'sphere', p: [-0.075, 1.63, -0.01], s: [0.13, 0.12, 0.17], tint: '#8ea9e0' },
  { id: 'brain-r', label: 'Brain', system: 'nervous', shape: 'sphere', p: [0.075, 1.63, -0.01], s: [0.13, 0.12, 0.17], tint: '#8ea9e0' },
  { id: 'cerebellum', label: 'Cerebellum', system: 'nervous', shape: 'sphere', p: [0, 1.5, -0.12], s: [0.1, 0.05, 0.06], tint: '#8ea9e0' },
  { id: 'cord', label: 'Spinal cord', system: 'nervous', shape: 'cyl', p: [0, 0.55, -0.15], s: [0.022, 1.75, 0.022], tint: '#a9c4f0' },
  { id: 'eye-l', label: 'Eye', system: 'ocular', shape: 'sphere', p: [-0.075, 1.55, 0.19], s: [0.035, 0.035, 0.035], tint: '#d7e6ff' },
  { id: 'eye-r', label: 'Eye', system: 'ocular', shape: 'sphere', p: [0.075, 1.55, 0.19], s: [0.035, 0.035, 0.035], tint: '#d7e6ff' },
  { id: 'thyroid', label: 'Thyroid', system: 'endocrine', shape: 'sphere', p: [0, 1.2, 0.08], s: [0.07, 0.035, 0.035], tint: '#c7a6e8' },
  { id: 'adrenal-l', label: 'Adrenal gland', system: 'endocrine', shape: 'sphere', p: [-0.16, 0.44, -0.1], s: [0.04, 0.025, 0.03], tint: '#c7a6e8' },
  { id: 'adrenal-r', label: 'Adrenal gland', system: 'endocrine', shape: 'sphere', p: [0.16, 0.44, -0.1], s: [0.04, 0.025, 0.03], tint: '#c7a6e8' },
  { id: 'lung-l', label: 'Lung', system: 'respiratory', shape: 'sphere', p: [-0.19, 0.84, 0], s: [0.14, 0.29, 0.14], tint: '#7fc2e6' },
  { id: 'lung-r', label: 'Lung', system: 'respiratory', shape: 'sphere', p: [0.19, 0.84, 0], s: [0.14, 0.29, 0.14], tint: '#7fc2e6' },
  { id: 'trachea', label: 'Trachea', system: 'respiratory', shape: 'cyl', p: [0, 1.12, 0.02], s: [0.025, 0.22, 0.025], tint: '#7fc2e6' },
  { id: 'heart', label: 'Heart', system: 'cardiovascular', shape: 'sphere', p: [0.05, 0.74, 0.1], s: [0.09, 0.11, 0.085], tint: '#d59ac6' },
  { id: 'aorta', label: 'Aorta', system: 'cardiovascular', shape: 'cyl', p: [0.025, 0.25, -0.05], s: [0.02, 1.05, 0.02], tint: '#d59ac6' },
  { id: 'liver', label: 'Liver', system: 'hepatic', shape: 'sphere', p: [-0.17, 0.42, 0.07], s: [0.23, 0.115, 0.13], tint: '#c79a6e' },
  { id: 'stomach', label: 'Stomach', system: 'digestive', shape: 'sphere', p: [0.14, 0.41, 0.09], s: [0.11, 0.09, 0.08], tint: '#d9b98a' },
  { id: 'bowel', label: 'Intestines', system: 'digestive', shape: 'torus', p: [0, 0.03, 0.06], s: [0.18, 0.18, 0.11], tint: '#d6b49a' },
  { id: 'spleen', label: 'Spleen', system: 'immune', shape: 'sphere', p: [0.28, 0.38, -0.03], s: [0.05, 0.09, 0.05], tint: '#a98ad6' },
  { id: 'thymus', label: 'Thymus', system: 'immune', shape: 'sphere', p: [0, 0.98, 0.1], s: [0.05, 0.05, 0.03], tint: '#a98ad6' },
  { id: 'kidney-l', label: 'Kidney', system: 'renal', shape: 'sphere', p: [-0.15, 0.3, -0.11], s: [0.05, 0.085, 0.045], tint: '#b48ad0' },
  { id: 'kidney-r', label: 'Kidney', system: 'renal', shape: 'sphere', p: [0.15, 0.3, -0.11], s: [0.05, 0.085, 0.045], tint: '#b48ad0' },
  { id: 'bladder', label: 'Bladder', system: 'renal', shape: 'sphere', p: [0, -0.28, 0.08], s: [0.055, 0.05, 0.05], tint: '#b48ad0' },
  { id: 'repro', label: 'Reproductive organs', system: 'reproductive', shape: 'sphere', p: [0, -0.4, 0.03], s: [0.07, 0.045, 0.045], tint: '#9fb6e8' },
  { id: 'spine', label: 'Spine', system: 'musculoskeletal', shape: 'cyl', p: [0, 0.5, -0.19], s: [0.04, 1.65, 0.04], tint: '#e3e9f2' },
  { id: 'pelvis', label: 'Pelvis', system: 'musculoskeletal', shape: 'torus', p: [0, -0.32, -0.03], s: [0.24, 0.13, 0.1], tint: '#e3e9f2' },
  { id: 'femur-l', label: 'Femur', system: 'musculoskeletal', shape: 'cyl', p: [-0.18, -1.02, 0], s: [0.035, 0.95, 0.035], tint: '#e3e9f2' },
  { id: 'femur-r', label: 'Femur', system: 'musculoskeletal', shape: 'cyl', p: [0.18, -1.02, 0], s: [0.035, 0.95, 0.035], tint: '#e3e9f2' },
  { id: 'tibia-l', label: 'Tibia', system: 'musculoskeletal', shape: 'cyl', p: [-0.18, -1.95, 0], s: [0.028, 0.8, 0.028], tint: '#e3e9f2' },
  { id: 'tibia-r', label: 'Tibia', system: 'musculoskeletal', shape: 'cyl', p: [0.18, -1.95, 0], s: [0.028, 0.8, 0.028], tint: '#e3e9f2' },
  { id: 'humerus-l', label: 'Humerus', system: 'musculoskeletal', shape: 'cyl', p: [-0.55, 0.72, 0], s: [0.026, 0.6, 0.026], r: [0, 0, 0.12], tint: '#e3e9f2' },
  { id: 'humerus-r', label: 'Humerus', system: 'musculoskeletal', shape: 'cyl', p: [0.55, 0.72, 0], s: [0.026, 0.6, 0.026], r: [0, 0, -0.12], tint: '#e3e9f2' },
  { id: 'sternum', label: 'Sternum (bone marrow)', system: 'hematologic', shape: 'box', p: [0, 0.8, 0.19], s: [0.045, 0.38, 0.02], tint: '#e8d9b0' },
]

// Ribs: thin open arcs around the thorax (musculoskeletal).
export const RIBS = Array.from({ length: 9 }, (_, i) => ({ y: 1.02 - i * 0.075, rx: 0.3 + Math.sin((i / 8) * Math.PI) * 0.06, rz: 0.2 }))

// Smooth trunk profile (radius, y) from the base of the neck to the hips; lathed and flattened in z.
export const TORSO_PROFILE = [
  [0.07, 1.33], [0.09, 1.27], [0.2, 1.21], [0.37, 1.13], [0.42, 1.0], [0.41, 0.82], [0.38, 0.62],
  [0.33, 0.42], [0.3, 0.22], [0.33, 0.0], [0.37, -0.2], [0.38, -0.36], [0.33, -0.48], [0.2, -0.55], [0.0, -0.57],
]

// Tapered limb segments: [x, yTop, yBottom, rTop, rBottom, tiltZ]
export const LIMB_SEGMENTS = [
  [-0.5, 1.08, 0.42, 0.085, 0.065, 0.12], [0.5, 1.08, 0.42, 0.085, 0.065, -0.12],
  [-0.6, 0.42, -0.18, 0.062, 0.045, 0.06], [0.6, 0.42, -0.18, 0.062, 0.045, -0.06],
  [-0.19, -0.45, -1.48, 0.15, 0.095, 0], [0.19, -0.45, -1.48, 0.15, 0.095, 0],
  [-0.19, -1.5, -2.38, 0.09, 0.055, 0], [0.19, -1.5, -2.38, 0.09, 0.055, 0],
]
export const JOINTS = [
  [-0.5, 1.08, 0.1], [0.5, 1.08, 0.1], [-0.56, 0.42, 0.066], [0.56, 0.42, 0.066],
  [-0.62, -0.2, 0.05], [0.62, -0.2, 0.05], [-0.19, -1.49, 0.095], [0.19, -1.49, 0.095],
]
export const HANDS = [[-0.63, -0.33], [0.63, -0.33]]
export const FEET = [[-0.19, -2.43], [0.19, -2.43]]

// Continuous limbs (lathed profiles hanging from the shoulder / hip): [x, yTop, tiltZ, profile(r, dy)]
const ARM = [[0.0, 0.0], [0.07, -0.02], [0.088, -0.12], [0.078, -0.35], [0.062, -0.6], [0.058, -0.66], [0.064, -0.8], [0.05, -1.1], [0.04, -1.24], [0.045, -1.3], [0.05, -1.42], [0.035, -1.52], [0.0, -1.56]]
const LEG = [[0.0, 0.0], [0.13, -0.03], [0.155, -0.15], [0.14, -0.55], [0.1, -0.98], [0.088, -1.06], [0.098, -1.3], [0.07, -1.7], [0.052, -1.9], [0.055, -1.97], [0.0, -2.0]]
export const LIMB_LATHES = [
  { x: -0.47, y: 1.12, tilt: 0.11, profile: ARM },
  { x: 0.47, y: 1.12, tilt: -0.11, profile: ARM },
  { x: -0.19, y: -0.42, tilt: 0.0, profile: LEG },
  { x: 0.19, y: -0.42, tilt: 0.0, profile: LEG },
]
