import React, { useEffect, useState, useMemo, useRef } from 'react'
import { api } from '../api.js'
import {
  Map,
  Building2,
  TrendingUp,
  AlertTriangle,
  FileText,
  Search,
  CheckCircle2,
  Info,
  Code2,
  Layers,
  Activity,
  ArrowUpRight,
  Calendar,
  Sparkles,
  ChevronDown,
  ChevronUp,
  ShieldCheck,
  Percent,
  Crosshair,
  MapPin,
  RefreshCw,
} from 'lucide-react'
import { PageHeader } from '../components/ui/PageHeader.jsx'
import { ClinicalCard } from '../components/ui/ClinicalCard.jsx'
import { StatCard } from '../components/ui/StatCard.jsx'
import { ScoreBar } from '../components/ui/ScoreBar.jsx'
import { StatusBadge, SeverityBadge } from '../components/ui/StatusBadge.jsx'
import { ErrorAlert } from '../components/ui/ErrorAlert.jsx'
import IndiaMap from '../components/map/IndiaMap.jsx'
import StateDetailPanel from '../components/map/StateDetailPanel.jsx'
import { normalizeStateName } from '../components/map/indiaMapData.js'

const AVAILABLE_MONTHS = ['2026-01', '2026-02']

// Baseline Seed Surveillance Data (matches data/seeds/simulated_national_records.csv)
const BASELINE_NATIONAL_DATA = {
  month: '2026-01',
  totals: {
    cases: 1702,
    confirmed: 1203,
    red_flagged: 245,
    states_reporting: 18,
  },
  states: [
    { state: 'Maharashtra', cases: 233, asha_reports: 330, confirmed: 203, red_flagged: 29, by_disease: { 'ORPHA:231222': 145, 'ORPHA:232': 88 }, labs: 0, specialists: 1, access_gap_score: 233.0, gap_label: 'critical', consanguinity_rate: 9.0 },
    { state: 'Uttar Pradesh', cases: 202, asha_reports: 300, confirmed: 129, red_flagged: 31, by_disease: { 'ORPHA:231222': 160, 'ORPHA:98863': 42 }, labs: 0, specialists: 2, access_gap_score: 101.0, gap_label: 'critical', consanguinity_rate: 3.0 },
    { state: 'Tamil Nadu', cases: 154, asha_reports: 248, confirmed: 136, red_flagged: 22, by_disease: { 'ORPHA:231222': 120, 'ORPHA:915': 34 }, labs: 1, specialists: 3, access_gap_score: 38.5, gap_label: 'high', consanguinity_rate: 28.0 },
    { state: 'Andhra Pradesh', cases: 136, asha_reports: 206, confirmed: 105, red_flagged: 20, by_disease: { 'ORPHA:915': 41, 'ORPHA:231222': 95 }, labs: 0, specialists: 1, access_gap_score: 136.0, gap_label: 'critical', consanguinity_rate: 26.0 },
    { state: 'Bihar', cases: 130, asha_reports: 200, confirmed: 72, red_flagged: 20, by_disease: { 'ORPHA:231222': 130 }, labs: 0, specialists: 1, access_gap_score: 130.0, gap_label: 'critical', consanguinity_rate: 2.8 },
    { state: 'Chhattisgarh', cases: 110, asha_reports: 170, confirmed: 66, red_flagged: 19, by_disease: { 'ORPHA:232': 110 }, labs: 0, specialists: 1, access_gap_score: 110.0, gap_label: 'critical', consanguinity_rate: 6.0 },
    { state: 'Madhya Pradesh', cases: 98, asha_reports: 150, confirmed: 59, red_flagged: 17, by_disease: { 'ORPHA:232': 98 }, labs: 0, specialists: 1, access_gap_score: 98.0, gap_label: 'critical', consanguinity_rate: 4.5 },
    { state: 'West Bengal', cases: 88, asha_reports: 130, confirmed: 60, red_flagged: 10, by_disease: { 'ORPHA:231222': 88 }, labs: 1, specialists: 2, access_gap_score: 29.33, gap_label: 'high', consanguinity_rate: 3.5 },
    { state: 'Karnataka', cases: 84, asha_reports: 120, confirmed: 61, red_flagged: 9, by_disease: { 'ORPHA:231222': 84 }, labs: 1, specialists: 2, access_gap_score: 28.0, gap_label: 'high', consanguinity_rate: 27.0 },
    { state: 'Odisha', cases: 76, asha_reports: 110, confirmed: 48, red_flagged: 13, by_disease: { 'ORPHA:232': 76 }, labs: 0, specialists: 1, access_gap_score: 76.0, gap_label: 'critical', consanguinity_rate: 7.0 },
    { state: 'Gujarat', cases: 72, asha_reports: 105, confirmed: 55, red_flagged: 8, by_disease: { 'ORPHA:231222': 72 }, labs: 0, specialists: 2, access_gap_score: 36.0, gap_label: 'high', consanguinity_rate: 5.5 },
    { state: 'Rajasthan', cases: 70, asha_reports: 100, confirmed: 44, red_flagged: 9, by_disease: { 'ORPHA:231222': 70 }, labs: 0, specialists: 1, access_gap_score: 70.0, gap_label: 'critical', consanguinity_rate: 4.0 },
    { state: 'Jharkhand', cases: 54, asha_reports: 80, confirmed: 31, red_flagged: 9, by_disease: { 'ORPHA:232': 54 }, labs: 0, specialists: 1, access_gap_score: 54.0, gap_label: 'critical', consanguinity_rate: 2.5 },
    { state: 'Punjab', cases: 52, asha_reports: 75, confirmed: 36, red_flagged: 7, by_disease: { 'ORPHA:231222': 52 }, labs: 0, specialists: 1, access_gap_score: 52.0, gap_label: 'critical', consanguinity_rate: 2.0 },
    { state: 'Assam', cases: 46, asha_reports: 70, confirmed: 26, red_flagged: 6, by_disease: { 'ORPHA:231222': 46 }, labs: 0, specialists: 1, access_gap_score: 46.0, gap_label: 'critical', consanguinity_rate: 1.3 },
    { state: 'Kerala', cases: 40, asha_reports: 60, confirmed: 31, red_flagged: 4, by_disease: { 'ORPHA:231222': 40 }, labs: 0, specialists: 1, access_gap_score: 40.0, gap_label: 'high', consanguinity_rate: 5.0 },
    { state: 'Telangana', cases: 29, asha_reports: 48, confirmed: 22, red_flagged: 6, by_disease: { 'ORPHA:915': 29 }, labs: 0, specialists: 2, access_gap_score: 14.5, gap_label: 'ok', consanguinity_rate: 18.0 },
    { state: 'Delhi', cases: 28, asha_reports: 40, confirmed: 19, red_flagged: 6, by_disease: { 'ORPHA:98863': 28 }, labs: 0, specialists: 3, access_gap_score: 9.33, gap_label: 'ok', consanguinity_rate: 1.8 },
  ],
}

export default function NationalView() {
  const [selectedMonth, setSelectedMonth] = useState('2026-01')
  const [nat, setNat] = useState(BASELINE_NATIONAL_DATA)
  const [brief, setBrief] = useState(null)
  const [err, setErr] = useState(null)
  const [loading, setLoading] = useState(false)
  const [tableSearch, setTableSearch] = useState('')
  const [selectedState, setSelectedState] = useState(null)
  const [activeMetric, setActiveMetric] = useState('cases')
  const [showMarkers, setShowMarkers] = useState(true)
  const [showClusters, setShowClusters] = useState(false)
  const [showMethodology, setShowMethodology] = useState(false)
  const [showRawJson, setShowRawJson] = useState(false)

  const mapSectionRef = useRef(null)
  const tableRef = useRef(null)

  // Fetch live updates from API without blocking baseline display
  useEffect(() => {
    let isMounted = true
    setLoading(true)

    const fetchLive = async () => {
      try {
        const liveNat = await api.national(selectedMonth)
        if (isMounted && liveNat?.states) {
          setNat(liveNat)
          setErr(null)
        }
      } catch (ex) {
        // The map still renders from the bundled snapshot of the same simulated dataset, but the user is told so.
        if (isMounted) setErr(`Live national data could not be loaded (${ex.message}). Showing the bundled snapshot of the simulated dataset for ${BASELINE_NATIONAL_DATA.month}, not the selected cycle.`)
      } finally {
        if (isMounted) setLoading(false)
      }
    }

    const fetchBrief = async () => {
      try {
        const b = await api.policyBrief()
        if (isMounted) setBrief(b)
      } catch {
        /* brief optional */
      }
    }

    fetchLive()
    fetchBrief()

    return () => {
      isMounted = false
    }
  }, [selectedMonth])

  const rawStates = useMemo(() => nat?.states || nat?.rows || [], [nat])

  // Filtered states for surveillance table
  const filteredStates = useMemo(() => {
    if (!tableSearch) return rawStates
    const q = tableSearch.toLowerCase()
    return rawStates.filter((s) => (s.state || s.name || '').toLowerCase().includes(q))
  }, [rawStates, tableSearch])

  // Dynamic National Insights calculated strictly from actual data
  const insights = useMemo(() => {
    if (!rawStates.length) return null

    let highestBurdenState = rawStates[0]
    let largestGapState = rawStates[0]
    let highestConsanguinityState = rawStates[0]
    const diseaseFrequency = {}

    for (const s of rawStates) {
      if ((s.cases || 0) > (highestBurdenState.cases || 0)) highestBurdenState = s
      if ((s.access_gap_score || 0) > (largestGapState.access_gap_score || 0)) largestGapState = s
      if ((s.consanguinity_rate || 0) > (highestConsanguinityState.consanguinity_rate || 0))
        highestConsanguinityState = s

      if (s.by_disease) {
        for (const [d, count] of Object.entries(s.by_disease)) {
          diseaseFrequency[d] = (diseaseFrequency[d] || 0) + count
        }
      }
    }

    const topDisease = Object.entries(diseaseFrequency).sort((a, b) => b[1] - a[1])[0]

    return {
      highestBurdenState,
      largestGapState,
      highestConsanguinityState,
      topDisease: topDisease ? { id: topDisease[0], count: topDisease[1] } : null,
    }
  }, [rawStates])

  const handleSelectState = (stateObj) => {
    setSelectedState(stateObj)
  }

  const handleFocusState = (stateObj) => {
    setSelectedState(stateObj)
    if (mapSectionRef.current) {
      mapSectionRef.current.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
  }

  const handleViewInTable = (stateName) => {
    setTableSearch(stateName)
    if (tableRef.current) {
      tableRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <PageHeader
        title="National Rare Disease Intelligence & Surveillance"
        subtitle="Geographic epidemiological burden tracking, diagnostic access deficits, and policy synthesis across Indian states."
        badge={{
          label: 'Epidemiological Surveillance Engine',
          color: 'secondary',
          icon: Map,
        }}
        actions={
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold text-outline hidden sm:inline">Surveillance Cycle:</span>
            <div className="relative">
              <select aria-label="Surveillance Cycle"
                value={selectedMonth}
                onChange={(e) => setSelectedMonth(e.target.value)}
                className="h-9 px-3 pr-8 rounded-lg bg-surface-container border border-outline-variant/50 text-xs font-bold text-primary focus:outline-none focus:border-primary appearance-none cursor-pointer"
              >
                {AVAILABLE_MONTHS.map((m) => (
                  <option key={m} value={m}>
                    Cycle: {m}
                  </option>
                ))}
              </select>
              <Calendar
                size={14}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-outline pointer-events-none"
              />
            </div>
          </div>
        }
      />

      {/* Prominent National KPI Header */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard
          title="Estimated Cases"
          value={
            nat.totals?.cases != null
              ? nat.totals.cases.toLocaleString('en-IN')
              : '1,702'
          }
          subtitle={`Cycle: ${nat.month || selectedMonth}`}
          icon={Activity}
          color="primary"
        />
        <StatCard
          title="Confirmed Diagnoses"
          value={
            nat.totals?.confirmed != null
              ? nat.totals.confirmed.toLocaleString('en-IN')
              : '1,203'
          }
          subtitle="Molecularly verified cases"
          icon={CheckCircle2}
          color="secondary"
        />
        <StatCard
          title="Reporting States"
          value={`${nat.totals?.states_reporting || rawStates.length} / 36`}
          subtitle="Covering states & union territories"
          icon={Building2}
          color="primary"
        />
        <StatCard
          title="Diagnostic Backlog"
          value={
            nat.totals?.red_flagged != null
              ? nat.totals.red_flagged.toLocaleString('en-IN')
              : '245'
          }
          subtitle="Red-flagged high-priority cases"
          icon={AlertTriangle}
          color="warning"
        />
      </div>

      {/* Transparency & Data Methodology Disclosure Banner */}
      <div className="rounded-xl border border-blue-200/80 bg-blue-50/60 p-4 text-blue-950 space-y-2">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-2.5">
            <Info size={18} className="text-blue-700 shrink-0 mt-0.5" />
            <div className="text-xs leading-relaxed">
              <span className="font-bold">Modelled Surveillance Estimates: </span>
              State-level estimates are modelled from knowledge-graph disease prevalences, NFHS-5 regional consanguinity rates, and clinical demographic models. India's official National Registry for Rare Diseases (ICMR NRROID) is not open for raw public download.
            </div>
          </div>
          <button
            onClick={() => setShowMethodology(!showMethodology)}
            className="text-xs font-semibold text-blue-800 hover:text-blue-900 flex items-center gap-1 shrink-0"
          >
            <span>{showMethodology ? 'Hide Methodology' : 'Methodology Details'}</span>
            {showMethodology ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </button>
        </div>

        {/* Expandable Methodology Details */}
        {showMethodology && (
          <div className="pt-3 mt-2 border-t border-blue-200/60 text-xs space-y-2 text-blue-900 bg-white/60 p-3 rounded-lg">
            <div>
              <span className="font-bold">Data Provenance: </span>
              Synthesized from Orphanet India epidemiological priors cross-referenced with District Level Household Survey & NFHS-5 consanguinity metrics.
            </div>
            <div>
              <span className="font-bold">Diagnostic Access Deficit Formulation: </span>
              Deficit Score = State Case Burden / (Specialist Clinicians + NABL Accredited Genetic Testing Facilities). Scores &gt;40 classified as Critical Deficit.
            </div>
            <div>
              <span className="font-bold">Temporal Cadence: </span>
              In this prototype the monthly figures are simulated from knowledge-graph prevalences and NFHS-5 rates; they are not submissions from health centers or ASHA workers.
            </div>
          </div>
        )}
      </div>

      {/* Error Alert if any non-fatal issue arose */}
      {err && <ErrorAlert error={err} title="Surveillance Notice" />}

      {/* Main Geographic Intelligence Section - ALWAYS RENDERED */}
      <div ref={mapSectionRef} className="space-y-6 scroll-mt-16">
        {/* Map + Detail / Insights Split Container */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 items-start">
          {/* Left 2 Cols: Interactive India Map */}
          <div className="lg:col-span-2 space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-primary animate-pulse" />
                <h3 className="text-xs font-bold text-on-surface uppercase tracking-wider">
                  Interactive All-India Genomic Surveillance Choropleth
                </h3>
              </div>
              <span className="text-[11px] font-mono text-outline">
                ViewBox: 36 States & UTs
              </span>
            </div>

            <IndiaMap
              statesData={rawStates}
              selectedState={selectedState}
              onSelectState={handleSelectState}
              activeMetric={activeMetric}
              onMetricChange={setActiveMetric}
              showMarkers={showMarkers}
              onToggleMarkers={() => setShowMarkers(!showMarkers)}
              showClusters={showClusters}
              onToggleClusters={() => setShowClusters(!showClusters)}
              isLoading={loading}
            />
          </div>

          {/* Right 1 Col: State Search + Detail Panel OR National Insights */}
          <div className="space-y-4">
            {/* State Search Input */}
            <div className="relative">
              <Search
                size={15}
                className="absolute left-3 top-1/2 -translate-y-1/2 text-outline"
              />
              <input aria-label="Search state or territory (e.g. Tamil Nadu)..."
                type="text"
                placeholder="Search state or territory (e.g. Tamil Nadu)..."
                value={tableSearch}
                onChange={(e) => setTableSearch(e.target.value)}
                className="w-full h-10 pl-9 pr-3 rounded-xl bg-white border border-outline-variant/60 text-xs text-on-surface placeholder:text-outline focus:outline-none focus:border-primary shadow-xs font-medium"
              />
            </div>

            {/* State Details Panel (if state is selected) */}
            {selectedState ? (
              <div className="min-h-[500px]">
                <StateDetailPanel
                  state={selectedState}
                  onClose={() => setSelectedState(null)}
                  onViewInTable={handleViewInTable}
                />
              </div>
            ) : (
              /* National Insights Card (when no specific state is selected) */
              <ClinicalCard
                title="National Epidemiological Insights"
                subtitle={`Computed dynamically from ${rawStates.length} reporting states`}
                icon={Sparkles}
                headerBadge={{
                  label: 'Dynamic AI Insights',
                  color: 'secondary',
                }}
              >
                <div className="space-y-3.5">
                  {insights?.highestBurdenState && (
                    <div
                      onClick={() => handleSelectState(insights.highestBurdenState)}
                      className="p-3 rounded-xl bg-surface-container-low hover:bg-surface-container border border-outline-variant/30 cursor-pointer transition-colors space-y-1"
                    >
                      <div className="flex items-center justify-between text-xs">
                        <span className="text-outline font-semibold uppercase text-[10px]">
                          Highest Reported Burden
                        </span>
                        <span className="font-bold text-primary">
                          {insights.highestBurdenState.state}
                        </span>
                      </div>
                      <div className="text-xs font-mono font-bold text-on-surface">
                        {insights.highestBurdenState.cases.toLocaleString('en-IN')} Cases
                        <span className="text-outline font-normal font-sans ml-1 text-[11px]">
                          ({insights.highestBurdenState.confirmed} confirmed)
                        </span>
                      </div>
                    </div>
                  )}

                  {insights?.largestGapState && (
                    <div
                      onClick={() => handleSelectState(insights.largestGapState)}
                      className="p-3 rounded-xl bg-surface-container-low hover:bg-surface-container border border-outline-variant/30 cursor-pointer transition-colors space-y-1"
                    >
                      <div className="flex items-center justify-between text-xs">
                        <span className="text-outline font-semibold uppercase text-[10px]">
                          Largest Diagnostic Gap
                        </span>
                        <span className="font-bold text-amber-800">
                          {insights.largestGapState.state}
                        </span>
                      </div>
                      <div className="text-xs font-mono font-bold text-on-surface">
                        {insights.largestGapState.access_gap_score}:1 Deficit Ratio
                        <span className="text-amber-700 font-semibold uppercase text-[10px] ml-1">
                          ({insights.largestGapState.gap_label})
                        </span>
                      </div>
                    </div>
                  )}

                  {insights?.highestConsanguinityState && (
                    <div
                      onClick={() => handleSelectState(insights.highestConsanguinityState)}
                      className="p-3 rounded-xl bg-surface-container-low hover:bg-surface-container border border-outline-variant/30 cursor-pointer transition-colors space-y-1"
                    >
                      <div className="flex items-center justify-between text-xs">
                        <span className="text-outline font-semibold uppercase text-[10px]">
                          Highest Regional Consanguinity
                        </span>
                        <span className="font-bold text-secondary">
                          {insights.highestConsanguinityState.state}
                        </span>
                      </div>
                      <div className="text-xs font-mono font-bold text-on-surface">
                        {insights.highestConsanguinityState.consanguinity_rate}% Rate
                        <span className="text-outline font-normal font-sans ml-1 text-[11px]">
                          (NFHS-5 Survey)
                        </span>
                      </div>
                    </div>
                  )}

                  {insights?.topDisease && (
                    <div className="p-3 rounded-xl bg-surface-container-low border border-outline-variant/30 space-y-1">
                      <div className="flex items-center justify-between text-xs">
                        <span className="text-outline font-semibold uppercase text-[10px]">
                          Top Surveillance Locus
                        </span>
                        <span className="font-mono font-bold text-primary">
                          {insights.topDisease.id}
                        </span>
                      </div>
                      <div className="text-xs font-mono text-on-surface">
                        {insights.topDisease.count.toLocaleString('en-IN')} cumulative cases
                      </div>
                    </div>
                  )}

                  <div className="p-3 rounded-lg bg-surface-container-lowest border border-outline-variant/20 text-[11px] text-outline text-center">
                    Click any state on the map to inspect its full disease distribution & infrastructure.
                  </div>
                </div>
              </ClinicalCard>
            )}
          </div>
        </div>

        {/* Synchronized State Surveillance Table */}
        <div ref={tableRef}>
          <ClinicalCard
            title="State-Wise Surveillance & Diagnostic Deficit Table"
            subtitle={`Surveillance cycle: ${nat.month || selectedMonth} (${rawStates.length} reporting units)`}
            icon={Building2}
            actions={
              <div className="text-xs text-outline">
                Showing {filteredStates.length} of {rawStates.length} reporting states
              </div>
            }
          >
            <div className="overflow-x-auto rounded-xl border border-outline-variant/40">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="bg-surface-container-low text-on-surface-variant border-b border-outline-variant/40 font-semibold uppercase text-[10px]">
                    <th className="p-3">State / Union Territory</th>
                    <th className="p-3 text-right">Estimated Cases</th>
                    <th className="p-3 text-right">Confirmed</th>
                    <th className="p-3 text-right">Red Flagged</th>
                    <th className="p-3 text-center">Consanguinity</th>
                    <th className="p-3 w-40">Access Deficit Index</th>
                    <th className="p-3">Gap Status</th>
                    <th className="p-3 text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-outline-variant/20">
                  {filteredStates.map((s, idx) => {
                    const isSelected =
                      selectedState &&
                      normalizeStateName(selectedState.state) === normalizeStateName(s.state)

                    return (
                      <tr
                        key={idx}
                        onClick={() => handleSelectState(s)}
                        className={`cursor-pointer transition-colors ${
                          isSelected
                            ? 'bg-primary-container/20 font-medium'
                            : 'hover:bg-surface-container-low/50'
                        }`}
                      >
                        <td className="p-3">
                          <div className="font-bold text-on-surface">{s.state || s.name}</div>
                          {s.specialists != null && s.labs != null && (
                            <div className="text-[10px] text-outline font-mono">
                              {s.specialists} doctors · {s.labs} labs
                            </div>
                          )}
                        </td>
                        <td className="p-3 text-right font-mono font-bold text-primary">
                          {typeof s.cases === 'number'
                            ? s.cases.toLocaleString('en-IN')
                            : s.cases || '—'}
                        </td>
                        <td className="p-3 text-right font-mono text-on-surface-variant">
                          {s.confirmed != null ? s.confirmed.toLocaleString('en-IN') : '—'}
                        </td>
                        <td className="p-3 text-right font-mono">
                          {s.red_flagged != null ? (
                            <span className="text-amber-700 font-bold">
                              {s.red_flagged.toLocaleString('en-IN')}
                            </span>
                          ) : (
                            '—'
                          )}
                        </td>
                        <td className="p-3 text-center">
                          {s.consanguinity_rate != null ? (
                            <span className="px-2 py-0.5 rounded-full bg-secondary-container/15 text-secondary font-mono text-[11px] font-semibold border border-secondary/20">
                              {s.consanguinity_rate}%
                            </span>
                          ) : (
                            '—'
                          )}
                        </td>
                        <td className="p-3">
                          <div className="space-y-1">
                            <div className="flex items-center justify-between text-[10px] font-mono text-outline">
                              <span>Ratio: {s.access_gap_score ?? '—'}:1</span>
                            </div>
                            <ScoreBar
                              score={
                                typeof s.access_gap_score === 'number'
                                  ? Math.min(1, s.access_gap_score / 150)
                                  : 0
                              }
                              showPercentage={false}
                              color={
                                s.gap_label === 'critical'
                                  ? 'danger'
                                  : s.gap_label === 'high'
                                  ? 'warning'
                                  : 'secondary'
                              }
                              size="sm"
                            />
                          </div>
                        </td>
                        <td className="p-3">
                          <span
                            className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider border ${
                              s.gap_label === 'critical'
                                ? 'bg-red-50 text-red-800 border-red-200'
                                : s.gap_label === 'high'
                                ? 'bg-amber-50 text-amber-800 border-amber-200'
                                : 'bg-emerald-50 text-emerald-800 border-emerald-200'
                            }`}
                          >
                            {s.gap_label || 'Standard'}
                          </span>
                        </td>
                        <td className="p-3 text-right">
                          <button
                            onClick={(e) => {
                              e.stopPropagation()
                              handleFocusState(s)
                            }}
                            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all flex items-center gap-1.5 ml-auto ${
                              isSelected
                                ? 'bg-primary text-white shadow-xs ring-2 ring-primary/30'
                                : 'bg-surface-container hover:bg-primary hover:text-white text-on-surface-variant'
                            }`}
                            title={`Focus and zoom on ${s.state || s.name} on the map`}
                          >
                            <Crosshair size={13} className={isSelected ? 'text-white' : 'text-primary'} />
                            <span>{isSelected ? 'Focused' : 'Focus'}</span>
                          </button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </ClinicalCard>
        </div>

        {/* Executive Policy Brief Card */}
        {brief && (
          <ClinicalCard
            title={`Monthly Policy Brief: Rare Disease Surveillance${brief.month ? ` (${brief.month})` : ''}`}
            subtitle="Prototype brief generated from simulated data. Not an official MoHFW or ICMR document."
            icon={FileText}
          >
            <div className="space-y-4">
              <div className="text-xs text-on-surface leading-relaxed whitespace-pre-wrap bg-surface-container-low/50 p-4 rounded-xl border border-outline-variant/40 font-sans">
                {typeof brief.markdown === 'string'
                  ? brief.markdown.trim()
                  : typeof brief.brief === 'string'
                  ? brief.brief.trim()
                  : JSON.stringify(brief, null, 2)}
              </div>
            </div>
          </ClinicalCard>
        )}

        {/* Raw payload inspector: developer aid, present only in the Vite dev server, absent from production builds */}
        {import.meta.env.DEV && <div className="pt-2">
          <button
            onClick={() => setShowRawJson(!showRawJson)}
            className="text-xs font-mono text-outline hover:text-on-surface flex items-center gap-1.5"
          >
            <Code2 size={14} />
            <span>
              {showRawJson ? 'Hide Raw National Payload' : 'Inspect raw payload (development only)'}
            </span>
          </button>
          {showRawJson && (
            <pre className="mt-2 p-4 rounded-xl bg-surface-container-lowest border border-outline-variant/40 text-[11px] font-mono text-on-surface-variant overflow-x-auto max-h-96">
              {JSON.stringify(nat, null, 2)}
            </pre>
          )}
        </div>}
      </div>
    </div>
  )
}
