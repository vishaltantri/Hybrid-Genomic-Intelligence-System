import React, { useEffect, useMemo, useRef, useState } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { OrbitControls, Html, Line, QuadraticBezierLine, Stars } from '@react-three/drei'
import { EffectComposer, Bloom, Vignette } from '@react-three/postprocessing'
import * as THREE from 'three'
import { ORGANS, RIBS, TORSO_PROFILE, LIMB_LATHES, FEET } from './bodyModel.js'
import { CAMERA_VIEWS, SYSTEM_STATE } from './webgl.js'

/**
 * Dark holographic WebGL stage.
 *  - mode 'anatomy' : procedural reference body (rim-lit shell, skeleton hint, organs) + a small genome helix that is
 *                     linked to organ systems ONLY when the selected variant/gene has a knowledge-graph-backed link.
 *  - mode 'dna'     : large DNA double helix with the selected variant marked.
 * Colour encodes data only: neutral tint = no case data, blue = case data, cyan = linked to selection, mint = selected.
 */

const BASES = ['A', 'T', 'G', 'C']
const COMP = { A: 'T', T: 'A', G: 'C', C: 'G' }
const BASE_COLOR = { A: '#3fa9ff', T: '#7fd8ff', G: '#21c7b7', C: '#8ff0d8' }
const STATE_STYLE = {
  case: { color: '#3aa8ff', emissive: 0.75, opacity: 0.9 },
  linked: { color: '#4fe3ff', emissive: 1.35, opacity: 0.95 },
  selected: { color: '#33f5c4', emissive: 1.8, opacity: 1 },
}
const SYSTEM_IDS = ['nervous', 'ocular', 'cardiovascular', 'respiratory', 'digestive', 'hepatic', 'renal', 'endocrine',
  'musculoskeletal', 'hematologic', 'immune', 'reproductive', 'integumentary']

function holoMaterial({ color = '#4fc3ff', rim = '#9fe8ff', opacity = 0.05, power = 2.4, strength = 0.9 }) {
  return new THREE.ShaderMaterial({
    uniforms: {
      uColor: { value: new THREE.Color(color) },
      uRim: { value: new THREE.Color(rim) },
      uOpacity: { value: opacity },
      uPower: { value: power },
      uStrength: { value: strength },
    },
    vertexShader: `
      varying vec3 vN; varying vec3 vV;
      void main(){
        vec4 mv = modelViewMatrix * vec4(position,1.0);
        vN = normalize(normalMatrix * normal); vV = normalize(-mv.xyz);
        gl_Position = projectionMatrix * mv;
      }`,
    fragmentShader: `
      uniform vec3 uColor; uniform vec3 uRim; uniform float uOpacity; uniform float uPower; uniform float uStrength;
      varying vec3 vN; varying vec3 vV;
      void main(){
        float f = pow(1.0 - abs(dot(normalize(vN), normalize(vV))), uPower);
        vec3 c = mix(uColor, uRim, f);
        gl_FragColor = vec4(c * (0.35 + f * 1.6), uOpacity + f * uStrength);
      }`,
    transparent: true,
    depthWrite: false,
    side: THREE.FrontSide,
    blending: THREE.AdditiveBlending,
  })
}

function CameraRig({ goal }) {
  const { camera, controls, invalidate } = useThree()
  const target = useRef(null)
  useEffect(() => {
    if (!goal) return
    target.current = { pos: new THREE.Vector3(...goal.pos), look: new THREE.Vector3(...goal.target) }
    invalidate()
  }, [goal, invalidate])
  useFrame((_, dt) => {
    const t = target.current
    if (!t) return
    const k = 1 - Math.pow(0.0005, dt)
    camera.position.lerp(t.pos, k)
    if (controls) {
      controls.target.lerp(t.look, k)
      controls.update()
    }
    if (camera.position.distanceTo(t.pos) < 0.02) target.current = null
    else invalidate()
  })
  return null
}

// ----------------------------- body -----------------------------

function Organ({ organ, state, geoms, onSelect, onHover, pulse }) {
  const mat = useRef()
  const st = STATE_STYLE[state]
  const color = st ? st.color : organ.tint
  useFrame(({ clock }) => {
    if (!mat.current) return
    const base = st ? st.emissive : 0.18
    mat.current.emissiveIntensity = pulse && st && state !== 'case' ? base + 0.35 * Math.sin(clock.elapsedTime * 2.4) : base
  })
  return (
    <mesh
      geometry={geoms[organ.shape]} position={organ.p} rotation={organ.r || [0, 0, 0]} scale={organ.s}
      onClick={(e) => { e.stopPropagation(); onSelect(organ.system) }}
      onPointerOver={(e) => { e.stopPropagation(); document.body.style.cursor = 'pointer'; onHover({ label: organ.label, p: organ.p }) }}
      onPointerOut={() => { document.body.style.cursor = ''; onHover(null) }}
    >
      <meshPhysicalMaterial ref={mat} color={color} emissive={color} emissiveIntensity={0.18} roughness={0.35} metalness={0.1}
        clearcoat={0.6} transparent opacity={st ? st.opacity : 0.55} depthWrite={!!st} />
    </mesh>
  )
}

function Body({ states, onSelectSystem, low, pulse, systemsData, selectedSystem, linkedSystems, showCallouts, helixLink }) {
  const [hover, setHover] = useState(null)
  const seg = low ? 14 : 36
  const geoms = useMemo(() => ({
    sphere: new THREE.SphereGeometry(1, seg, Math.max(10, seg / 2)),
    cyl: new THREE.CylinderGeometry(1, 1, 1, Math.max(8, seg / 3)),
    box: new THREE.BoxGeometry(1, 1, 1),
    torus: new THREE.TorusGeometry(1, 0.35, 12, seg),
  }), [seg])
  const shell = useMemo(() => holoMaterial({}), [])
  const shellInner = useMemo(() => holoMaterial({ color: '#1b5fa8', rim: '#4fc3ff', opacity: 0.02, power: 1.4, strength: 0.25 }), [])
  const torso = useMemo(() => {
    const curve = new THREE.CatmullRomCurve3(TORSO_PROFILE.map(([r, y]) => new THREE.Vector3(r, y, 0)))
    return new THREE.LatheGeometry(curve.getPoints(48).map((v) => new THREE.Vector2(Math.max(v.x, 0.001), v.y)), seg)
  }, [seg])
  const limbs = useMemo(() => LIMB_LATHES.map((l) => {
    const curve = new THREE.CatmullRomCurve3(l.profile.map(([rr, dy]) => new THREE.Vector3(rr, dy, 0)))
    return {
      geo: new THREE.LatheGeometry(curve.getPoints(40).map((v) => new THREE.Vector2(Math.max(v.x, 0.001), v.y)), Math.max(12, seg / 2)),
      p: [l.x, l.y, 0], r: [0, 0, l.tilt],
    }
  }), [seg])
  const rib = useMemo(() => new THREE.TorusGeometry(1, 0.035, 6, Math.max(16, seg), Math.PI * 1.45), [seg])
  useEffect(() => () => {
    Object.values(geoms).forEach((g) => g.dispose())
    ;[torso, rib, shell, shellInner].forEach((g) => g.dispose())
    limbs.forEach((l) => l.geo.dispose())
  }, [geoms, torso, rib, shell, shellInner, limbs])
  const skeletonStyle = STATE_STYLE[states.musculoskeletal]
  const ribColor = skeletonStyle?.color || '#c9d8ea'

  const callouts = useMemo(() => {
    const extra = { integumentary: [0.4, -0.05, 0.1] } // skin has no organ mesh: anchor on the body surface
    const anchor = (sid) => ORGANS.find((o) => o.system === sid)?.p || extra[sid]
    const ids = new Set()
    if (showCallouts) systemsData.filter((s) => s.has_case_data).forEach((s) => ids.add(s.id))
    if (selectedSystem) ids.add(selectedSystem)
    ;(linkedSystems || []).forEach((id) => ids.add(id))
    const rows = [...ids].map((id) => ({ sys: systemsData.find((s) => s.id === id), p: anchor(id) }))
      .filter((r) => r.sys && r.p).sort((x, y) => y.p[1] - x.p[1]).slice(0, 8)
    const last = { '-1': Infinity, '1': Infinity }
    return rows.map((r, i) => {
      const side = i % 2 === 0 ? -1 : 1
      const y = Math.min(r.p[1] + 0.1, last[side] - 0.5)
      last[side] = y
      return { ...r, label: [side * 1.15, y, 0.15] }
    })
  }, [showCallouts, systemsData, selectedSystem, linkedSystems])

  return (
    <group position={[0, -0.25, 0]}>
      <mesh geometry={torso} scale={[1, 1, 0.58]} material={shell} />
      <mesh geometry={torso} scale={[0.985, 0.99, 0.56]} material={shellInner} />
      <mesh position={[0, 1.6, 0]} scale={[0.22, 0.27, 0.24]} material={shell}><sphereGeometry args={[1, seg, seg / 2]} /></mesh>
      <mesh position={[0, 1.4, 0.02]} scale={[0.15, 0.1, 0.16]} material={shell}><sphereGeometry args={[1, seg / 2, seg / 4]} /></mesh>
      {limbs.map((l, i) => <mesh key={i} geometry={l.geo} position={l.p} rotation={l.r} scale={[1, 1, 0.85]} material={shell} />)}
      {FEET.map(([x, y], i) => <mesh key={`f${i}`} position={[x, y, 0.07]} scale={[0.06, 0.04, 0.14]} material={shell}><sphereGeometry args={[1, 16, 12]} /></mesh>)}

      {RIBS.map((r, i) => (
        <mesh key={`rib${i}`} geometry={rib} position={[0, r.y, -0.02]} rotation={[Math.PI / 2, 0, -Math.PI * 0.22]} scale={[r.rx, r.rz, 0.6]}
          onClick={(e) => { e.stopPropagation(); onSelectSystem('musculoskeletal') }}>
          <meshStandardMaterial color={ribColor} emissive={ribColor} emissiveIntensity={skeletonStyle ? 1.1 : 0.12} transparent opacity={0.45} />
        </mesh>
      ))}

      {ORGANS.map((o) => (
        <Organ key={o.id} organ={o} state={states[o.system] || 'neutral'} geoms={geoms} onSelect={onSelectSystem} onHover={setHover} pulse={pulse} />
      ))}

      {callouts.map((c) => (
        <group key={`c-${c.sys.id}`}>
          <Line points={[c.p, [c.label[0] * 0.55, c.label[1], 0.1], c.label]} color={c.sys.id === selectedSystem ? '#33f5c4' : '#4fc3ff'}
            lineWidth={1} transparent opacity={0.7} />
          <Html position={c.label} center zIndexRange={[30, 0]} distanceFactor={5.5}>
            <button onClick={() => onSelectSystem(c.sys.id)}
              className="whitespace-nowrap text-left px-2.5 py-1.5 rounded-lg border bg-[#071426]/85 backdrop-blur text-[11px] leading-tight shadow-lg"
              style={{ borderColor: c.sys.id === selectedSystem ? '#33f5c4' : 'rgba(79,195,255,0.55)', color: '#dff4ff' }}>
              <span className="block font-semibold tracking-wide">{c.sys.label}</span>
              <span className="block text-[10px]" style={{ color: '#8fc9ee' }}>
                {c.sys.has_case_data
                  ? `${c.sys.phenotypes.length} phenotype${c.sys.phenotypes.length === 1 ? '' : 's'} · ${c.sys.genes.join(', ') || 'no gene'}`
                  : 'no case data'}
              </span>
            </button>
          </Html>
        </group>
      ))}

      {helixLink}

      {hover && (
        <Html position={[hover.p[0], hover.p[1] + 0.14, hover.p[2] + 0.25]} center distanceFactor={8} zIndexRange={[40, 0]}>
          <div className="pointer-events-none px-2 py-1 rounded-md border text-[11px] font-semibold whitespace-nowrap"
            style={{ background: 'rgba(7,20,38,0.9)', borderColor: 'rgba(79,195,255,0.6)', color: '#dff4ff' }}>
            {hover.label}
          </div>
        </Html>
      )}
    </group>
  )
}

function Platform({ reduced }) {
  const ring = useRef()
  useFrame((_, dt) => {
    if (ring.current && !reduced) ring.current.rotation.z += dt * 0.15
  })
  return (
    <group position={[0, -2.78, 0]} rotation={[-Math.PI / 2, 0, 0]}>
      <mesh><circleGeometry args={[1.25, 64]} /><meshBasicMaterial color="#0a3a66" transparent opacity={0.35} /></mesh>
      <mesh ref={ring}><ringGeometry args={[1.18, 1.24, 96, 1, 0, Math.PI * 1.6]} /><meshBasicMaterial color="#4fc3ff" transparent opacity={0.85} side={THREE.DoubleSide} /></mesh>
      <mesh><ringGeometry args={[0.78, 0.8, 96]} /><meshBasicMaterial color="#2a8fd6" transparent opacity={0.6} side={THREE.DoubleSide} /></mesh>
    </group>
  )
}

// ----------------------------- DNA -----------------------------

function seqFor(i) {
  const x = Math.sin(i * 12.9898) * 43758.5453
  return BASES[Math.floor((x - Math.floor(x)) * 4)]
}

function Helix({ markers, low, reduced, onSelectVariant, onHoverRung, interactive = true, speed = 0.22 }) {
  const group = useRef()
  const N = low ? 22 : 40
  const R = 0.62
  const H = 5.4
  const turns = 3.4
  const pts = useMemo(() => {
    const a = []
    const b = []
    for (let i = 0; i < N; i++) {
      const t = i / (N - 1)
      const ang = t * turns * Math.PI * 2
      const y = (t - 0.5) * H
      a.push(new THREE.Vector3(R * Math.cos(ang), y, R * Math.sin(ang)))
      b.push(new THREE.Vector3(R * Math.cos(ang + Math.PI), y, R * Math.sin(ang + Math.PI)))
    }
    return { a, b }
  }, [N])
  const tubes = useMemo(() => {
    const mk = (arr) => new THREE.TubeGeometry(new THREE.CatmullRomCurve3(arr), N * 5, 0.05, low ? 6 : 12, false)
    return [mk(pts.a), mk(pts.b)]
  }, [pts, N, low])
  const markerRungs = useMemo(() => {
    const m = new Map()
    markers.forEach((mk) => m.set(Math.max(1, Math.min(N - 2, Math.round(mk.fraction * (N - 1)))), mk))
    return m
  }, [markers, N])
  const rungs = useMemo(() => pts.a.map((pa, i) => {
    const mk = markerRungs.get(i)
    let b1 = seqFor(i)
    if (mk && mk.ref && mk.ref.length === 1 && BASES.includes(mk.ref.toUpperCase())) b1 = mk.ref.toUpperCase()
    return { i, pa, pb: pts.b[i], b1, b2: COMP[b1], marker: mk }
  }), [pts, markerRungs])
  const [hoverIdx, setHoverIdx] = useState(null)
  const cyl = useMemo(() => new THREE.CylinderGeometry(0.03, 0.03, 1, 8), [])
  const ball = useMemo(() => new THREE.SphereGeometry(0.075, 16, 12), [])
  useEffect(() => () => { tubes.forEach((t) => t.dispose()); cyl.dispose(); ball.dispose() }, [tubes, cyl, ball])
  useFrame((_, dt) => {
    if (group.current && !reduced) group.current.rotation.y += dt * speed
  })
  const half = (r, side) => {
    const from = side === 0 ? r.pa : r.pb
    const mid = new THREE.Vector3(0, r.pa.y, 0)
    const dir = new THREE.Vector3().subVectors(mid, from)
    return {
      pos: new THREE.Vector3().addVectors(from, mid).multiplyScalar(0.5),
      q: new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir.clone().normalize()),
      len: dir.length(),
    }
  }
  return (
    <group ref={group}>
      {tubes.map((g, k) => (
        <mesh key={k} geometry={g}>
          <meshStandardMaterial color={k === 0 ? '#2f9bff' : '#22d3c5'} emissive={k === 0 ? '#2f9bff' : '#22d3c5'} emissiveIntensity={0.7} roughness={0.3} metalness={0.2} />
        </mesh>
      ))}
      {rungs.map((r) => [0, 1].map((side) => {
        const h = half(r, side)
        const base = side === 0 ? r.b1 : r.b2
        const hot = r.i === hoverIdx || !!r.marker
        return (
          <mesh key={`${r.i}-${side}`} geometry={cyl} position={h.pos} quaternion={h.q} scale={[hot ? 1.7 : 1, h.len, hot ? 1.7 : 1]}
            onPointerOver={interactive ? (e) => { e.stopPropagation(); setHoverIdx(r.i); onHoverRung?.({ index: r.i + 1, bases: `${r.b1}-${r.b2}`, marker: r.marker || null }) } : undefined}
            onPointerOut={interactive ? () => { setHoverIdx(null); onHoverRung?.(null) } : undefined}>
            <meshStandardMaterial color={BASE_COLOR[base]} emissive={BASE_COLOR[base]} emissiveIntensity={hot ? 1.4 : 0.35} roughness={0.4} />
          </mesh>
        )
      }))}
      {rungs.filter((r) => r.marker).map((r) => (
        <group key={`m-${r.i}`} position={[0, r.pa.y, 0]}>
          <mesh geometry={ball} position={[R + 0.3, 0, 0]} scale={1.8}
            onClick={interactive ? (e) => { e.stopPropagation(); onSelectVariant?.(r.marker.variant_id) } : undefined}>
            <meshStandardMaterial color="#33f5c4" emissive="#33f5c4" emissiveIntensity={2.2} />
          </mesh>
          <mesh rotation={[Math.PI / 2, 0, 0]}>
            <torusGeometry args={[R + 0.14, 0.014, 8, 64]} />
            <meshStandardMaterial color="#33f5c4" emissive="#33f5c4" emissiveIntensity={1.8} />
          </mesh>
        </group>
      ))}
    </group>
  )
}

/** Small genome helix beside the body; links are drawn only to systems the selection is knowledge-graph-linked to. */
function GenomeLink({ markers, linkedSystems, label, low, reduced }) {
  const origin = [1.6, 0.3, 0]
  const targets = (linkedSystems || []).map((sid) => ORGANS.find((o) => o.system === sid)?.p).filter(Boolean)
  return (
    <group>
      <group position={origin} scale={0.4}>
        <Helix markers={markers} low={low} reduced={reduced} interactive={false} speed={0.5} />
      </group>
      {targets.map((t, i) => (
        <QuadraticBezierLine key={i} start={[origin[0] - 0.28, origin[1], 0]} end={t}
          mid={[(origin[0] + t[0]) / 2, Math.max(origin[1], t[1]) + 0.45, 0.35]}
          color="#4fe3ff" lineWidth={1.4} dashed dashScale={20} transparent opacity={0.85} />
      ))}
      <Html position={[origin[0], origin[1] + 1.35, 0]} center distanceFactor={5.5} zIndexRange={[25, 0]}>
        <div className="pointer-events-none whitespace-nowrap text-center px-2 py-1 rounded-md border text-[10px]"
          style={{ background: 'rgba(7,20,38,0.8)', borderColor: 'rgba(79,195,255,0.4)', color: '#bfe6ff' }}>
          {label || 'Genome layer — select a variant to link it'}
        </div>
      </Html>
    </group>
  )
}

export default function Stage3D({
  mode, goal, selectedSystem, linkedSystems, caseSystems, onSelectSystem, dnaMarkers, onSelectVariant, onHoverRung,
  low, reduced, autoRotate, onUserInteract, systemsData, showCallouts, genomeLabel,
}) {
  const states = useMemo(() => {
    const out = {}
    SYSTEM_IDS.forEach((id) => { out[id] = SYSTEM_STATE(id, { selectedSystem, linkedSystems, caseSystems }) })
    return out
  }, [selectedSystem, linkedSystems, caseSystems])
  const hasHighlight = Object.values(states).some((s) => s === 'selected' || s === 'linked')
  const isDna = mode === 'dna'
  const spinning = autoRotate && !reduced
  return (
    <Canvas
      frameloop={reduced && !isDna ? 'demand' : 'always'}
      dpr={low ? [1, 1] : [1, 1.75]}
      camera={{ position: CAMERA_VIEWS.front.pos, fov: 38, near: 0.1, far: 80 }}
      gl={{ antialias: !low, powerPreference: low ? 'low-power' : 'high-performance', alpha: false }}
      style={{ touchAction: 'none' }}
      aria-label={isDna ? 'Interactive 3D DNA double helix' : 'Interactive 3D anatomical reference body'}
    >
      <color attach="background" args={['#040b18']} />
      <fog attach="fog" args={['#040b18', 12, 26]} />
      <ambientLight intensity={0.45} />
      <directionalLight position={[3, 6, 6]} intensity={1.0} color="#d8eeff" />
      <pointLight position={[-4, 1, 3]} intensity={14} distance={14} color="#2f9bff" />
      <pointLight position={[4, -1, -3]} intensity={10} distance={14} color="#22d3c5" />
      {!low && <Stars radius={40} depth={20} count={700} factor={2} saturation={0} fade speed={reduced ? 0 : 0.4} />}
      <CameraRig goal={goal} />
      <OrbitControls makeDefault enableDamping dampingFactor={0.08} enablePan minDistance={2.2} maxDistance={16}
        maxPolarAngle={Math.PI * 0.92} autoRotate={spinning && !isDna} autoRotateSpeed={0.7} onStart={onUserInteract} />
      {isDna ? (
        <Helix markers={dnaMarkers || []} low={low} reduced={reduced} onSelectVariant={onSelectVariant} onHoverRung={onHoverRung} />
      ) : (
        <>
          <Body
            states={states} onSelectSystem={onSelectSystem} low={low} pulse={!reduced && hasHighlight}
            systemsData={systemsData || []} selectedSystem={selectedSystem} linkedSystems={linkedSystems} showCallouts={showCallouts}
            helixLink={<GenomeLink markers={dnaMarkers || []} linkedSystems={linkedSystems} label={genomeLabel} low={low} reduced={reduced} />}
          />
          <Platform reduced={reduced} />
        </>
      )}
      {!low && (
        <EffectComposer multisampling={0} disableNormalPass>
          <Bloom intensity={0.85} luminanceThreshold={0.22} luminanceSmoothing={0.3} mipmapBlur />
          <Vignette eskil={false} offset={0.25} darkness={0.75} />
        </EffectComposer>
      )}
    </Canvas>
  )
}
