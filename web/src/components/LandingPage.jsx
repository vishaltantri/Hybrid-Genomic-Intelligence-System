import React from 'react'
import Logo from './Logo.jsx'

export default function LandingPage({ onSignIn, onExploreDemo }) {
  const scrollTo = (id) => {
    const el = document.getElementById(id)
    if (el) el.scrollIntoView({ behavior: 'smooth' })
  }

  const handleOpenNationalMap = () => {
    if (onExploreDemo) {
      onExploreDemo('national')
    } else {
      onSignIn()
    }
  }

  return (
    <div
      className="bg-background font-body-md text-on-surface antialiased min-h-screen"
      style={{
        background:
          'linear-gradient(180deg, #d8eefc 0%, #cae7fb 18%, #bee0fa 42%, #cbe5f8 65%, #c0e0f8 85%, #d1e8fc 100%)',
        backgroundAttachment: 'fixed',
      }}
    >
      {/* HEADER */}
      <header className="sticky top-0 z-50 w-full bg-surface-container-lowest/80 backdrop-blur-md border-b border-outline-variant/40 shadow-[0_1px_8px_rgba(0,28,55,0.04)] transition-all duration-300">
        <div className="h-16 max-w-7xl mx-auto px-4 lg:px-8 flex items-center justify-between gap-6">
          <div className="flex items-center gap-6">
            <a
              className="flex items-center gap-3 group focus:outline-none"
              href="#"
              onClick={(e) => {
                e.preventDefault()
                window.scrollTo({ top: 0, behavior: 'smooth' })
              }}
            >
              <Logo size={38} className="shadow-xs group-hover:scale-105 transition-transform" />
              <div className="flex flex-col">
                <span className="font-headline-sm text-lg font-bold tracking-tight text-on-surface group-hover:text-primary transition-colors leading-tight">
                  GENOMERA
                </span>
                <span className="font-label-sm text-[10px] tracking-wider font-semibold text-secondary uppercase -mt-0.5">
                  CLINICAL INTELLIGENCE
                </span>
              </div>
            </a>
          </div>

          <nav className="hidden lg:flex items-center gap-7 h-full">
            <button
              onClick={() => scrollTo('platform')}
              className="font-title-sm text-sm text-primary font-semibold border-b-2 border-primary py-2 transition-colors"
            >
              Platform
            </button>
            <button
              onClick={() => scrollTo('capabilities')}
              className="font-title-sm text-sm text-on-surface-variant hover:text-primary transition-colors py-2"
            >
              Intelligence
            </button>
            <button
              onClick={() => scrollTo('assistant')}
              className="font-title-sm text-sm text-on-surface-variant hover:text-primary transition-colors py-2"
            >
              AI Assistant
            </button>
            <button
              onClick={() => scrollTo('digital-twin')}
              className="font-title-sm text-sm text-on-surface-variant hover:text-primary transition-colors py-2"
            >
              Digital Twin
            </button>
            <button
              onClick={() => scrollTo('research')}
              className="font-title-sm text-sm text-on-surface-variant hover:text-primary transition-colors py-2"
            >
              Research
            </button>
            <button
              onClick={() => scrollTo('workflow')}
              className="font-title-sm text-sm text-on-surface-variant hover:text-primary transition-colors py-2"
            >
              Workflow
            </button>
            <button
              onClick={handleOpenNationalMap}
              className="font-title-sm text-sm text-secondary hover:text-primary transition-colors py-2 flex items-center gap-1.5 font-semibold"
            >
              <span className="w-2 h-2 rounded-full bg-secondary animate-pulse" />
              <span>National Map</span>
            </button>
          </nav>

          <div className="flex items-center gap-3">
            <button
              onClick={onSignIn}
              className="inline-flex items-center justify-center h-9 px-4 rounded-lg font-title-sm text-sm font-semibold text-primary hover:bg-surface-container-low transition-colors border border-outline-variant/60"
            >
              Sign In
            </button>
            <button
              onClick={handleOpenNationalMap}
              className="inline-flex items-center justify-center h-9 px-4 rounded-lg font-title-sm text-sm font-semibold bg-primary-container text-white border border-secondary-fixed/50 hover:bg-primary transition-all shadow-[0_2px_8px_rgba(0,98,163,0.18)]"
            >
              Explore Platform
            </button>
          </div>
        </div>
      </header>

      {/* MAIN CONTENT */}
      <main
        className="w-full pt-8 min-h-screen"
        style={{
          background:
            'radial-gradient(ellipse at 50% 0%, rgba(2, 132, 199, 0.16) 0%, transparent 60%), radial-gradient(ellipse at 80% 50%, rgba(0, 106, 97, 0.08) 0%, transparent 50%), transparent',
        }}
      >
        <div className="flex flex-col w-full">
          {/* Top Ambient Glow Aura */}
          <div className="relative w-full overflow-hidden">
            <div
              className="absolute top-0 left-1/2 -translate-x-1/2 w-[1200px] h-[480px] blur-3xl pointer-events-none -z-10"
              style={{
                background:
                  'radial-gradient(circle, rgba(14, 165, 233, 0.28) 0%, rgba(0, 98, 163, 0.15) 45%, transparent 75%)',
              }}
            ></div>

            {/* 1. HERO SECTION */}
            <section className="max-w-7xl mx-auto px-4 lg:px-8 pt-6 pb-12" id="platform">
              <div className="flex flex-col items-center text-center max-w-4xl mx-auto">
                {/* Eyebrow Pill */}
                <div className="inline-flex items-center gap-2.5 px-3.5 py-1.5 rounded-full bg-surface-container-low shadow-sm mb-6 border border-outline-variant/30">
                  <span className="relative flex h-2 w-2">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-secondary opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-secondary"></span>
                  </span>
                  <span className="font-label-sm text-xs font-semibold tracking-wider text-secondary uppercase">
                    Genomic Intelligence Platform • Next-Gen Clinical Decision Support
                  </span>
                </div>

                {/* Main Title */}
                <h1 className="font-display-lg text-4xl lg:text-5xl font-bold text-on-surface tracking-tight mb-5 max-w-3xl leading-tight">
                  From Genomic Data to{' '}
                  <span className="text-primary italic font-editorial-accent font-normal">
                    Clinical Intelligence.
                  </span>
                </h1>

                {/* Supporting Text */}
                <p className="font-body-lg text-base lg:text-lg text-on-surface-variant max-w-2xl mb-8 leading-relaxed">
                  Genomera brings genomic data, phenotypes, evidence, and explainable intelligence together
                  to help researchers and clinical teams explore complex genomic cases with mathematical rigor.
                </p>

                {/* CTA Row */}
                <div className="flex flex-wrap items-center justify-center gap-4 mb-12">
                  <button
                    onClick={onSignIn}
                    className="inline-flex items-center justify-center gap-2 px-6 h-12 rounded-lg font-title-sm text-sm font-semibold bg-primary text-white shadow-[0_4px_16px_rgba(0,74,124,0.24)] hover:bg-primary-container transition-all"
                  >
                    <span className="material-symbols-outlined text-[18px]">biotech</span>
                    Explore Genomera
                  </button>
                  <button
                    onClick={handleOpenNationalMap}
                    className="inline-flex items-center justify-center gap-2 px-6 h-12 rounded-lg font-title-sm text-sm font-semibold bg-surface-container-lowest text-primary shadow-sm hover:bg-blue-50 border border-primary/30 transition-all ring-1 ring-primary/20"
                  >
                    <span className="material-symbols-outlined text-[18px]">map</span>
                    All-India Genomics Map
                  </button>
                  <button
                    onClick={() => scrollTo('workflow')}
                    className="inline-flex items-center justify-center gap-2 px-6 h-12 rounded-lg font-title-sm text-sm font-semibold bg-surface-container-lowest text-primary shadow-sm hover:bg-surface-container-low transition-all border border-outline-variant/40"
                  >
                    <span className="material-symbols-outlined text-[18px]">play_circle</span>
                    See How It Works
                  </button>
                </div>
              </div>

              {/* Master Workstation Visual Card */}
              <div className="relative w-full rounded-xl bg-surface-container-lowest shadow-xl overflow-hidden border border-outline-variant/30">
                {/* Visual Workstation Top Chrome */}
                <div className="w-full bg-surface-container-low px-4 py-2.5 flex items-center justify-between text-on-surface-variant border-b border-outline-variant/30">
                  <div className="flex items-center gap-4">
                    <div className="flex items-center gap-1.5">
                      <span className="w-2.5 h-2.5 rounded-full bg-outline-variant/60"></span>
                      <span className="w-2.5 h-2.5 rounded-full bg-outline-variant/60"></span>
                      <span className="w-2.5 h-2.5 rounded-full bg-outline-variant/60"></span>
                    </div>
                    <span className="font-label-sm text-xs text-on-surface font-semibold tracking-wide flex items-center gap-2 font-mono">
                      <span className="material-symbols-outlined text-[15px] text-primary">analytics</span>
                      ANALYSIS_VIEW // CHR17:q21.31 • BRCA1 REGION
                    </span>
                  </div>
                  <div className="flex items-center gap-4">
                    <span className="font-label-sm text-xs text-secondary px-2 py-0.5 rounded bg-secondary-container/20 font-semibold font-mono">
                      ACMG CLASS 1 PATHOGENIC
                    </span>
                    <span className="font-label-sm text-xs text-on-surface-variant font-medium font-mono hidden sm:inline">
                      CONCORDANCE: 99.4%
                    </span>
                  </div>
                </div>

                {/* Visual Media Canvas */}
                <div className="relative w-full h-[360px] lg:h-[500px] bg-inverse-surface overflow-hidden">
                  <img
                    alt="High-Resolution Genomic Sequence Analysis and Protein Structure Modeling"
                    className="w-full h-full object-cover opacity-95"
                    src="https://lh3.googleusercontent.com/aida-public/AB6AXuCCRFvNy_pdOw80pVP_YQGLnNXCDtD-yqsCZV5vLOWipvzDker8VnOkduqBpRgo3lQcafN_22z4s5W8SZhN6eqxnxQZpkgJTqe04wvXhpKPcez-0GsYOi0T1JIb06sa0dtOPXwAUgwtePJlOYiflSrY1oN7IPvqPChGjcxJQGs0ucJYQkIDMBvpBSVYjS5aBMfV3teYREaxID2lMWND8Q9qgDLkmVTNWIH4R3c4HMSfLduAUKJjX-jE"
                  />
                  {/* Scientific Glass Overlay Bar */}
                  <div className="absolute bottom-4 left-4 right-4 lg:bottom-6 lg:left-6 lg:right-6 p-4 rounded-lg bg-surface-container-lowest/90 backdrop-blur-md shadow-md flex flex-wrap items-center justify-between gap-4 border border-outline-variant/30">
                    <div className="flex items-center gap-6">
                      <div className="flex flex-col">
                        <span className="font-label-sm text-[11px] text-outline uppercase font-semibold">
                          Target Cytoband
                        </span>
                        <span className="font-title-sm text-xs lg:text-sm text-on-surface font-mono font-semibold">
                          17q21.31 [43,044,295..43,125,482]
                        </span>
                      </div>
                      <div className="h-8 w-[1px] bg-outline-variant/30 hidden sm:block"></div>
                      <div className="flex flex-col">
                        <span className="font-label-sm text-[11px] text-outline uppercase font-semibold">
                          Variant Call
                        </span>
                        <span className="font-title-sm text-xs lg:text-sm text-primary font-mono font-semibold">
                          NM_007294.4:c.5266dupC
                        </span>
                      </div>
                      <div className="h-8 w-[1px] bg-outline-variant/30 hidden md:block"></div>
                      <div className="flex flex-col hidden md:flex">
                        <span className="font-label-sm text-[11px] text-outline uppercase font-semibold">
                          Read Depth / Quality
                        </span>
                        <span className="font-title-sm text-xs lg:text-sm text-on-surface font-mono">
                          148x • Q42 Validated
                        </span>
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <div className="flex items-center gap-1.5 px-3 py-1 rounded bg-secondary-container/30 text-secondary font-label-sm text-xs font-semibold">
                        <span className="material-symbols-outlined text-[15px]">verified</span>
                        CLIA-CAP AUDITED
                      </div>
                      <button
                        onClick={onSignIn}
                        className="px-3.5 py-1.5 rounded bg-primary text-white font-title-sm text-xs font-semibold flex items-center gap-1.5 hover:bg-primary-container transition-colors shadow-sm"
                      >
                        <span className="material-symbols-outlined text-[16px]">visibility</span>
                        Inspect Variant
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            </section>
          </div>

          {/* 2. CAPABILITY STRIP */}
          <section
            className="w-full py-8"
            style={{
              background: 'linear-gradient(180deg, rgba(186, 222, 248, 0.6) 0%, rgba(175, 215, 245, 0.45) 100%)',
              borderTop: '1px solid rgba(147, 204, 255, 0.4)',
              borderBottom: '1px solid rgba(147, 204, 255, 0.4)',
            }}
          >
            <div className="max-w-7xl mx-auto px-4 lg:px-8">
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-6">
                <h2 className="font-title-md text-base lg:text-lg text-on-surface font-semibold">
                  Built for the complexity of modern genomic medicine.
                </h2>
                <span className="font-label-sm text-xs text-outline uppercase tracking-wider font-semibold">
                  6 Core Functional Layers
                </span>
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
                {[
                  { icon: 'strikethrough_s', title: 'Variant Intel', sub: 'ACMG Classification', color: 'text-primary' },
                  { icon: 'clinical_notes', title: 'Phenotype Analysis', sub: 'HPO Ontology', color: 'text-secondary' },
                  { icon: 'hub', title: 'Knowledge Graph', sub: 'Graph Traversal', color: 'text-primary-container' },
                  { icon: 'psychology', title: 'Explainable AI', sub: 'Decision Weights', color: 'text-tertiary' },
                  { icon: 'menu_book', title: 'Evidence Intel', sub: 'PubMed/ClinVar', color: 'text-secondary' },
                  { icon: 'assignment_turned_in', title: 'Clinical Reports', sub: 'Audit Trail Export', color: 'text-primary' },
                ].map((item, idx) => (
                  <div
                    key={idx}
                    className="p-3.5 rounded-lg bg-surface-container-lowest shadow-sm hover:shadow-md transition-shadow flex items-center gap-3 border border-outline-variant/30"
                  >
                    <div className={`w-8 h-8 rounded bg-surface-container flex items-center justify-center ${item.color}`}>
                      <span className="material-symbols-outlined text-[18px]">{item.icon}</span>
                    </div>
                    <div className="flex flex-col min-w-0">
                      <span className="font-title-sm text-xs font-semibold text-on-surface truncate">
                        {item.title}
                      </span>
                      <span className="font-label-sm text-[11px] text-on-surface-variant truncate">
                        {item.sub}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </section>

          {/* 3. WORKFLOW PIPELINE */}
          <section className="max-w-7xl mx-auto px-4 lg:px-8 py-14" id="workflow">
            <div className="flex flex-col mb-10">
              <div className="flex items-center gap-2 mb-2">
                <span className="w-1.5 h-4 bg-primary rounded-full"></span>
                <span className="font-label-sm text-xs font-semibold text-primary uppercase tracking-widest">
                  Unified Diagnostics
                </span>
              </div>
              <h2 className="font-headline-lg text-2xl lg:text-3xl text-on-surface font-bold">
                One Intelligence Layer for the Genomic Journey
              </h2>
              <p className="font-body-md text-sm text-on-surface-variant max-w-2xl mt-1">
                Seamless transition from unstructured clinical intake through deep variant calling and contextual decision delivery.
              </p>
            </div>

            {/* Pipeline Visual Track */}
            <div className="w-full bg-surface-container-lowest rounded-xl p-6 shadow-sm mb-8 border border-outline-variant/30">
              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
                {[
                  { step: '01', icon: 'person', title: 'Patient', desc: 'EHR & Pedigree ingestion, consent records', code: 'ID: #PX-9820' },
                  { step: '02', icon: 'assignment', title: 'Phenotype', desc: 'HPO ontology extraction & symptom weighting', code: 'HPO:0003002' },
                  { step: '03', icon: 'grain', title: 'Genomic Data', desc: 'VCF/BAM processing, sequencing QC filters', code: 'GRCh38.p14' },
                  { step: '04', icon: 'neurology', title: 'AI Analysis', desc: 'Graph neural traversal, pathogenic scoring', code: 'Scored: 0.9984' },
                  { step: '05', icon: 'auto_stories', title: 'Evidence', desc: 'ClinVar, COSMIC, gnomAD & PubMed mining', code: 'Tier 1 Matched' },
                  { step: '06', icon: 'verified_user', title: 'Clinical Intel', desc: 'Explainable diagnostic synthesis ready for sign-off', code: 'Actionable Plan' },
                ].map((s, idx) => (
                  <div
                    key={idx}
                    className="flex flex-col p-4 rounded-lg bg-surface-container-low hover:bg-surface-container-high transition-colors border border-outline-variant/20"
                  >
                    <div className="flex items-center justify-between mb-3">
                      <span className="font-label-sm text-xs font-bold text-primary font-mono">{s.step}</span>
                      <span className="material-symbols-outlined text-[18px] text-on-surface-variant">{s.icon}</span>
                    </div>
                    <span className="font-title-sm text-sm text-on-surface font-semibold mb-1">{s.title}</span>
                    <span className="font-body-sm text-xs text-on-surface-variant flex-1">{s.desc}</span>
                    <span className="mt-3 font-label-sm text-[11px] text-secondary font-mono font-semibold">{s.code}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Laboratory Context Banner Card */}
            <div className="w-full rounded-xl bg-surface-container-lowest p-6 shadow-sm flex flex-col lg:flex-row items-center gap-8 border border-outline-variant/30">
              <div className="w-full lg:w-1/2 h-64 lg:h-80 rounded-lg overflow-hidden relative shadow-sm">
                <img
                  alt="Clinical laboratory team reviewing molecular genomic arrays"
                  className="w-full h-full object-cover"
                  src="https://lh3.googleusercontent.com/aida-public/AB6AXuCiSLBMUBqyhIJ4CR9yFroyATF0hD8TH-_P4B9kcEDjWWZOED9TZdU6xonSuB8DVyDlKn1OnZ_P5Yck6mk0ioIGjRXHBYrWuTJwz0U2NpxZU6uwmpG9ggrV_XBtVt6oGYfqPIFOQL4qd_-tX7eukOSs6igCRR-8m5GmuE_eDoykW2qXvzOAo0kG5AHdyffwXjNwNcUoljV9viny6mds10Te_FNUrx69b4kZpjlgUidM_8hk-tYzQE1B"
                />
                <div className="absolute inset-0 bg-gradient-to-t from-inverse-surface/80 via-transparent to-transparent flex items-end p-4">
                  <span className="font-label-sm text-xs text-white font-mono font-semibold">
                    CLINICAL AUTOMATION • NEXT-GEN SEQUENCING SUITE
                  </span>
                </div>
              </div>
              <div className="w-full lg:w-1/2 flex flex-col justify-center">
                <span className="font-label-sm text-xs text-secondary font-semibold uppercase tracking-wider mb-2">
                  Automated High-Throughput Curation
                </span>
                <h3 className="font-headline-sm text-xl lg:text-2xl text-on-surface font-bold mb-3">
                  Bridging wet-lab automation with real-time computational inference.
                </h3>
                <p className="font-body-md text-sm text-on-surface-variant mb-6 leading-relaxed">
                  Genomera synchronizes directly with major sequencer runs (Illumina, PacBio, Oxford Nanopore),
                  standardizing secondary and tertiary pipeline outputs into audit-ready clinical decisions without human interpretation lag.
                </p>
                <div className="grid grid-cols-2 gap-4">
                  <div className="p-3.5 rounded-lg bg-surface-container-low flex flex-col border border-outline-variant/30">
                    <span className="font-headline-sm text-xl font-bold text-primary font-mono">&lt; 14m</span>
                    <span className="font-body-sm text-xs text-on-surface-variant">Full genome graph traversal and prioritization</span>
                  </div>
                  <div className="p-3.5 rounded-lg bg-surface-container-low flex flex-col border border-outline-variant/30">
                    <span className="font-headline-sm text-xl font-bold text-secondary font-mono">100%</span>
                    <span className="font-body-sm text-xs text-on-surface-variant">Deterministic ACMG evidence audit trails</span>
                  </div>
                </div>
              </div>
            </div>
          </section>

          {/* 4. PREMIUM CAPABILITY GRID */}
          <section
            className="w-full py-14"
            id="capabilities"
            style={{
              background: 'linear-gradient(180deg, rgba(180, 218, 248, 0.45) 0%, rgba(195, 227, 252, 0.55) 50%, rgba(185, 222, 250, 0.4) 100%)',
              borderTop: '1px solid rgba(160, 210, 250, 0.35)',
              borderBottom: '1px solid rgba(160, 210, 250, 0.35)',
            }}
          >
            <div className="max-w-7xl mx-auto px-4 lg:px-8">
              <div className="flex flex-col text-center max-w-2xl mx-auto mb-12">
                <span className="font-label-sm text-xs text-primary font-semibold uppercase tracking-widest mb-2">
                  Core Computational Capabilities
                </span>
                <h2 className="font-headline-lg text-2xl lg:text-3xl text-on-surface font-bold">
                  Engineered for absolute clinical precision.
                </h2>
                <p className="font-body-md text-sm text-on-surface-variant mt-2">
                  Transparent, modular modules built to support certified geneticists in multi-gene oncology, rare disorders, and pharmacogenomics.
                </p>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {[
                  { icon: 'strikethrough_s', color: 'text-primary', title: 'Genomic Intelligence', desc: 'Explore variants, genes, diseases, and genomic relationships with zero ambiguity. Compute missense pathogenicity and structural breakpoint impacts in real time.', tag: 'SNV • INDEL • CNV • SV' },
                  { icon: 'medical_information', color: 'text-secondary', title: 'Phenotype Intelligence', desc: 'Transform clinical observations into structured phenotype insights. Advanced NLP extracts human phenotype ontology (HPO) terms directly from physician consultation notes.', tag: 'HPO • OMIM • Orphanet' },
                  { icon: 'share', color: 'text-primary-container', title: 'Knowledge Graph', desc: 'Traverse interconnected biological vectors linking genes, diseases, variants, phenotypes, and drug interactions across 40M+ synthesized peer-reviewed papers.', tag: '4.8B Relations • GraphDB' },
                  { icon: 'fact_check', color: 'text-tertiary', title: 'Explainable AI', desc: 'Understand exactly why specific genes, diseases, or variants are prioritized. Detailed mathematical attribution charts break down every contribution to the diagnostic score.', tag: 'SHAP • Integrated Gradients' },
                  { icon: 'find_in_page', color: 'text-secondary', title: 'Evidence Intelligence', desc: 'Real-time synchronization with PubMed, ClinVar, gnomAD, and active clinical trials. Continuously re-score variants whenever novel literature or functional assays emerge.', tag: 'Daily PubMed Synchronization' },
                  { icon: 'description', color: 'text-primary', title: 'Clinical Reporting', desc: 'Transform intricate bioinformatic outputs into standardized, signed, and certified diagnostic reports compliant with ACMG guidelines and EHR HL7/FHIR protocols.', tag: 'PDF Export • HL7 • FHIR v4' },
                ].map((c, idx) => (
                  <div
                    key={idx}
                    className="p-6 rounded-xl bg-surface-container-lowest shadow-sm hover:shadow-lg transition-all flex flex-col justify-between border border-outline-variant/30"
                  >
                    <div>
                      <div className={`w-10 h-10 rounded-lg bg-surface-container flex items-center justify-center ${c.color} mb-4`}>
                        <span className="material-symbols-outlined text-[22px]">{c.icon}</span>
                      </div>
                      <h3 className="font-title-md text-base text-on-surface font-semibold mb-2">{c.title}</h3>
                      <p className="font-body-md text-sm text-on-surface-variant mb-4 leading-relaxed">{c.desc}</p>
                    </div>
                    <div className="pt-4 flex items-center justify-between border-t border-outline-variant/20">
                      <span className="font-label-sm text-xs font-mono text-secondary font-semibold">{c.tag}</span>
                      <button onClick={onSignIn} className="text-primary hover:translate-x-1 transition-transform">
                        <span className="material-symbols-outlined text-[18px]">arrow_forward</span>
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </section>

          {/* 5. GENOMERA AI ASSISTANT */}
          <section className="max-w-7xl mx-auto px-4 lg:px-8 py-14" id="assistant">
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-center">
              <div className="lg:col-span-5 flex flex-col">
                <div className="flex items-center gap-2 mb-2">
                  <span className="w-1.5 h-4 bg-secondary rounded-full"></span>
                  <span className="font-label-sm text-xs font-semibold text-secondary uppercase tracking-widest">
                    Decision Support
                  </span>
                </div>
                <h2 className="font-headline-lg text-2xl lg:text-3xl text-on-surface font-bold mb-4">
                  Your Genomic Intelligence Assistant
                </h2>
                <p className="font-body-lg text-base text-on-surface-variant mb-6 leading-relaxed">
                  Ask complex genomic questions in natural language and explore cases, variants, genes, diseases,
                  phenotypes, and evidence through a contextual AI assistant.
                </p>

                {/* Clickable Sample Prompts */}
                <div className="flex flex-col gap-2 mb-6">
                  <span className="font-label-sm text-xs text-outline uppercase font-semibold">Suggested queries:</span>
                  <div className="flex flex-wrap gap-2">
                    {[
                      'Explain this variant.',
                      'Why is this gene relevant?',
                      'Which phenotype supports this diagnosis?',
                      'Show the evidence behind this ranking.',
                    ].map((prompt, idx) => (
                      <button
                        key={idx}
                        onClick={onSignIn}
                        className="px-3 py-1.5 rounded-lg bg-surface-container-low text-primary font-body-sm text-xs hover:bg-surface-container-high transition-colors text-left flex items-center gap-1.5 border border-outline-variant/30"
                      >
                        <span className="material-symbols-outlined text-[15px]">search</span>
                        "{prompt}"
                      </button>
                    ))}
                  </div>
                </div>

                <div className="p-4 rounded-lg bg-surface-container-low text-on-surface-variant flex items-center gap-3 border border-outline-variant/30">
                  <span className="material-symbols-outlined text-secondary text-[24px]">lock</span>
                  <span className="font-body-sm text-xs leading-relaxed">
                    Zero training on PHI. Fully isolated HIPAA-compliant inference environment with deterministic citation tracing.
                  </span>
                </div>
              </div>

              {/* High-Fidelity Assistant Chat Interface */}
              <div className="lg:col-span-7 rounded-xl bg-surface-container-lowest shadow-xl overflow-hidden border border-outline-variant/30">
                {/* Assistant Top Bar */}
                <div className="bg-surface-container-low p-4 flex items-center justify-between border-b border-outline-variant/30">
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-full bg-primary-container text-white flex items-center justify-center font-bold text-sm">
                      <span className="material-symbols-outlined text-[18px]">smart_toy</span>
                    </div>
                    <div className="flex flex-col">
                      <span className="font-title-sm text-sm text-on-surface font-semibold">Genomera AI Assistant</span>
                      <span className="font-label-sm text-[11px] text-secondary font-medium flex items-center gap-1 font-mono">
                        <span className="w-1.5 h-1.5 rounded-full bg-secondary"></span>
                        Active Clinical Session • Ref: Case-4912
                      </span>
                    </div>
                  </div>
                  <span className="font-label-sm text-xs text-outline font-mono">MODEL: CLIN-V3</span>
                </div>

                {/* Chat History */}
                <div className="p-6 flex flex-col gap-5 max-h-[440px] overflow-y-auto">
                  {/* User message */}
                  <div className="flex flex-col items-end">
                    <div className="bg-primary text-white px-4 py-2.5 rounded-xl rounded-tr-none max-w-lg shadow-sm">
                      <p className="font-body-md text-sm">Why was this variant ranked first?</p>
                    </div>
                    <span className="font-label-sm text-[11px] text-outline mt-1 font-mono">11:42 AM • Dr. A. Vance</span>
                  </div>

                  {/* Assistant response */}
                  <div className="flex flex-col items-start">
                    <div className="bg-surface-container-low text-on-surface p-5 rounded-xl rounded-tl-none max-w-xl shadow-sm border border-outline-variant/30">
                      <p className="font-body-md text-sm mb-3 leading-relaxed">
                        This variant (<span className="font-mono font-semibold text-primary">NM_007294.4:c.5266dupC</span> in{' '}
                        <span className="font-semibold">BRCA1</span>) has the strongest overall evidence based on the available
                        phenotype (<span className="text-on-surface font-semibold">early-onset bilateral breast carcinoma, HPO:0003002</span>),
                        autosomal dominant maternal inheritance context, population allele frequency (&lt;0.0001 in gnomAD v4),
                        and ACMG/AMP Pathogenicity signals (PVS1, PM2, PP3).
                      </p>
                      {/* Evidence Pills */}
                      <div className="pt-2 flex flex-wrap gap-2">
                        <span className="font-label-sm text-[11px] px-2.5 py-1 rounded bg-surface-container text-primary font-mono font-semibold flex items-center gap-1 shadow-sm">
                          <span className="material-symbols-outlined text-[13px]">dataset</span>
                          ClinVar: VCV000017662
                        </span>
                        <span className="font-label-sm text-[11px] px-2.5 py-1 rounded bg-surface-container text-secondary font-mono font-semibold flex items-center gap-1 shadow-sm">
                          <span className="material-symbols-outlined text-[13px]">tune</span>
                          gnomAD AF: 0.00003
                        </span>
                        <span className="font-label-sm text-[11px] px-2.5 py-1 rounded bg-surface-container text-tertiary font-mono font-semibold flex items-center gap-1 shadow-sm">
                          <span className="material-symbols-outlined text-[13px]">article</span>
                          PubMed: 28492532
                        </span>
                      </div>
                    </div>
                    <span className="font-label-sm text-[11px] text-outline mt-1 font-mono">
                      11:42 AM • Genomera Verified Reasoning
                    </span>
                  </div>
                </div>

                {/* Chat Input */}
                <div className="p-4 bg-surface-container-lowest flex items-center gap-3 border-t border-outline-variant/30">
                  <input
                    readOnly
                    className="flex-1 h-11 px-4 rounded-lg bg-surface-container-low text-on-surface font-body-md text-sm focus:outline-none border border-outline-variant/30"
                    placeholder="Ask a question about this variant or phenotype..."
                    type="text"
                    value="Synthesize the maternal inheritance pedigree correlation..."
                  />
                  <button
                    onClick={onSignIn}
                    className="w-11 h-11 rounded-lg bg-primary text-white flex items-center justify-center hover:bg-primary-container transition-colors shadow-sm"
                  >
                    <span className="material-symbols-outlined text-[20px]">send</span>
                  </button>
                </div>
              </div>
            </div>
          </section>

          {/* 6. COMPUTATIONAL TWIN */}
          <section
            className="w-full py-14"
            id="digital-twin"
            style={{
              background: 'linear-gradient(180deg, rgba(176, 216, 247, 0.5) 0%, rgba(190, 225, 252, 0.6) 100%)',
              borderTop: '1px solid rgba(147, 204, 255, 0.35)',
              borderBottom: '1px solid rgba(147, 204, 255, 0.35)',
            }}
          >
            <div className="max-w-7xl mx-auto px-4 lg:px-8">
              <div className="flex flex-col lg:flex-row items-start lg:items-end justify-between gap-6 mb-10">
                <div className="max-w-2xl">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="w-1.5 h-4 bg-primary rounded-full"></span>
                    <span className="font-label-sm text-xs font-semibold text-primary uppercase tracking-widest">
                      In-Silico Modeling
                    </span>
                  </div>
                  <h2 className="font-headline-lg text-2xl lg:text-3xl text-on-surface font-bold">
                    A Computational Twin of the Patient
                  </h2>
                  <p className="font-body-lg text-base text-on-surface-variant mt-2">
                    Bring phenotype, genotype, variants, genes, diseases, and evidence into a unified computational
                    representation for exploration and scenario analysis.
                  </p>
                </div>
                <button
                  onClick={onSignIn}
                  className="px-5 h-11 rounded-lg bg-primary text-white font-title-sm text-sm font-semibold inline-flex items-center gap-2 hover:bg-primary-container transition-colors shadow-md"
                >
                  <span className="material-symbols-outlined text-[18px]">account_tree</span>
                  Explore Digital Twin
                </button>
              </div>

              {/* Computational Twin Diagnostic Console */}
              <div className="w-full rounded-xl bg-surface-container-lowest shadow-xl overflow-hidden border border-outline-variant/30">
                {/* Channel Ribbon */}
                <div className="p-4 bg-surface-container-low flex flex-wrap items-center justify-between gap-2 border-b border-outline-variant/30">
                  <span className="font-label-sm text-xs text-outline uppercase font-semibold">Channel Continuity:</span>
                  <div className="flex items-center gap-2 overflow-x-auto text-on-surface-variant font-label-sm text-xs font-mono">
                    <span className="px-2.5 py-1 rounded bg-surface-container-lowest font-medium text-on-surface">Patient</span>
                    <span className="material-symbols-outlined text-[14px]">arrow_forward</span>
                    <span className="px-2.5 py-1 rounded bg-surface-container-lowest font-medium text-on-surface">Phenotype</span>
                    <span className="material-symbols-outlined text-[14px]">arrow_forward</span>
                    <span className="px-2.5 py-1 rounded bg-surface-container-lowest font-medium text-on-surface">Genotype</span>
                    <span className="material-symbols-outlined text-[14px]">arrow_forward</span>
                    <span className="px-2.5 py-1 rounded bg-surface-container-lowest font-medium text-primary font-semibold">Variants</span>
                    <span className="material-symbols-outlined text-[14px]">arrow_forward</span>
                    <span className="px-2.5 py-1 rounded bg-surface-container-lowest font-medium text-secondary font-semibold">Genes</span>
                    <span className="material-symbols-outlined text-[14px]">arrow_forward</span>
                    <span className="px-2.5 py-1 rounded bg-secondary-container/40 text-secondary font-semibold">Evidence</span>
                  </div>
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-12">
                  <div className="lg:col-span-8 relative h-[320px] lg:h-[440px] bg-inverse-surface">
                    <img
                      alt="Computational Patient Digital Twin with Bio-Computational Network Map"
                      className="w-full h-full object-cover"
                      src="https://lh3.googleusercontent.com/aida-public/AB6AXuDG4ReXycfZhFg6Y34iLhsZJ7bRjCAnW_eNNYOqdEX06i_UYezzC6PfjyXgnKJ0zhChJkvmJtgE6qNOPxzXalT7x_RPS8emV4NzjOeyFBKiBN0HY84zPxrQJRHiLB6bMIgTRpY19SG16R3duk0uu_JBZqILQxyjAzsIEz-YDAZLpi_YPI-6PxQ5b5dhcpei4p9FQQV8vVGgAOCdt6uDI_3d9q6YzsVMOYYkb7lECkwiu2I_IesyuPAQ"
                    />
                    <div className="absolute top-4 left-4 p-2.5 rounded bg-surface-container-lowest/90 backdrop-blur-md shadow-sm border border-outline-variant/30">
                      <span className="font-label-sm text-xs font-mono text-primary font-bold">
                        TWIN_INSTANCE // BIO-GRAPH v4.1 ACTIVE
                      </span>
                    </div>
                  </div>

                  <div className="lg:col-span-4 p-6 bg-surface-container-lowest flex flex-col justify-between border-t lg:border-t-0 lg:border-l border-outline-variant/30">
                    <div className="flex flex-col gap-5">
                      <div className="flex items-center justify-between">
                        <span className="font-title-sm text-sm text-on-surface font-semibold">Phenotypic Alignment</span>
                        <span className="font-label-sm text-xs font-mono text-secondary font-semibold">97.8% Confidence</span>
                      </div>
                      <div>
                        <div className="flex justify-between text-xs text-on-surface-variant mb-1">
                          <span>Hereditary Breast &amp; Ovarian Cancer</span>
                          <span className="font-mono text-primary font-semibold">0.96</span>
                        </div>
                        <div className="w-full h-2 rounded-full bg-surface-container-low overflow-hidden">
                          <div className="h-full bg-primary rounded-full w-[96%]"></div>
                        </div>
                      </div>
                      <div>
                        <div className="flex justify-between text-xs text-on-surface-variant mb-1">
                          <span>Fanconi Anemia Complement D1</span>
                          <span className="font-mono text-outline font-semibold">0.14</span>
                        </div>
                        <div className="w-full h-2 rounded-full bg-surface-container-low overflow-hidden">
                          <div className="h-full bg-outline rounded-full w-[14%]"></div>
                        </div>
                      </div>
                      <div className="p-3.5 rounded-lg bg-surface-container-low border border-outline-variant/30">
                        <span className="font-label-sm text-[11px] text-outline uppercase font-semibold block mb-1">
                          Metabolic In-Silico Impact
                        </span>
                        <p className="font-body-sm text-xs text-on-surface leading-relaxed">
                          Pathways simulation predicts double-strand DNA repair pathway inhibition at 84% knockdown equivalent.
                        </p>
                      </div>
                    </div>
                    <div className="pt-4 flex items-center justify-between">
                      <span className="font-label-sm text-xs text-outline font-mono">SIMULATION_TRIAL: #082</span>
                      <button onClick={onSignIn} className="font-title-sm text-xs font-semibold text-primary hover:underline flex items-center gap-1">
                        Run Perturbation Test
                        <span className="material-symbols-outlined text-[16px]">play_arrow</span>
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </section>

          {/* 7. KNOWLEDGE GRAPH */}
          <section
            className="max-w-7xl mx-auto px-4 lg:px-8 py-14"
            style={{
              background: 'linear-gradient(180deg, rgba(184, 220, 250, 0.45) 0%, rgba(170, 212, 245, 0.55) 100%)',
              borderTop: '1px solid rgba(147, 204, 255, 0.35)',
              borderBottom: '1px solid rgba(147, 204, 255, 0.35)',
            }}
          >
            <div className="flex flex-col text-center max-w-2xl mx-auto mb-10">
              <div className="inline-flex items-center justify-center gap-2 mb-2">
                <span className="w-1.5 h-4 bg-primary-container rounded-full"></span>
                <span className="font-label-sm text-xs font-semibold text-primary uppercase tracking-widest">
                  Relational Discovery
                </span>
              </div>
              <h2 className="font-headline-lg text-2xl lg:text-3xl text-on-surface font-bold">
                Connect the Relationships Hidden Inside Genomic Data.
              </h2>
              <p className="font-body-md text-sm text-on-surface-variant mt-2">
                Explore high-dimensional graph neural networks navigating millions of clinical evidence bridges simultaneously.
              </p>
            </div>

            {/* SVG Graph Representation */}
            <div className="w-full rounded-xl bg-surface-container-lowest p-6 shadow-sm overflow-hidden relative border border-outline-variant/30">
              <div className="w-full h-[360px] flex items-center justify-center relative">
                <svg className="w-full h-full text-on-surface" fill="none" viewBox="0 0 800 400" xmlns="http://www.w3.org/2000/svg">
                  <line className="opacity-60" stroke="#c1c7d2" strokeDasharray="4 4" strokeWidth="1.5" x1="400" x2="220" y1="200" y2="100" />
                  <line stroke="#0062a3" strokeWidth="2" x1="400" x2="580" y1="200" y2="100" />
                  <line stroke="#006a61" strokeWidth="2" x1="400" x2="160" y1="200" y2="230" />
                  <line stroke="#004b74" strokeWidth="2" x1="400" x2="640" y1="200" y2="220" />
                  <line stroke="#c1c7d2" strokeWidth="1.5" x1="400" x2="280" y1="200" y2="330" />
                  <line stroke="#006a61" strokeWidth="2" x1="400" x2="520" y1="200" y2="330" />

                  <rect fill="#e5eeff" height="18" rx="3" width="80" x="460" y="135" />
                  <text fill="#004a7c" fontFamily="JetBrains Mono" fontSize="9" fontWeight="600" textAnchor="middle" x="500" y="148">Expressed In</text>
                  <rect fill="#e5eeff" height="18" rx="3" width="80" x="250" y="195" />
                  <text fill="#006a61" fontFamily="JetBrains Mono" fontSize="9" fontWeight="600" textAnchor="middle" x="290" y="208">Associated With</text>
                  <rect fill="#e5eeff" height="18" rx="3" width="86" x="480" y="275" />
                  <text fill="#004b74" fontFamily="JetBrains Mono" fontSize="9" fontWeight="600" textAnchor="middle" x="523" y="288">Downregulates</text>

                  <circle cx="400" cy="200" fill="#004a7c" r="42" />
                  <circle className="animate-pulse" cx="400" cy="200" opacity="0.4" r="48" stroke="#0062a3" strokeWidth="2" />
                  <text fill="#ffffff" fontFamily="Inter" fontSize="12" fontWeight="bold" textAnchor="middle" x="400" y="196">PATIENT</text>
                  <text fill="#9dcaff" fontFamily="JetBrains Mono" fontSize="9" textAnchor="middle" x="400" y="210">PX-9820</text>

                  <circle cx="220" cy="100" fill="#f0f5fc" r="32" stroke="#c1c7d2" strokeWidth="1.5" />
                  <text fill="#001c37" fontFamily="Inter" fontSize="11" fontWeight="600" textAnchor="middle" x="220" y="98">Phenotypes</text>
                  <text fill="#006a61" fontFamily="JetBrains Mono" fontSize="8" textAnchor="middle" x="220" y="112">4 Match</text>

                  <circle cx="580" cy="100" fill="#f0f5fc" r="34" stroke="#0062a3" strokeWidth="2" />
                  <text fill="#004a7c" fontFamily="Inter" fontSize="11" fontWeight="bold" textAnchor="middle" x="580" y="98">BRCA1</text>
                  <text fill="#0062a3" fontFamily="JetBrains Mono" fontSize="8" textAnchor="middle" x="580" y="112">Score: 0.99</text>

                  <circle cx="160" cy="230" fill="#f0f5fc" r="32" stroke="#006a61" strokeWidth="2" />
                  <text fill="#001c37" fontFamily="Inter" fontSize="11" fontWeight="600" textAnchor="middle" x="160" y="228">Variants</text>
                  <text fill="#006a61" fontFamily="JetBrains Mono" fontSize="8" textAnchor="middle" x="160" y="242">Pathogenic</text>

                  <circle cx="640" cy="220" fill="#f0f5fc" r="32" stroke="#004b74" strokeWidth="1.5" />
                  <text fill="#001c37" fontFamily="Inter" fontSize="11" fontWeight="600" textAnchor="middle" x="640" y="218">Diseases</text>
                  <text fill="#004b74" fontFamily="JetBrains Mono" fontSize="8" textAnchor="middle" x="640" y="232">HBOC</text>

                  <circle cx="280" cy="330" fill="#f0f5fc" r="30" stroke="#c1c7d2" strokeWidth="1.5" />
                  <text fill="#001c37" fontFamily="Inter" fontSize="10" fontWeight="600" textAnchor="middle" x="280" y="328">Literature</text>
                  <text fill="#717781" fontFamily="JetBrains Mono" fontSize="8" textAnchor="middle" x="280" y="342">14 Papers</text>

                  <circle cx="520" cy="330" fill="#f0f5fc" r="32" stroke="#006a61" strokeWidth="2" />
                  <text fill="#001c37" fontFamily="Inter" fontSize="11" fontWeight="600" textAnchor="middle" x="520" y="328">Evidence</text>
                  <text fill="#006a61" fontFamily="JetBrains Mono" fontSize="8" textAnchor="middle" x="520" y="342">Tier 1 Val</text>
                </svg>
              </div>
            </div>
          </section>

          {/* 8. RESEARCH & CLINICAL SECTION */}
          <section className="max-w-7xl mx-auto px-4 lg:px-8 py-14" id="research">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
              <div className="p-8 rounded-xl bg-surface-container-lowest shadow-sm flex flex-col justify-between border border-outline-variant/30">
                <div>
                  <div className="flex items-center gap-3 mb-4">
                    <div className="w-10 h-10 rounded-lg bg-surface-container flex items-center justify-center text-primary">
                      <span className="material-symbols-outlined text-[22px]">stethoscope</span>
                    </div>
                    <div>
                      <span className="font-label-sm text-xs text-outline uppercase font-semibold">Healthcare Institutions</span>
                      <h3 className="font-headline-sm text-lg font-bold text-on-surface">For Clinical Teams</h3>
                    </div>
                  </div>
                  <p className="font-body-md text-sm text-on-surface-variant mb-6 leading-relaxed">
                    Explore complex genomic cases with structured evidence and explainable intelligence. Accelerate molecular tumor boards,
                    shorten turnaround time for rare genetic diseases, and minimize variant curation backlogs.
                  </p>
                  <ul className="flex flex-col gap-2.5 mb-6 text-on-surface font-body-sm text-xs">
                    <li className="flex items-center gap-2">
                      <span className="material-symbols-outlined text-secondary text-[16px]">check_circle</span>
                      ACMG / AMP / CAP automated guideline adherence
                    </li>
                    <li className="flex items-center gap-2">
                      <span className="material-symbols-outlined text-secondary text-[16px]">check_circle</span>
                      EHR-integrated patient case history synthesis
                    </li>
                    <li className="flex items-center gap-2">
                      <span className="material-symbols-outlined text-secondary text-[16px]">check_circle</span>
                      Explainable variant ranking for clinical geneticists
                    </li>
                  </ul>
                </div>
                <button onClick={onSignIn} className="font-title-sm text-sm text-primary hover:underline inline-flex items-center gap-1.5 font-semibold text-left">
                  Sign in to clinical console
                  <span className="material-symbols-outlined text-[16px]">arrow_forward</span>
                </button>
              </div>

              <div className="p-8 rounded-xl bg-surface-container-lowest shadow-sm flex flex-col justify-between border border-outline-variant/30">
                <div>
                  <div className="flex items-center gap-3 mb-4">
                    <div className="w-10 h-10 rounded-lg bg-surface-container flex items-center justify-center text-secondary">
                      <span className="material-symbols-outlined text-[22px]">biotech</span>
                    </div>
                    <div>
                      <span className="font-label-sm text-xs text-outline uppercase font-semibold">Biotech &amp; Academia</span>
                      <h3 className="font-headline-sm text-lg font-bold text-on-surface">For Researchers</h3>
                    </div>
                  </div>
                  <p className="font-body-md text-sm text-on-surface-variant mb-6 leading-relaxed">
                    Connect genomic data, phenotypes, literature, and computational analysis across cohorts. Query millions of patient profiles
                    safely in-silico to uncover novel disease-gene associations.
                  </p>
                  <ul className="flex flex-col gap-2.5 mb-6 text-on-surface font-body-sm text-xs">
                    <li className="flex items-center gap-2">
                      <span className="material-symbols-outlined text-secondary text-[16px]">check_circle</span>
                      Large-scale multi-sample cohort exploration
                    </li>
                    <li className="flex items-center gap-2">
                      <span className="material-symbols-outlined text-secondary text-[16px]">check_circle</span>
                      Multi-hop heterogeneous graph traversal
                    </li>
                    <li className="flex items-center gap-2">
                      <span className="material-symbols-outlined text-secondary text-[16px]">check_circle</span>
                      Novel biomarker and founder effect prediction
                    </li>
                  </ul>
                </div>
                <button onClick={onSignIn} className="font-title-sm text-sm text-secondary hover:underline inline-flex items-center gap-1.5 font-semibold text-left">
                  Access research workspace
                  <span className="material-symbols-outlined text-[16px]">arrow_forward</span>
                </button>
              </div>
            </div>
          </section>

          {/* 9. FINAL ELEVATED CTA SECTION */}
          <section className="max-w-7xl mx-auto px-4 lg:px-8 pb-16">
            <div className="w-full rounded-2xl bg-gradient-to-br from-primary via-primary-container to-tertiary-container p-8 lg:p-14 shadow-xl text-center text-white relative overflow-hidden">
              <div className="relative z-10 max-w-3xl mx-auto flex flex-col items-center">
                <span className="px-3.5 py-1 rounded-full bg-white/10 text-white font-label-sm text-xs font-semibold uppercase tracking-wider mb-6">
                  Next-Generation Diagnostic Precision
                </span>
                <h2 className="font-display-lg text-3xl lg:text-4xl font-bold tracking-tight mb-4 text-white">
                  Turn Genomic Complexity Into Clinical Clarity.
                </h2>
                <p className="font-body-lg text-base text-white/90 max-w-xl mb-8 leading-relaxed">
                  Explore a unified intelligence layer for genomic interpretation, evidence discovery, and explainable clinical reasoning.
                </p>
                <div className="flex flex-wrap items-center justify-center gap-4">
                  <button
                    onClick={onSignIn}
                    className="px-8 h-12 rounded-lg bg-surface-container-lowest text-primary font-title-sm text-sm font-semibold shadow-lg hover:bg-surface-container-low transition-all inline-flex items-center gap-2"
                  >
                    <span className="material-symbols-outlined text-[18px]">rocket_launch</span>
                    Explore Genomera
                  </button>
                  <button
                    onClick={onSignIn}
                    className="px-8 h-12 rounded-lg bg-primary-container/40 text-white border border-white/30 font-title-sm text-sm font-semibold hover:bg-primary-container/70 transition-all inline-flex items-center gap-2"
                  >
                    <span className="material-symbols-outlined text-[18px]">dashboard</span>
                    Sign In to Console
                  </button>
                </div>
              </div>
            </div>
          </section>
        </div>
      </main>

      {/* FOOTER */}
      <footer
        className="relative w-full border-t border-outline-variant/30 overflow-hidden"
        style={{
          background: 'linear-gradient(180deg, #cbe5f8 0%, #bddff7 100%)',
          borderTop: '1px solid rgba(0, 98, 163, 0.2)',
        }}
      >
        <div className="relative max-w-7xl mx-auto px-4 lg:px-8 py-12">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-12 gap-8 mb-10">
            <div className="lg:col-span-4 flex flex-col gap-2">
              <div className="flex items-center gap-2.5">
                <Logo size={28} />
                <span className="font-headline-sm text-lg font-bold tracking-tight text-on-surface">GENOMERA</span>
                <span className="font-label-sm text-[10px] font-semibold text-secondary uppercase bg-secondary-container/20 px-2 py-0.5 rounded">
                  CLINICAL
                </span>
              </div>
              <p className="font-editorial-accent text-sm italic text-primary">Genomic Intelligence, Reimagined.</p>
              <p className="font-body-md text-xs text-on-surface-variant max-w-sm mt-1">
                An intelligent platform for genomic interpretation, evidence discovery, and explainable clinical decision support.
              </p>
            </div>
            <div className="lg:col-span-8 grid grid-cols-2 sm:grid-cols-3 gap-6">
              <div className="flex flex-col gap-2">
                <span className="font-title-sm text-xs text-on-surface font-semibold uppercase tracking-wider">Platform</span>
                <button onClick={() => scrollTo('platform')} className="text-left font-body-sm text-xs text-on-surface-variant hover:text-primary transition-colors">Overview</button>
                <button onClick={() => scrollTo('capabilities')} className="text-left font-body-sm text-xs text-on-surface-variant hover:text-primary transition-colors">Genomic Engine</button>
                <button onClick={onSignIn} className="text-left font-body-sm text-xs text-on-surface-variant hover:text-primary transition-colors">Diagnostic Console</button>
              </div>
              <div className="flex flex-col gap-2">
                <span className="font-title-sm text-xs text-on-surface font-semibold uppercase tracking-wider">Intelligence</span>
                <button onClick={() => scrollTo('assistant')} className="text-left font-body-sm text-xs text-on-surface-variant hover:text-primary transition-colors">AI Assistant</button>
                <button onClick={() => scrollTo('digital-twin')} className="text-left font-body-sm text-xs text-on-surface-variant hover:text-primary transition-colors">Digital Twin</button>
                <button onClick={() => scrollTo('capabilities')} className="text-left font-body-sm text-xs text-on-surface-variant hover:text-primary transition-colors">Knowledge Graph</button>
              </div>
              <div className="flex flex-col gap-2">
                <span className="font-title-sm text-xs text-on-surface font-semibold uppercase tracking-wider">Compliance</span>
                <span className="font-body-sm text-xs text-on-surface-variant flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-secondary"></span>HIPAA Compliant</span>
                <span className="font-body-sm text-xs text-on-surface-variant flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-secondary"></span>CLIA / CAP Ready</span>
                <span className="font-body-sm text-xs text-on-surface-variant flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-secondary"></span>FHIR • HL7 Interoperable</span>
              </div>
            </div>
          </div>
          <div className="pt-6 border-t border-outline-variant/20 flex flex-col sm:flex-row items-center justify-between gap-4">
            <span className="font-label-sm text-xs text-on-surface-variant">
              © 2026 GENOMERA Clinical Intelligence System. All rights reserved.
            </span>
            <div className="flex items-center gap-6 font-body-sm text-xs text-on-surface-variant">
              <span>Privacy Policy</span>
              <span>Terms of Service</span>
              <span>Clinical Architecture</span>
            </div>
          </div>
        </div>
      </footer>
    </div>
  )
}
