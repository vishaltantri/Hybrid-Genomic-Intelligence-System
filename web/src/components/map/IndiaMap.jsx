import React, { useState, useMemo, useRef, useEffect } from 'react'
import { INDIA_LOCATIONS } from './indiaSvgPaths.js'
import {
  STATE_CENTROIDS,
  REGIONAL_ZONES,
  MAP_METRICS,
  normalizeStateName,
  getChoroplethColor,
} from './indiaMapData.js'
import {
  ZoomIn,
  ZoomOut,
  RotateCcw,
  Layers,
  MapPin,
  Crosshair,
  Info,
  ChevronRight,
  Maximize2,
  Minimize2,
  RefreshCw,
} from 'lucide-react'

export default function IndiaMap({
  statesData = [],
  selectedState = null,
  onSelectState,
  activeMetric = 'cases',
  onMetricChange,
  showMarkers = true,
  onToggleMarkers,
  showClusters = false,
  onToggleClusters,
  isLoading = false,
}) {
  const [hoveredLocation, setHoveredLocation] = useState(null)
  const [tooltipPos, setTooltipPos] = useState({ x: 0, y: 0 })
  const [zoomLevel, setZoomLevel] = useState(1)
  const [panOffset, setPanOffset] = useState({ x: 0, y: 0 })
  const [isFullscreen, setIsFullscreen] = useState(false)
  const mapContainerRef = useRef(null)

  const metricDef = MAP_METRICS[activeMetric] || MAP_METRICS.cases

  // Build lookup index: normalized state name -> state data object
  const stateDataMap = useMemo(() => {
    const map = new Map()
    for (const s of statesData) {
      if (s?.state) {
        map.set(normalizeStateName(s.state), s)
      }
    }
    return map
  }, [statesData])

  // Calculate min and max for active metric
  const { minVal, maxVal, topHotspots } = useMemo(() => {
    let min = Infinity
    let max = -Infinity
    const values = []

    for (const s of statesData) {
      const val = metricDef.getValue(s)
      if (val != null && !isNaN(val)) {
        values.push({ state: s.state, val })
        if (val < min) min = val
        if (val > max) max = val
      }
    }

    values.sort((a, b) => b.val - a.val)
    const hotspots = new Set(values.slice(0, 3).map((v) => normalizeStateName(v.state)))

    return {
      minVal: min === Infinity ? 0 : min,
      maxVal: max === -Infinity ? 100 : max,
      topHotspots: hotspots,
    }
  }, [statesData, metricDef])

  // Calculate dynamic SVG viewBox based on zoom and pan
  const currentViewBox = useMemo(() => {
    const baseW = 612
    const baseH = 696
    const curW = baseW / zoomLevel
    const curH = baseH / zoomLevel
    const curX = (baseW - curW) / 2 + panOffset.x
    const curY = (baseH - curH) / 2 + panOffset.y
    return `${curX} ${curY} ${curW} ${curH}`
  }, [zoomLevel, panOffset])

  // Center and zoom in on selected state when focused
  useEffect(() => {
    if (selectedState) {
      const norm = normalizeStateName(selectedState.state || selectedState.name)
      const loc = INDIA_LOCATIONS.find((l) => normalizeStateName(l.name) === norm)
      if (loc) {
        const centroid = STATE_CENTROIDS[loc.id]
        if (centroid) {
          const baseW = 612
          const baseH = 696
          const targetX = centroid.x - baseW / 2
          const targetY = centroid.y - baseH / 2
          setZoomLevel(1.8)
          setPanOffset({
            x: Math.max(-120, Math.min(120, targetX * 0.7)),
            y: Math.max(-120, Math.min(120, targetY * 0.7)),
          })
        }
      }
    } else {
      setZoomLevel(1)
      setPanOffset({ x: 0, y: 0 })
    }
  }, [selectedState])

  const handleZoom = (delta) => {
    setZoomLevel((prev) => {
      const next = Math.max(1, Math.min(3, prev + delta))
      if (next === 1) setPanOffset({ x: 0, y: 0 })
      return next
    })
  }

  const handleReset = () => {
    setZoomLevel(1)
    setPanOffset({ x: 0, y: 0 })
  }

  const handleMouseMove = (e) => {
    if (mapContainerRef.current) {
      const rect = mapContainerRef.current.getBoundingClientRect()
      setTooltipPos({
        x: e.clientX - rect.left,
        y: e.clientY - rect.top,
      })
    }
  }

  const selectedNorm = selectedState
    ? normalizeStateName(selectedState.state || selectedState.name)
    : ''

  return (
    <div
      ref={mapContainerRef}
      onMouseMove={handleMouseMove}
      className={`relative rounded-2xl bg-gradient-to-b from-white to-surface-container-lowest border border-outline-variant/40 shadow-xs overflow-hidden flex flex-col ${
        isFullscreen
          ? 'fixed inset-4 z-50 bg-white shadow-2xl'
          : 'w-full min-h-[580px] lg:min-h-[640px]'
      }`}
    >
      {/* Top Toolbar: Mode Switcher & Controls */}
      <div className="p-3 border-b border-outline-variant/30 flex flex-wrap items-center justify-between gap-2.5 bg-white/95 backdrop-blur-xs z-10">
        {/* Metric Selector Tabs */}
        <div className="flex flex-wrap items-center gap-1 p-1 rounded-xl bg-surface-container-low border border-outline-variant/40">
          {Object.values(MAP_METRICS).map((m) => {
            const active = activeMetric === m.id
            return (
              <button
                key={m.id}
                onClick={() => onMetricChange(m.id)}
                className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                  active
                    ? 'bg-white text-primary shadow-xs border border-primary/20'
                    : 'text-on-surface-variant hover:text-on-surface hover:bg-white/50'
                }`}
                title={m.description}
              >
                <span>{m.label}</span>
              </button>
            )
          })}
        </div>

        {/* Feature Toggles & Zoom Controls */}
        <div className="flex items-center gap-2">
          {isLoading && (
            <div className="flex items-center gap-1.5 px-2 py-1 rounded bg-primary-container/20 text-primary text-[11px] font-mono animate-pulse">
              <RefreshCw size={12} className="animate-spin" />
              <span>Updating Map...</span>
            </div>
          )}

          {/* Hotspot Markers Toggle */}
          <button
            onClick={onToggleMarkers}
            className={`px-2.5 py-1.5 rounded-lg text-xs font-medium border flex items-center gap-1.5 transition-colors ${
              showMarkers
                ? 'bg-secondary-container/20 text-secondary border-secondary/30'
                : 'bg-surface-container-low text-on-surface-variant border-outline-variant/40'
            }`}
            title="Toggle geographic hotspot indicators"
          >
            <MapPin size={13} />
            <span className="hidden sm:inline">Activity Points</span>
          </button>

          {/* Regional Clusters Toggle */}
          <button
            onClick={onToggleClusters}
            className={`px-2.5 py-1.5 rounded-lg text-xs font-medium border flex items-center gap-1.5 transition-colors ${
              showClusters
                ? 'bg-primary-container/20 text-primary border-primary/30'
                : 'bg-surface-container-low text-on-surface-variant border-outline-variant/40'
            }`}
            title="Group into Regional Surveillance Clusters"
          >
            <Layers size={13} />
            <span className="hidden sm:inline">Clusters</span>
          </button>

          {/* Zoom Buttons */}
          <div className="flex items-center rounded-lg bg-surface-container-low border border-outline-variant/40 overflow-hidden">
            <button
              onClick={() => handleZoom(0.5)}
              className="p-1.5 hover:bg-surface-container text-on-surface-variant"
              title="Zoom In"
              aria-label="Zoom In"
            >
              <ZoomIn size={15} />
            </button>
            <button
              onClick={() => handleZoom(-0.5)}
              disabled={zoomLevel <= 1}
              className="p-1.5 hover:bg-surface-container text-on-surface-variant disabled:opacity-40"
              title="Zoom Out"
              aria-label="Zoom Out"
            >
              <ZoomOut size={15} />
            </button>
            <button
              onClick={handleReset}
              className="p-1.5 hover:bg-surface-container text-on-surface-variant border-l border-outline-variant/30"
              title="Reset View"
              aria-label="Reset View"
            >
              <RotateCcw size={13} />
            </button>
          </div>

          {/* Fullscreen Toggle */}
          <button
            onClick={() => setIsFullscreen(!isFullscreen)}
            className="p-1.5 rounded-lg bg-surface-container-low border border-outline-variant/40 text-on-surface-variant hover:text-on-surface"
            title={isFullscreen ? 'Exit Fullscreen' : 'Expand Fullscreen'}
          >
            {isFullscreen ? <Minimize2 size={15} /> : <Maximize2 size={15} />}
          </button>
        </div>
      </div>

      {/* Main Map Viewport with Guaranteed Non-Zero Dimensions */}
      <div className="flex-1 w-full min-h-[460px] lg:min-h-[520px] relative flex items-center justify-center p-3 select-none overflow-hidden">
        <svg
          viewBox={currentViewBox}
          style={{
            width: '100%',
            height: '100%',
            minHeight: '440px',
            maxHeight: '560px',
            aspectRatio: '612 / 696',
            cursor: zoomLevel > 1 ? 'grab' : 'default',
          }}
          className="transition-all duration-300"
        >
          {/* Defs for gradients & filters */}
          <defs>
            <filter id="map-glow" x="-20%" y="-20%" width="140%" height="140%">
              <feDropShadow dx="0" dy="2" stdDeviation="3" floodColor="#00629E" floodOpacity="0.4" />
            </filter>
            <filter id="marker-shadow" x="-50%" y="-50%" width="200%" height="200%">
              <feDropShadow dx="0" dy="1" stdDeviation="1.5" floodColor="#001C37" floodOpacity="0.3" />
            </filter>
          </defs>

          {/* Indian States / UTs SVG Paths */}
          <g id="states-group">
            {INDIA_LOCATIONS.map((loc) => {
              const normName = normalizeStateName(loc.name)
              const stateData = stateDataMap.get(normName)
              const val = stateData ? metricDef.getValue(stateData) : null
              const isSelected = selectedNorm === normName
              const isHovered = hoveredLocation?.id === loc.id

              const fillColor = getChoroplethColor(
                val,
                minVal,
                maxVal,
                metricDef.scale
              )

              return (
                <path
                  key={loc.id}
                  id={loc.id}
                  d={loc.path}
                  fill={fillColor}
                  stroke={isSelected ? '#001C37' : isHovered ? '#00629E' : '#94a3b8'}
                  strokeWidth={isSelected ? '2.5' : isHovered ? '2' : '0.9'}
                  strokeLinejoin="round"
                  filter={isSelected ? 'url(#map-glow)' : undefined}
                  className="transition-all duration-150 cursor-pointer"
                  onMouseEnter={() =>
                    setHoveredLocation({
                      id: loc.id,
                      name: loc.name,
                      data: stateData,
                    })
                  }
                  onMouseLeave={() => setHoveredLocation(null)}
                  onClick={() => {
                    if (onSelectState) {
                      onSelectState(
                        stateData || {
                          state: loc.name,
                          cases: null,
                          confirmed: null,
                          access_gap_score: null,
                          consanguinity_rate: null,
                          is_unavailable: true,
                        }
                      )
                    }
                  }}
                  role="button"
                  aria-label={`${loc.name} ${val != null ? `${metricDef.label}: ${metricDef.format(val)}` : 'Data Unavailable'}`}
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault()
                      if (onSelectState) {
                        onSelectState(stateData || { state: loc.name, is_unavailable: true })
                      }
                    }
                  }}
                />
              )
            })}
          </g>

          {/* Activity Hotspot Markers Layer */}
          {showMarkers && !showClusters && (
            <g id="markers-group" pointerEvents="none">
              {INDIA_LOCATIONS.map((loc) => {
                const normName = normalizeStateName(loc.name)
                const stateData = stateDataMap.get(normName)
                if (!stateData) return null

                const centroid = STATE_CENTROIDS[loc.id]
                if (!centroid) return null

                const val = metricDef.getValue(stateData)
                if (val == null) return null

                const isHotspot = topHotspots.has(normName)
                const isSelected = selectedNorm === normName

                const r = Math.max(
                  4,
                  Math.min(13, 4 + ((val - minVal) / Math.max(1, maxVal - minVal)) * 9)
                )

                return (
                  <g key={`marker-${loc.id}`}>
                    {/* Animated Pulsing Ring for Top Hotspots */}
                    {isHotspot && (
                      <circle
                        cx={centroid.x}
                        cy={centroid.y}
                        r={r + 6}
                        fill="none"
                        stroke="#0284C7"
                        strokeWidth="1.5"
                        opacity="0.6"
                        className="animate-ping"
                      />
                    )}
                    {/* Centroid Data Marker */}
                    <circle
                      cx={centroid.x}
                      cy={centroid.y}
                      r={r}
                      fill={isSelected ? '#001C37' : '#0284C7'}
                      stroke="#FFFFFF"
                      strokeWidth="1.8"
                      filter="url(#marker-shadow)"
                      opacity="0.9"
                    />
                    <circle
                      cx={centroid.x}
                      cy={centroid.y}
                      r="1.8"
                      fill="#FFFFFF"
                    />
                  </g>
                )
              })}
            </g>
          )}

          {/* Regional Clusters Layer */}
          {showClusters && (
            <g id="clusters-group">
              {Object.entries(REGIONAL_ZONES).map(([zoneName, zone]) => {
                let totalZoneCases = 0
                let reportingCount = 0

                zone.states.forEach((stateId) => {
                  const loc = INDIA_LOCATIONS.find((l) => l.id === stateId)
                  if (loc) {
                    const norm = normalizeStateName(loc.name)
                    const data = stateDataMap.get(norm)
                    if (data && typeof data.cases === 'number') {
                      totalZoneCases += data.cases
                      reportingCount++
                    }
                  }
                })

                if (reportingCount === 0) return null

                return (
                  <g
                    key={`cluster-${zoneName}`}
                    className="cursor-pointer transition-transform hover:scale-110"
                    onClick={() => {
                      setZoomLevel(1.8)
                      setPanOffset({
                        x: (zone.x - 306) * 0.7,
                        y: (zone.y - 348) * 0.7,
                      })
                    }}
                  >
                    <circle
                      cx={zone.x}
                      cy={zone.y}
                      r="20"
                      fill="#004A7C"
                      opacity="0.85"
                      stroke="#FFFFFF"
                      strokeWidth="2.5"
                      filter="url(#marker-shadow)"
                    />
                    <text
                      x={zone.x}
                      y={zone.y - 2}
                      textAnchor="middle"
                      fill="#FFFFFF"
                      fontSize="9"
                      fontWeight="bold"
                      fontFamily="sans-serif"
                    >
                      {totalZoneCases}
                    </text>
                    <text
                      x={zone.x}
                      y={zone.y + 8}
                      textAnchor="middle"
                      fill="#BAE6FD"
                      fontSize="6.5"
                      fontFamily="monospace"
                    >
                      {reportingCount} states
                    </text>
                  </g>
                )
              })}
            </g>
          )}
        </svg>

        {/* Dynamic Floating Tooltip */}
        {hoveredLocation && (
          <div
            className="absolute pointer-events-none z-30 transition-all duration-75 ease-out shadow-lg rounded-xl bg-white/95 backdrop-blur-md border border-outline-variant/50 p-3 w-60 text-xs"
            style={{
              left: Math.min(
                (mapContainerRef.current?.clientWidth || 500) - 260,
                Math.max(12, tooltipPos.x + 16)
              ),
              top: Math.min(
                (mapContainerRef.current?.clientHeight || 500) - 180,
                Math.max(12, tooltipPos.y - 20)
              ),
            }}
          >
            <div className="flex items-center justify-between pb-1.5 border-b border-outline-variant/30">
              <span className="font-bold text-sm text-on-surface truncate">
                {hoveredLocation.name}
              </span>
              <span className="text-[10px] font-mono text-outline uppercase">
                {hoveredLocation.data ? 'REPORTING' : 'NO RECORD'}
              </span>
            </div>

            {hoveredLocation.data ? (
              <div className="space-y-1.5 pt-2">
                <div className="flex items-center justify-between">
                  <span className="text-outline text-[11px]">Estimated Cases:</span>
                  <span className="font-mono font-bold text-primary">
                    {hoveredLocation.data.cases != null
                      ? hoveredLocation.data.cases.toLocaleString('en-IN')
                      : 'Unavailable'}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-outline text-[11px]">Confirmed:</span>
                  <span className="font-mono text-on-surface">
                    {hoveredLocation.data.confirmed != null
                      ? hoveredLocation.data.confirmed.toLocaleString('en-IN')
                      : 'Unavailable'}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-outline text-[11px]">Access Deficit:</span>
                  <span className="font-mono font-semibold text-secondary">
                    {hoveredLocation.data.access_gap_score != null
                      ? `${hoveredLocation.data.access_gap_score}:1 (${hoveredLocation.data.gap_label || 'ok'})`
                      : 'Unavailable'}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-outline text-[11px]">Consanguinity:</span>
                  <span className="font-mono text-on-surface">
                    {hoveredLocation.data.consanguinity_rate != null
                      ? `${hoveredLocation.data.consanguinity_rate}%`
                      : 'Unavailable'}
                  </span>
                </div>
                <div className="text-[9.5px] text-outline italic pt-1 border-t border-outline-variant/20">
                  Model-derived surveillance synthesis
                </div>
              </div>
            ) : (
              <div className="pt-2 text-outline text-[11px] italic">
                No surveillance submission recorded for this state in the current reporting cycle.
              </div>
            )}
          </div>
        )}
      </div>

      {/* Dynamic Map Legend Bar */}
      <div className="p-3 bg-white/90 border-t border-outline-variant/30 flex flex-wrap items-center justify-between gap-3 text-xs">
        <div className="flex items-center gap-2">
          <span className="font-bold text-on-surface">{metricDef.label}</span>
          <span className="text-outline text-[11px]">({metricDef.unit})</span>
        </div>

        <div className="flex items-center gap-2">
          <span className="font-mono text-[10px] text-outline font-semibold">
            {metricDef.format(minVal)}
          </span>
          <div className="flex h-3 w-32 sm:w-44 rounded-sm overflow-hidden border border-outline-variant/40">
            {metricDef.scale.map((color, idx) => (
              <div
                key={idx}
                className="flex-1 h-full"
                style={{ backgroundColor: color }}
              />
            ))}
          </div>
          <span className="font-mono text-[10px] text-outline font-semibold">
            {metricDef.format(maxVal)}
          </span>
        </div>

        <div className="flex items-center gap-1.5 text-[11px] text-outline">
          <div className="w-3.5 h-3 rounded-xs bg-[#f1f5f9] border border-[#cbd5e1]" />
          <span>Unavailable / Unreported</span>
        </div>
      </div>
    </div>
  )
}
