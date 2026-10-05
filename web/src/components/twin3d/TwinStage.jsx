import React, { Suspense, lazy, useEffect, useMemo, useRef, useState } from 'react'
import { Maximize2, Minimize2, Pause, Play } from 'lucide-react'
import BodyFallback2D from './BodyFallback2D.jsx'
import DnaFallback2D from './DnaFallback2D.jsx'
import GenomeView from './GenomeView.jsx'
import TwinTimeline from './TwinTimeline.jsx'
import { lowPowerDevice, prefersReducedMotion, webglAvailable } from './webgl.js'
import { chromOfVariant, dnaMarkersFor, highlightFor, variantById } from './selection.js'

// three.js is only downloaded when the 3D stage is actually shown.
const Stage3D = lazy(() => import('./Stage3D.jsx'))

class StageBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { failed: false }
  }
  static getDerivedStateFromError() {
    return { failed: true }
  }
  componentDidCatch(err) {
    console.warn('3D stage failed, using 2D schematic:', err?.message)
    this.props.onFail?.()
  }
  render() {
    return this.state.failed ? this.props.fallback : this.props.children
  }
}

export const MODES = [
  { id: 'anatomy', label: 'Anatomy' },
  { id: 'genome', label: 'Genome' },
  { id: 'dna', label: 'DNA' },
  { id: 'systems', label: 'Systems' },
  { id: 'timeline', label: 'Timeline' },
]

export default function TwinStage({
  twin, mode, goal, selection, selectedChrom, onSelectSystem, onSelectVariant, onSelectChrom, forceFallback = false,
}) {
  const box = useRef(null)
  const [fs, setFs] = useState(false)
  const [rung, setRung] = useState(null)
  const [broken, setBroken] = useState(false)
  const [spin, setSpin] = useState(true)
  const gl = useMemo(() => !forceFallback && webglAvailable(), [forceFallback])
  const low = useMemo(() => lowPowerDevice(), [])
  const reduced = useMemo(() => prefersReducedMotion(), [])
  const use3d = gl && !broken
  // a camera preset (Front/Back/...) takes over from the turntable
  useEffect(() => { if (goal && goal.key) setSpin(false) }, [goal])

  useEffect(() => {
    const h = () => setFs(document.fullscreenElement === box.current)
    document.addEventListener('fullscreenchange', h)
    return () => document.removeEventListener('fullscreenchange', h)
  }, [])
  const toggleFs = () => {
    if (!box.current) return
    if (document.fullscreenElement) document.exitFullscreen?.()
    else box.current.requestFullscreen?.()
  }

  const hl = useMemo(() => highlightFor(twin, selection), [twin, selection])
  const caseSystems = hl.caseSystems
  const markers = useMemo(() => dnaMarkersFor(twin, selection), [twin, selection])
  const selVariant = selection?.kind === 'variant' ? variantById(twin, selection.id) : null
  const selGene = selVariant?.gene_symbol || (selection?.kind === 'gene' ? selection.id : null)

  const bodyFallback = (
    <BodyFallback2D
      selectedSystem={hl.selectedSystem} linkedSystems={hl.linkedSystems} caseSystems={caseSystems}
      onSelectSystem={onSelectSystem}
      notice={use3d ? null : 'WebGL is unavailable, so a 2D anatomical schematic is shown. All data remains available in the panels.'}
    />
  )
  const dnaFallback = <DnaFallback2D marker={markers[0]} />

  const dark = mode !== 'genome' && mode !== 'timeline'
  let content
  if (mode === 'genome') {
    content = (
      <GenomeView
        chromosomes={twin.anatomy.chromosomes}
        selectedVariantId={selection?.kind === 'variant' ? selection.id : null}
        selectedChrom={selectedChrom || (selection?.kind === 'variant' ? chromOfVariant(twin, selection.id) : null)}
        onSelectVariant={onSelectVariant} onSelectChrom={onSelectChrom}
      />
    )
  } else if (mode === 'timeline') {
    content = <TwinTimeline timeline={twin.timeline} large />
  } else if (!use3d) {
    content = mode === 'dna' ? dnaFallback : bodyFallback
  } else {
    content = (
      <StageBoundary fallback={mode === 'dna' ? dnaFallback : bodyFallback} onFail={() => setBroken(true)}>
        <Suspense fallback={<div className="w-full h-full flex items-center justify-center text-xs text-outline">Loading 3D stage…</div>}>
          <Stage3D
            mode={mode === 'dna' ? 'dna' : 'anatomy'} goal={goal}
            selectedSystem={hl.selectedSystem} linkedSystems={hl.linkedSystems} caseSystems={caseSystems}
            onSelectSystem={onSelectSystem} dnaMarkers={markers} onSelectVariant={onSelectVariant}
            onHoverRung={setRung} low={low} reduced={reduced}
            autoRotate={spin} onUserInteract={() => setSpin(false)}
            systemsData={twin.anatomy.systems} showCallouts={mode === 'systems'}
            genomeLabel={selGene ? `${selGene}${selVariant ? ` · ${selVariant.cdna || selVariant.hgvs} · ${selVariant.acmg_classification}` : ''}` : null}
          />
        </Suspense>
      </StageBoundary>
    )
  }

  return (
    <div
      ref={box} data-testid="twin-stage" data-mode={mode} data-renderer={use3d ? 'webgl' : 'fallback-2d'}
      className={`relative w-full h-full min-h-[420px] rounded-2xl overflow-hidden border ${dark ? 'border-[#1d3a5f] text-[#dff4ff]' : 'border-outline-variant/40'}`}
      style={{ background: dark ? 'radial-gradient(ellipse at 50% 35%, #0d2747 0%, #06142a 55%, #030914 100%)' : 'linear-gradient(#f6fafe, #e6f0f9)' }}
    >
      {dark && (
        <div className="absolute inset-0 opacity-[0.18] pointer-events-none"
          style={{ backgroundImage: 'linear-gradient(#2a5d8f 1px, transparent 1px), linear-gradient(90deg, #2a5d8f 1px, transparent 1px)', backgroundSize: '40px 40px' }} />
      )}
      <div className="absolute inset-0">{content}</div>

      <div className="absolute top-3 left-3 right-28 pointer-events-none space-y-1">
        <div className="text-[10px] font-mono tracking-[0.2em] uppercase" style={{ color: dark ? '#6fc6ff' : '#00629e' }}>
          Genomera Twin · {twin.identity.patient_id} · {twin.snapshot.snapshot_version}
        </div>
        <span className={`inline-block px-2.5 py-1 rounded-full backdrop-blur border text-[10px] font-semibold ${dark ? 'bg-[#071426]/70 border-[#2a5d8f] text-[#a9d8f5]' : 'bg-white/80 border-outline-variant/50 text-on-surface-variant'}`}>
          Computational Digital Twin — derived from available clinical and genomic data, not a scan
        </span>
      </div>
      <div className="absolute top-3 right-3 flex gap-1.5">
        {use3d && (mode === 'anatomy' || mode === 'systems') && (
          <button onClick={() => setSpin((v) => !v)} aria-pressed={spin} aria-label={spin ? 'Pause rotation' : 'Start rotation'} data-testid="auto-rotate"
            className="p-1.5 rounded-lg backdrop-blur border bg-[#071426]/70 border-[#2a5d8f] text-[#bfe6ff] hover:bg-[#0d2747]">
            {spin ? <Pause size={15} /> : <Play size={15} />}
          </button>
        )}
        <button
          onClick={toggleFs} aria-label={fs ? 'Exit full screen' : 'Enter full screen'} data-testid="fullscreen"
          className={`p-1.5 rounded-lg backdrop-blur border ${dark ? 'bg-[#071426]/70 border-[#2a5d8f] text-[#bfe6ff] hover:bg-[#0d2747]' : 'bg-white/85 border-outline-variant/50 text-on-surface hover:bg-white'}`}
        >
          {fs ? <Minimize2 size={15} /> : <Maximize2 size={15} />}
        </button>
      </div>
      {(mode === 'anatomy' || mode === 'systems') && (
        <div className="absolute right-3 bottom-3 rounded-lg px-2.5 py-2 text-[10px] space-y-1 backdrop-blur border border-[#2a5d8f] bg-[#071426]/70 text-[#bfe6ff]" data-testid="stage-legend">
          {[['#6f86a8', 'No case data (reference)'], ['#3aa8ff', 'Case data mapped'], ['#4fe3ff', 'Linked to selection'], ['#33f5c4', 'Selected']].map(([c, t]) => (
            <div key={t} className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full" style={{ background: c, boxShadow: `0 0 6px ${c}` }} />{t}</div>
          ))}
        </div>
      )}

      {mode === 'dna' && (
        <div className="absolute left-3 bottom-3 max-w-[280px] rounded-xl backdrop-blur border p-3 text-xs bg-[#071426]/80 border-[#2a5d8f] text-[#dff4ff]" data-testid="dna-info">
          <div className="font-bold mb-1 tracking-wide" style={{ color: '#6fc6ff' }}>DNA Helix</div>
          <div>Selected gene: <b>{selGene || 'none'}</b></div>
          <div>Selected variant: <b>{selVariant ? (selVariant.cdna || selVariant.hgvs) : 'none'}</b></div>
          <div>Classification: <b>{selVariant ? selVariant.acmg_classification : '-'}</b></div>
          {rung && <div className="mt-1" style={{ color: '#8fc9ee' }}>Base pair {rung.index}: {rung.bases}{rung.marker ? ` · variant ${rung.marker.gene}` : ' (illustrative)'}</div>}
          <div className="mt-1 text-[10px] leading-snug" style={{ color: '#8fb3cf' }}>
            {markers.length
              ? 'Helix is a conceptual segment; the marker sits at the variant position as a fraction of its chromosome and shows the VCF reference base.'
              : 'Global DNA illustration. Select a variant to mark it; no patient variants are invented.'}
          </div>
        </div>
      )}
      {(mode === 'anatomy' || mode === 'systems') && use3d && (
        <div className="absolute left-3 bottom-3 text-[10px] rounded px-2 py-1 pointer-events-none bg-[#071426]/60 text-[#8fc9ee]">
          Drag to rotate · scroll to zoom · right-drag to pan · click an organ system
        </div>
      )}
    </div>
  )
}
