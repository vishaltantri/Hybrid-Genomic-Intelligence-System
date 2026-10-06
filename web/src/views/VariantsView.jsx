import React, { useState, useEffect, useMemo } from 'react'
import { api, uploadVcfFile, consumeNavContext, setNavContext } from '../api.js'
import {
  Dna,
  Upload,
  FileText,
  Search,
  Filter,
  AlertTriangle,
  CheckCircle2,
  HelpCircle,
  ShieldAlert,
  ChevronRight,
  ExternalLink,
  Sparkles,
  Layers,
  ArrowRight,
  FileCheck,
  RefreshCw,
  X,
  SlidersHorizontal,
  Info
} from 'lucide-react'

export default function VariantsView({ onNavigateToDiagnosis, onNavigateToKg, onNavigateToReport }) {
  // State
  const [file, setFile] = useState(null)
  const [isUploading, setIsUploading] = useState(false)
  const [analysesList, setAnalysesList] = useState([])
  const [currentAnalysis, setCurrentAnalysis] = useState(null)
  const [selectedVariant, setSelectedVariant] = useState(null)
  const [errorMessage, setErrorMessage] = useState(null)
  const [successNotice, setSuccessNotice] = useState(null)
  const [loadingDemo, setLoadingDemo] = useState(false)

  // Filtering & Search
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedClassification, setSelectedClassification] = useState('ALL')
  const [selectedTier, setSelectedTier] = useState('ALL')
  const [selectedGene, setSelectedGene] = useState('ALL')

  // Patient link state
  const [patientId, setPatientId] = useState('')
  const [patientsList, setPatientsList] = useState([])

  // Load existing analyses and patients on mount
  useEffect(() => {
    // One-shot hint left by another module (e.g. Digital Twin) to open a specific analysis/variant
    const ctx = consumeNavContext('variants')
    if (ctx?.patient_id) setPatientId(ctx.patient_id)
    loadAnalyses(ctx)
    loadPatients()
  }, [])

  const loadAnalyses = async (ctx) => {
    try {
      const list = await api.listVariantAnalyses()
      setAnalysesList(list || [])
      if (ctx?.analysis_id) {
        loadAnalysisDetail(ctx.analysis_id, ctx.variant_id)
        return
      }
      // Arriving for a specific patient: open that patient's own newest analysis (the list is newest first)
      const own = ctx?.patient_id ? (list || []).find((x) => x.patient_id === ctx.patient_id) : null
      if (own) {
        loadAnalysisDetail(own.analysis_id)
        return
      }
      // If we don't have an active analysis but there's a previous one, load it
      if (!currentAnalysis && list && list.length > 0) {
        loadAnalysisDetail(list[0].analysis_id)
      }
    } catch (err) {
      console.warn('Failed to fetch analyses list', err)
    }
  }

  const loadPatients = async () => {
    try {
      const p = await api.listPatients()
      setPatientsList(p || [])
    } catch (err) {
      console.warn('Failed to fetch patients list', err)
    }
  }

  const loadAnalysisDetail = async (analysisId, variantId) => {
    try {
      const detail = await api.getVariantAnalysis(analysisId)
      setCurrentAnalysis(detail)
      if (detail?.variants?.length > 0) {
        setSelectedVariant(detail.variants.find((v) => v.variant_id === variantId) || detail.variants[0])
      }
    } catch (err) {
      setErrorMessage(`Failed to load analysis ${analysisId}: ${err.message}`)
    }
  }

  // Handle file selection
  const handleFileChange = (e) => {
    const f = e.target.files?.[0]
    if (f) {
      setFile(f)
      setErrorMessage(null)
    }
  }

  // Handle standard VCF upload
  const handleUpload = async () => {
    if (!file) {
      setErrorMessage('Please select a .vcf or .vcf.gz file to upload.')
      return
    }

    setIsUploading(true)
    setErrorMessage(null)
    setSuccessNotice(null)

    try {
      const formData = new FormData()
      formData.append('file', file)
      if (patientId) formData.append('patient_id', patientId)

      const res = await uploadVcfFile(formData)
      setCurrentAnalysis(res)
      if (res?.variants?.length > 0) {
        setSelectedVariant(res.variants[0])
      }
      setSuccessNotice(`Successfully processed ${res.qc_metrics?.total_variants} variants from ${res.filename}.`)
      loadAnalyses()
    } catch (err) {
      setErrorMessage(err.message || 'Error uploading VCF file.')
    } finally {
      setIsUploading(false)
    }
  }

  // Quick 1-click Demo VCF handler
  const handleLoadDemo = async () => {
    setLoadingDemo(true)
    setErrorMessage(null)
    setSuccessNotice(null)

    try {
      const demo = await api.getDemoVcf()
      const blob = new Blob([demo.content], { type: 'text/plain' })
      const demoFile = new File([blob], demo.filename, { type: 'text/plain' })

      const formData = new FormData()
      formData.append('file', demoFile)
      formData.append('patient_id', 'PAT-SAMPLE-01')
      // Pass Wilson Disease and Sickle Cell HPOs for priority scoring
      formData.append('hpo_ids_json', JSON.stringify(['HP:0200032', 'HP:0001337', 'HP:0001878']))

      const res = await uploadVcfFile(formData)
      setCurrentAnalysis(res)
      if (res?.variants?.length > 0) {
        setSelectedVariant(res.variants[0])
      }
      setSuccessNotice('Loaded verified clinical test trio VCF (ATP7B, HBB, BRCA1, CYP2C19).')
      loadAnalyses()
    } catch (err) {
      setErrorMessage(`Failed to load demo VCF: ${err.message}`)
    } finally {
      setLoadingDemo(false)
    }
  }

  // Handoff to Differential Diagnosis
  const handleDiagnosisHandoff = async () => {
    if (!currentAnalysis || !selectedVariant) return
    try {
      const res = await api.handoffToDiagnosis(currentAnalysis.analysis_id, {
        variant_ids: [selectedVariant.variant_id],
        patient_id: currentAnalysis.patient_id,
      })
      setSuccessNotice(
        `Forwarded candidate gene ${selectedVariant.gene_symbol} (${selectedVariant.hgvs}) to Differential Diagnosis.`
      )
      if (onNavigateToDiagnosis) {
        setTimeout(() => onNavigateToDiagnosis('diagnosis'), 1200)
      }
    } catch (err) {
      setErrorMessage(`Diagnosis handoff failed: ${err.message}`)
    }
  }

  // Open the Evidence & Literature workspace at this variant
  const handleViewEvidence = () => {
    if (!currentAnalysis || !selectedVariant) return
    setNavContext('evidence', {
      analysis_id: currentAnalysis.analysis_id, variant_id: selectedVariant.variant_id,
      patient_id: currentAnalysis.patient_id, gene: selectedVariant.gene_symbol, hgvs: selectedVariant.hgvs,
    })
    if (onNavigateToDiagnosis) onNavigateToDiagnosis('evidence')
  }

  // Open the Knowledge Graph at this variant's gene (and the case, when linked)
  const handleViewGraph = () => {
    if (!selectedVariant) return
    setNavContext('kg', { gene: selectedVariant.gene_symbol, disease_id: selectedVariant.disease_id || undefined })
    if (onNavigateToDiagnosis) onNavigateToDiagnosis('kg')
  }

  // Handoff to Clinical Report
  const handleReportHandoff = async () => {
    if (!currentAnalysis || !selectedVariant) return
    try {
      await api.handoffToReport(currentAnalysis.analysis_id, {
        variant_ids: [selectedVariant.variant_id],
        patient_id: currentAnalysis.patient_id,
      })
      setSuccessNotice(`Variant ${selectedVariant.hgvs} queued to Clinical Report bundle.`)
      if (onNavigateToReport) {
        setTimeout(() => onNavigateToReport('reports'), 1200)
      }
    } catch (err) {
      setErrorMessage(`Report handoff failed: ${err.message}`)
    }
  }

  // Filtered variants
  const filteredVariants = useMemo(() => {
    if (!currentAnalysis?.variants) return []
    return currentAnalysis.variants.filter((v) => {
      // Search query
      const q = searchQuery.toLowerCase().trim()
      if (q) {
        const matchId = v.variant_id?.toLowerCase().includes(q)
        const matchGene = v.gene_symbol?.toLowerCase().includes(q)
        const matchHgvs = v.hgvs?.toLowerCase().includes(q)
        const matchDisease = v.disease_name?.toLowerCase().includes(q)
        const matchClinvar = v.clinvar_id?.toLowerCase().includes(q)
        if (!matchId && !matchGene && !matchHgvs && !matchDisease && !matchClinvar) {
          return false
        }
      }

      // Classification
      if (selectedClassification !== 'ALL') {
        if (selectedClassification === 'PATHOGENIC') {
          if (v.acmg_classification !== 'Pathogenic' && v.acmg_classification !== 'Likely pathogenic') {
            return false
          }
        } else if (selectedClassification === 'VUS') {
          if (v.acmg_classification !== 'Uncertain significance') return false
        } else if (selectedClassification === 'BENIGN') {
          if (v.acmg_classification !== 'Benign' && v.acmg_classification !== 'Likely benign') return false
        }
      }

      // Tier
      if (selectedTier !== 'ALL') {
        if (selectedTier === 'TIER1' && !v.priority_tier?.startsWith('Tier 1')) return false
        if (selectedTier === 'TIER2' && !v.priority_tier?.startsWith('Tier 2')) return false
        if (selectedTier === 'TIER3' && !v.priority_tier?.startsWith('Tier 3')) return false
      }

      // Gene
      if (selectedGene !== 'ALL' && v.gene_symbol !== selectedGene) {
        return false
      }

      return true
    })
  }, [currentAnalysis, searchQuery, selectedClassification, selectedTier, selectedGene])

  // Distinct genes for filter
  const distinctGenes = useMemo(() => {
    if (!currentAnalysis?.variants) return []
    const set = new Set()
    currentAnalysis.variants.forEach((v) => {
      if (v.gene_symbol) set.add(v.gene_symbol)
    })
    return Array.from(set).sort()
  }, [currentAnalysis])

  // Badge styling helper
  const getClassificationBadge = (cls) => {
    switch (cls) {
      case 'Pathogenic':
        return 'bg-red-50 text-red-700 border-red-200'
      case 'Likely pathogenic':
        return 'bg-amber-50 text-amber-700 border-amber-200'
      case 'Uncertain significance':
        return 'bg-blue-50 text-blue-700 border-blue-200'
      case 'Likely benign':
        return 'bg-emerald-50 text-emerald-700 border-emerald-200'
      case 'Benign':
        return 'bg-slate-50 text-slate-700 border-slate-200'
      default:
        return 'bg-slate-100 text-slate-600 border-slate-200'
    }
  }

  const getTierBadge = (tier) => {
    if (tier?.startsWith('Tier 1')) {
      return 'bg-rose-50 text-rose-700 border-rose-200 font-semibold'
    }
    if (tier?.startsWith('Tier 2')) {
      return 'bg-amber-50 text-amber-700 border-amber-200'
    }
    return 'bg-slate-100 text-slate-600 border-slate-200'
  }

  return (
    <div className="space-y-6">
      {/* Top Banner / Headline */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-2 border-b border-outline-variant/30">
        <div>
          <div className="flex items-center gap-2">
            <span className="p-2 rounded-xl bg-primary/10 text-primary">
              <Dna size={22} />
            </span>
            <div>
              <h1 className="text-xl font-bold font-headline-sm text-on-surface">
                VCF Variant Intelligence & ACMG/AMP Workspace
              </h1>
              <p className="text-xs text-on-surface-variant">
                Full VCF 4.2+ parsing, indel normalization, IndiGenomes/GenomeIndia population frequency, and 2015 ACMG/AMP clinical classification.
              </p>
            </div>
          </div>
        </div>

        {/* Quick action buttons */}
        <div className="flex items-center gap-2">
          <button
            onClick={handleLoadDemo}
            disabled={loadingDemo || isUploading}
            className="inline-flex items-center gap-2 px-3.5 py-2 rounded-xl bg-secondary-container/20 text-secondary border border-secondary/30 text-xs font-semibold hover:bg-secondary-container/30 transition-all shadow-sm disabled:opacity-50"
          >
            <Sparkles size={14} className={loadingDemo ? 'animate-spin' : ''} />
            <span>{loadingDemo ? 'Analyzing Trio...' : 'Load Verified Clinical Trio VCF'}</span>
          </button>
        </div>
      </div>

      {/* Notices */}
      {errorMessage && (
        <div className="p-3.5 rounded-xl bg-red-50 border border-red-200 text-red-700 text-xs flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertTriangle size={16} className="text-red-500 shrink-0" />
            <span>{errorMessage}</span>
          </div>
          <button onClick={() => setErrorMessage(null)} className="text-red-400 hover:text-red-600">
            <X size={14} />
          </button>
        </div>
      )}

      {successNotice && (
        <div className="p-3.5 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs flex items-center justify-between">
          <div className="flex items-center gap-2">
            <CheckCircle2 size={16} className="text-emerald-600 shrink-0" />
            <span>{successNotice}</span>
          </div>
          <button onClick={() => setSuccessNotice(null)} className="text-emerald-500 hover:text-emerald-700">
            <X size={14} />
          </button>
        </div>
      )}

      {/* Upload & Context Selector Panel */}
      <div className="panel grid grid-cols-1 lg:grid-cols-12 gap-5 items-center">
        {/* Upload Drop Area */}
        <div className="lg:col-span-7 flex flex-col sm:flex-row items-center gap-4">
          <div className="w-full relative border-2 border-dashed border-outline-variant rounded-xl p-4 text-center hover:border-primary/60 transition-colors bg-surface-container-lowest/50">
            <input aria-label="Upload VCF file"
              type="file"
              accept=".vcf,.vcf.gz,.txt"
              onChange={handleFileChange}
              disabled={isUploading}
              className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
            />
            <div className="flex flex-col items-center justify-center pointer-events-none">
              <Upload size={22} className="text-primary mb-1.5" />
              <div className="text-xs font-semibold text-on-surface">
                {file ? file.name : 'Choose VCF File or Drag Here'}
              </div>
              <div className="text-[10px] text-on-surface-variant mt-0.5">
                Supports single-sample or multi-sample VCF 4.2+ (.vcf or .vcf.gz)
              </div>
            </div>
          </div>

          <button
            onClick={handleUpload}
            disabled={!file || isUploading}
            className="w-full sm:w-auto shrink-0 inline-flex items-center justify-center gap-2 px-5 py-3 rounded-xl bg-primary text-white text-xs font-semibold hover:bg-primary-container transition-all shadow-sm disabled:opacity-50"
          >
            <RefreshCw size={14} className={isUploading ? 'animate-spin' : ''} />
            <span>{isUploading ? 'Annotating...' : 'Analyze VCF'}</span>
          </button>
        </div>

        {/* Patient / Session Linker */}
        <div className="lg:col-span-5 flex flex-col sm:flex-row items-center gap-3">
          <div className="w-full">
            <label className="block text-[11px] font-semibold text-on-surface-variant uppercase tracking-wider mb-1">
              Link Clinical Patient (Optional)
            </label>
            <select aria-label="Link Clinical Patient (Optional)"
              value={patientId}
              onChange={(e) => setPatientId(e.target.value)}
              className="w-full px-3 py-2 text-xs rounded-lg border border-outline bg-surface text-on-surface focus:outline-none focus:ring-1 focus:ring-primary"
            >
              <option value="">None (Standalone Genomic Analysis)</option>
              {patientsList.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name || p.id} ({p.state || 'India'} - {p.community || 'General'})
                </option>
              ))}
            </select>
          </div>

          {/* Session history dropdown */}
          {analysesList.length > 0 && (
            <div className="w-full sm:w-auto shrink-0">
              <label className="block text-[11px] font-semibold text-on-surface-variant uppercase tracking-wider mb-1">
                Recent Runs
              </label>
              <select aria-label="Recent Runs"
                value={currentAnalysis?.analysis_id || ''}
                onChange={(e) => loadAnalysisDetail(e.target.value)}
                className="w-full px-3 py-2 text-xs rounded-lg border border-outline bg-surface text-on-surface focus:outline-none focus:ring-1 focus:ring-primary"
              >
                {analysesList.map((a) => (
                  <option key={a.analysis_id} value={a.analysis_id}>
                    {a.analysis_id} ({a.filename.slice(0, 15)})
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>
      </div>

      {/* QC Metrics & Summary KPIs */}
      {currentAnalysis && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          <div className="panel p-3.5 flex flex-col justify-between">
            <span className="text-[11px] font-semibold text-on-surface-variant">TOTAL VARIANTS</span>
            <div className="text-xl font-bold font-headline-sm text-on-surface mt-1">
              {currentAnalysis.qc_metrics?.total_variants || 0}
            </div>
            <span className="text-[10px] text-on-surface-variant mt-0.5">
              {currentAnalysis.qc_metrics?.sample_count || 1} sample(s) parsed
            </span>
          </div>

          <div className="panel p-3.5 flex flex-col justify-between bg-red-50/40 border-red-200">
            <span className="text-[11px] font-semibold text-red-700">PATHOGENIC</span>
            <div className="text-xl font-bold font-headline-sm text-red-700 mt-1">
              {currentAnalysis.qc_metrics?.pathogenic_count || 0}
            </div>
            <span className="text-[10px] text-red-600 mt-0.5">ACMG Class 5</span>
          </div>

          <div className="panel p-3.5 flex flex-col justify-between bg-amber-50/40 border-amber-200">
            <span className="text-[11px] font-semibold text-amber-700">LIKELY PATHOGENIC</span>
            <div className="text-xl font-bold font-headline-sm text-amber-700 mt-1">
              {currentAnalysis.qc_metrics?.likely_pathogenic_count || 0}
            </div>
            <span className="text-[10px] text-amber-600 mt-0.5">ACMG Class 4</span>
          </div>

          <div className="panel p-3.5 flex flex-col justify-between bg-blue-50/40 border-blue-200">
            <span className="text-[11px] font-semibold text-blue-700">VUS (UNCERTAIN)</span>
            <div className="text-xl font-bold font-headline-sm text-blue-700 mt-1">
              {currentAnalysis.qc_metrics?.vus_count || 0}
            </div>
            <span className="text-[10px] text-blue-600 mt-0.5">ACMG Class 3</span>
          </div>

          <div className="panel p-3.5 flex flex-col justify-between bg-emerald-50/40 border-emerald-200">
            <span className="text-[11px] font-semibold text-emerald-700">BENIGN / LIKELY</span>
            <div className="text-xl font-bold font-headline-sm text-emerald-700 mt-1">
              {currentAnalysis.qc_metrics?.benign_count || 0}
            </div>
            <span className="text-[10px] text-emerald-600 mt-0.5">BA1 / BS1 filter</span>
          </div>

          <div className="panel p-3.5 flex flex-col justify-between bg-purple-50/40 border-purple-200">
            <span className="text-[11px] font-semibold text-purple-700">PGX ACTIONABLE</span>
            <div className="text-xl font-bold font-headline-sm text-purple-700 mt-1">
              {currentAnalysis.qc_metrics?.pgx_variant_count || 0}
            </div>
            <span className="text-[10px] text-purple-600 mt-0.5">CPIC Guidelines</span>
          </div>
        </div>
      )}

      {/* Main Interactive Clinical Workspace: Table + Detail Drawer */}
      {currentAnalysis && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          {/* Variants Table Column */}
          <div className="lg:col-span-7 space-y-4">
            {/* Filters Bar */}
            <div className="panel p-3 flex flex-wrap items-center justify-between gap-3">
              <div className="relative flex-1 min-w-[180px]">
                <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant" />
                <input aria-label="Filter gene, cDNA, ClinVar, disease..."
                  type="text"
                  placeholder="Filter gene, cDNA, ClinVar, disease..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full pl-8 pr-3 py-1.5 text-xs rounded-lg border border-outline bg-surface text-on-surface placeholder:text-on-surface-variant/50 focus:outline-none focus:ring-1 focus:ring-primary"
                />
              </div>

              <div className="flex items-center gap-2 flex-wrap">
                <select aria-label="Filter by ACMG classification"
                  value={selectedClassification}
                  onChange={(e) => setSelectedClassification(e.target.value)}
                  className="px-2.5 py-1.5 text-xs rounded-lg border border-outline bg-surface text-on-surface focus:outline-none"
                >
                  <option value="ALL">All Classifications</option>
                  <option value="PATHOGENIC">Pathogenic / Likely Pathogenic</option>
                  <option value="VUS">VUS</option>
                  <option value="BENIGN">Benign / Likely Benign</option>
                </select>

                <select aria-label="Filter by tier"
                  value={selectedTier}
                  onChange={(e) => setSelectedTier(e.target.value)}
                  className="px-2.5 py-1.5 text-xs rounded-lg border border-outline bg-surface text-on-surface focus:outline-none"
                >
                  <option value="ALL">All Tiers</option>
                  <option value="TIER1">Tier 1 (High Actionability)</option>
                  <option value="TIER2">Tier 2 (Candidate)</option>
                  <option value="TIER3">Tier 3 (Low)</option>
                </select>

                {distinctGenes.length > 0 && (
                  <select aria-label="Filter by gene"
                    value={selectedGene}
                    onChange={(e) => setSelectedGene(e.target.value)}
                    className="px-2.5 py-1.5 text-xs rounded-lg border border-outline bg-surface text-on-surface focus:outline-none"
                  >
                    <option value="ALL">All Genes ({distinctGenes.length})</option>
                    {distinctGenes.map((g) => (
                      <option key={g} value={g}>
                        {g}
                      </option>
                    ))}
                  </select>
                )}
              </div>
            </div>

            {/* Table */}
            <div className="panel p-0 overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-surface-container-low border-b border-outline-variant/30 text-[11px] font-semibold text-on-surface-variant uppercase tracking-wider">
                    <tr>
                      <th className="px-3.5 py-3">Rank / Tier</th>
                      <th className="px-3.5 py-3">Gene & Variant</th>
                      <th className="px-3.5 py-3">Genotype</th>
                      <th className="px-3.5 py-3">ACMG / AMP</th>
                      <th className="px-3.5 py-3">Indian AF</th>
                      <th className="px-3.5 py-3 text-right">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-outline-variant/20">
                    {filteredVariants.length === 0 ? (
                      <tr>
                        <td colSpan={6} className="px-4 py-8 text-center text-on-surface-variant text-xs">
                          No variants match current filters.
                        </td>
                      </tr>
                    ) : (
                      filteredVariants.map((v) => {
                        const isSelected = selectedVariant?.variant_id === v.variant_id
                        return (
                          <tr
                            key={v.variant_id}
                            onClick={() => setSelectedVariant(v)}
                            className={`cursor-pointer transition-colors ${
                              isSelected
                                ? 'bg-primary/10 border-l-4 border-l-primary'
                                : 'hover:bg-surface-container-low'
                            }`}
                          >
                            <td className="px-3.5 py-3 whitespace-nowrap">
                              <div className="flex items-center gap-1.5">
                                <span className="font-bold text-on-surface">#{v.rank}</span>
                                <span
                                  className={`text-[10px] px-1.5 py-0.5 rounded border ${getTierBadge(
                                    v.priority_tier
                                  )}`}
                                >
                                  {v.priority_tier?.split(':')[0]}
                                </span>
                              </div>
                              <div className="text-[10px] text-on-surface-variant mt-0.5">
                                Score: {v.priority_score}%
                              </div>
                            </td>

                            <td className="px-3.5 py-3">
                              <div className="font-bold text-on-surface">{v.gene_symbol || 'Intergenic'}</div>
                              <div className="font-mono text-[11px] text-primary">{v.cdna || v.hgvs}</div>
                              <div className="text-[10px] text-on-surface-variant truncate max-w-[150px]">
                                {v.consequence.replace(/_/g, ' ')}
                              </div>
                            </td>

                            <td className="px-3.5 py-3 whitespace-nowrap">
                              <span className="font-mono text-[11px] font-semibold text-on-surface">
                                {v.genotype}
                              </span>
                              <div className="text-[10px] text-on-surface-variant">{v.zygosity}</div>
                              {v.depth && <div className="text-[10px] text-on-surface-variant/70">DP: {v.depth}x</div>}
                            </td>

                            <td className="px-3.5 py-3 whitespace-nowrap">
                              <span
                                className={`inline-block px-2 py-0.5 rounded-full text-[10px] font-semibold border ${getClassificationBadge(
                                  v.acmg_classification
                                )}`}
                              >
                                {v.acmg_classification}
                              </span>
                              <div className="text-[10px] text-on-surface-variant mt-0.5">
                                {v.criteria_met_pathogenic?.length > 0
                                  ? v.criteria_met_pathogenic.join(', ')
                                  : 'No path criteria'}
                              </div>
                            </td>

                            <td className="px-3.5 py-3 whitespace-nowrap">
                              <div className="font-mono text-on-surface">
                                {v.af_indian !== null && v.af_indian !== undefined
                                  ? `${(v.af_indian * 100).toFixed(3)}%`
                                  : 'Data unavailable'}
                              </div>
                              <div className="text-[10px] text-on-surface-variant">
                                Global: {v.af_global !== null && v.af_global !== undefined ? `${(v.af_global * 100).toFixed(3)}%` : 'N/A'}
                              </div>
                            </td>

                            <td className="px-3.5 py-3 text-right whitespace-nowrap">
                              <button
                                onClick={(e) => {
                                  e.stopPropagation()
                                  setSelectedVariant(v)
                                }}
                                className="px-2.5 py-1 rounded bg-surface-container text-xs font-medium text-primary hover:bg-primary hover:text-white transition-colors"
                              >
                                View
                              </button>
                            </td>
                          </tr>
                        )
                      })
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          {/* Detailed Clinical Variant Drawer Column */}
          <div className="lg:col-span-5 space-y-4">
            {selectedVariant ? (
              <div className="panel space-y-5">
                {/* Variant Header */}
                <div className="flex items-start justify-between pb-3 border-b border-outline-variant/30">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-base font-bold text-on-surface">
                        {selectedVariant.gene_symbol || 'Genomic Variant'}
                      </span>
                      <span
                        className={`text-[10px] px-2 py-0.5 rounded-full border font-semibold ${getClassificationBadge(
                          selectedVariant.acmg_classification
                        )}`}
                      >
                        {selectedVariant.acmg_classification}
                      </span>
                    </div>
                    <div className="font-mono text-xs text-primary font-semibold mt-0.5">
                      {selectedVariant.cdna || selectedVariant.hgvs}
                    </div>
                    {selectedVariant.protein && (
                      <div className="font-mono text-[11px] text-on-surface-variant">
                        {selectedVariant.protein}
                      </div>
                    )}
                  </div>

                  <div className="text-right">
                    <span className="text-[10px] font-semibold text-on-surface-variant uppercase">Rank</span>
                    <div className="text-base font-bold text-on-surface">#{selectedVariant.rank}</div>
                  </div>
                </div>

                {/* Priority Rationale Highlights */}
                <div>
                  <h4 className="text-[11px] font-semibold text-on-surface-variant uppercase tracking-wider mb-1.5 flex items-center gap-1.5">
                    <Sparkles size={13} className="text-primary" />
                    <span>Clinical Prioritization Rationale</span>
                  </h4>
                  <ul className="space-y-1 text-xs text-on-surface">
                    {selectedVariant.priority_rationale?.map((r, idx) => (
                      <li key={idx} className="flex items-start gap-1.5">
                        <span className="text-primary mt-0.5">•</span>
                        <span>{r}</span>
                      </li>
                    ))}
                  </ul>
                </div>

                {/* Evidence & Population Frequencies */}
                <div className="grid grid-cols-2 gap-3 text-xs bg-surface-container-lowest p-3 rounded-xl border border-outline-variant/30">
                  <div>
                    <span className="text-[10px] font-semibold text-on-surface-variant uppercase">
                      Indian Population AF
                    </span>
                    <div className="font-bold font-mono text-on-surface mt-0.5">
                      {selectedVariant.af_indian !== null && selectedVariant.af_indian !== undefined
                        ? `${(selectedVariant.af_indian * 100).toFixed(4)}%`
                        : 'Data unavailable in IndiGenomes'}
                    </div>
                    <span className="text-[9px] text-on-surface-variant">IndiGenomes + GenomeIndia</span>
                  </div>

                  <div>
                    <span className="text-[10px] font-semibold text-on-surface-variant uppercase">
                      ClinVar Significance
                    </span>
                    <div className="font-bold text-on-surface mt-0.5">
                      {selectedVariant.clinvar_significance || 'No matching record in configured dataset'}
                    </div>
                    <span className="text-[9px] text-on-surface-variant">
                      {selectedVariant.clinvar_id || 'ClinVar Accession N/A'}
                    </span>
                  </div>

                  <div>
                    <span className="text-[10px] font-semibold text-on-surface-variant uppercase">
                      In-Silico Deleteriousness
                    </span>
                    <div className="font-bold text-on-surface mt-0.5">
                      CADD Phred: {selectedVariant.cadd_phred?.toFixed(1) || 'N/A'}
                    </div>
                    <span className="text-[9px] text-on-surface-variant">
                      {selectedVariant.revel_score ? `REVEL: ${selectedVariant.revel_score}` : 'Pathogenicity threshold: >=20'}
                    </span>
                  </div>

                  <div>
                    <span className="text-[10px] font-semibold text-on-surface-variant uppercase">
                      Orphanet Disease
                    </span>
                    <div className="font-bold text-on-surface mt-0.5 truncate">
                      {selectedVariant.disease_name || 'N/A'}
                    </div>
                    <span className="text-[9px] text-on-surface-variant">
                      {selectedVariant.disease_id || selectedVariant.inheritance || 'Inheritance N/A'}
                    </span>
                  </div>
                </div>

                {/* 2015 ACMG / AMP Criteria Matrix Breakdown */}
                <div>
                  <h4 className="text-[11px] font-semibold text-on-surface-variant uppercase tracking-wider mb-2 flex items-center justify-between">
                    <span>ACMG / AMP 2015 Criteria Assessment</span>
                    <span className="text-[10px] font-normal text-on-surface-variant">
                      {selectedVariant.all_criteria?.filter((c) => c.status === 'Met').length || 0} met
                    </span>
                  </h4>

                  <div className="space-y-2 max-h-[220px] overflow-y-auto pr-1">
                    {selectedVariant.all_criteria?.map((c) => {
                      const isMet = c.status === 'Met'
                      return (
                        <div
                          key={c.code}
                          className={`p-2.5 rounded-lg border text-xs transition-colors ${
                            isMet
                              ? c.category === 'Pathogenic'
                                ? 'bg-red-50/60 border-red-200'
                                : 'bg-emerald-50/60 border-emerald-200'
                              : 'bg-surface-container-low/40 border-outline-variant/30 opacity-70'
                          }`}
                        >
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-1.5">
                              <span
                                className={`font-mono font-bold text-[11px] ${
                                  isMet
                                    ? c.category === 'Pathogenic'
                                      ? 'text-red-700'
                                      : 'text-emerald-700'
                                    : 'text-on-surface-variant'
                                }`}
                              >
                                {c.code}
                              </span>
                              <span className="text-[10px] text-on-surface-variant">
                                ({c.applied_strength})
                              </span>
                            </div>
                            <span
                              className={`text-[10px] font-semibold px-1.5 py-0.2 rounded ${
                                isMet
                                  ? 'bg-primary text-white'
                                  : 'bg-surface-container text-on-surface-variant'
                              }`}
                            >
                              {c.status}
                            </span>
                          </div>
                          <div className="text-[11px] text-on-surface mt-1">{c.description}</div>
                          {isMet && (
                            <div className="text-[10px] font-semibold text-primary mt-1">
                              Evidence: {c.evidence}
                            </div>
                          )}
                        </div>
                      )
                    })}
                  </div>
                </div>

                {/* Integration Handoff Actions */}
                <div className="pt-2 border-t border-outline-variant/30 space-y-2">
                  <div className="text-[11px] font-semibold text-on-surface-variant uppercase tracking-wider mb-2">
                    Clinical Platform Workflows
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    <button
                      onClick={handleDiagnosisHandoff}
                      className="inline-flex items-center justify-center gap-2 px-3 py-2 rounded-xl bg-primary text-white text-xs font-semibold hover:bg-primary-container transition-all shadow-sm"
                    >
                      <Layers size={14} />
                      <span>Forward to Diagnosis</span>
                    </button>

                    <button
                      onClick={handleReportHandoff}
                      className="inline-flex items-center justify-center gap-2 px-3 py-2 rounded-xl bg-surface-container text-primary border border-primary/20 text-xs font-semibold hover:bg-surface-container-high transition-all"
                    >
                      <FileCheck size={14} />
                      <span>Queue in Report</span>
                    </button>

                    <button
                      onClick={handleViewEvidence}
                      className="inline-flex items-center justify-center gap-2 px-3 py-2 rounded-xl bg-surface-container text-primary border border-primary/20 text-xs font-semibold hover:bg-surface-container-high transition-all"
                    >
                      <Search size={14} />
                      <span>View Evidence</span>
                    </button>

                    <button
                      onClick={handleViewGraph}
                      className="inline-flex items-center justify-center gap-2 px-3 py-2 rounded-xl bg-surface-container text-primary border border-primary/20 text-xs font-semibold hover:bg-surface-container-high transition-all"
                    >
                      <Search size={14} />
                      <span>View in Knowledge Graph</span>
                    </button>
                  </div>
                </div>
              </div>
            ) : (
              <div className="panel text-center py-12 text-on-surface-variant text-xs">
                Select a variant from the table to inspect detailed ACMG criteria, population frequencies, and clinical handoffs.
              </div>
            )}
          </div>
        </div>
      )}

      {/* Initial Empty State if no analysis loaded */}
      {!currentAnalysis && (
        <div className="panel text-center py-16 space-y-3">
          <Dna size={40} className="mx-auto text-primary/40 animate-pulse" />
          <h3 className="text-base font-bold text-on-surface">No VCF Analysis Loaded</h3>
          <p className="text-xs text-on-surface-variant max-w-md mx-auto">
            Upload a patient Whole Exome/Genome Sequencing VCF or click the "Load Verified Clinical Trio VCF" button to test the complete ACMG/AMP variant intelligence pipeline.
          </p>
        </div>
      )}
    </div>
  )
}
