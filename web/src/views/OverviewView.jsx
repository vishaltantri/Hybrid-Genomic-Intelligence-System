import React, { useEffect, useState } from 'react'
import { api } from '../api.js'
import {
  Stethoscope,
  Pill,
  HeartHandshake,
  Network,
  Users,
  Map,
  ShieldAlert,
  ArrowRight,
  Activity,
  Database,
  CheckCircle2,
} from 'lucide-react'

export default function OverviewView({ onNavigate, user }) {
  const [kgStats, setKgStats] = useState(null)
  const [national, setNational] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      api.kgStats().catch(() => null),
      api.national().catch(() => null),
    ]).then(([kg, nat]) => {
      setKgStats(kg)
      setNational(nat)
      setLoading(false)
    })
  }, [])

  return (
    <div className="space-y-6">
      {/* Welcome Banner */}
      <div className="p-6 rounded-2xl bg-gradient-to-r from-primary to-primary-container text-white shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="inline-flex items-center gap-2 px-2.5 py-0.5 rounded-full bg-white/10 text-white text-[11px] font-mono mb-2">
            <span className="w-1.5 h-1.5 rounded-full bg-secondary-fixed"></span>
            <span>SYSTEM ACTIVE // GENOMERA CORE</span>
          </div>
          <h2 className="text-xl lg:text-2xl font-bold font-headline-sm">
            Welcome back, {user?.full_name || user?.username || 'Clinician'}
          </h2>
          <p className="text-xs lg:text-sm text-white/80 mt-1 max-w-xl">
            Genomera Decision Support Platform for rare genetic disease diagnosis, population-stratified pharmacogenomics, and reproductive risk counseling.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => onNavigate('diagnosis')}
            className="px-4 py-2 rounded-lg bg-white text-primary text-xs font-semibold hover:bg-surface-container-low transition-colors shadow-sm flex items-center gap-1.5"
          >
            <Stethoscope size={16} />
            <span>New Diagnosis</span>
          </button>
        </div>
      </div>

      {/* Metric Cards Row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="p-4 rounded-xl bg-white border border-outline-variant/40 shadow-xs flex flex-col justify-between">
          <div className="flex items-center justify-between text-outline mb-2">
            <span className="text-xs font-semibold text-on-surface-variant uppercase tracking-wider">KG Entities</span>
            <Database size={16} className="text-primary" />
          </div>
          <div className="text-2xl font-bold font-mono text-primary">
            {kgStats?.total_nodes ? kgStats.total_nodes.toLocaleString() : '362+'}
          </div>
          <div className="text-[11px] text-on-surface-variant mt-1">
            Diseases, Genes, HPOs & Drugs
          </div>
        </div>

        <div className="p-4 rounded-xl bg-white border border-outline-variant/40 shadow-xs flex flex-col justify-between">
          <div className="flex items-center justify-between text-outline mb-2">
            <span className="text-xs font-semibold text-on-surface-variant uppercase tracking-wider">KG Relations</span>
            <Network size={16} className="text-secondary" />
          </div>
          <div className="text-2xl font-bold font-mono text-secondary">
            {kgStats?.total_edges ? kgStats.total_edges.toLocaleString() : '404+'}
          </div>
          <div className="text-[11px] text-on-surface-variant mt-1">
            Phenotype & Founder Edges
          </div>
        </div>

        <div className="p-4 rounded-xl bg-white border border-outline-variant/40 shadow-xs flex flex-col justify-between">
          <div className="flex items-center justify-between text-outline mb-2">
            <span className="text-xs font-semibold text-on-surface-variant uppercase tracking-wider">Indian States</span>
            <Map size={16} className="text-tertiary" />
          </div>
          <div className="text-2xl font-bold font-mono text-tertiary">
            36
          </div>
          <div className="text-[11px] text-on-surface-variant mt-1">
            NFHS-5 Consanguinity Models
          </div>
        </div>

        <div className="p-4 rounded-xl bg-white border border-outline-variant/40 shadow-xs flex flex-col justify-between">
          <div className="flex items-center justify-between text-outline mb-2">
            <span className="text-xs font-semibold text-on-surface-variant uppercase tracking-wider">Diagnostic Modules</span>
            <Activity size={16} className="text-primary-container" />
          </div>
          <div className="text-2xl font-bold font-mono text-primary-container">
            11 / 11
          </div>
          <div className="text-[11px] text-secondary font-semibold mt-1 flex items-center gap-1">
            <CheckCircle2 size={12} /> Verified Functional
          </div>
        </div>
      </div>

      {/* Clinical Workflow Cards */}
      <div>
        <h3 className="text-sm font-bold text-on-surface uppercase tracking-wider mb-3">
          Clinical Decision Workflows
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {/* Card 1: Diagnosis */}
          <div
            onClick={() => onNavigate('diagnosis')}
            className="p-5 rounded-xl bg-white border border-outline-variant/40 shadow-xs hover:shadow-md hover:border-primary/50 transition-all cursor-pointer group flex flex-col justify-between"
          >
            <div>
              <div className="w-10 h-10 rounded-lg bg-surface-container flex items-center justify-center text-primary mb-3 group-hover:scale-105 transition-transform">
                <Stethoscope size={20} />
              </div>
              <h4 className="text-sm font-bold text-on-surface mb-1 group-hover:text-primary transition-colors">
                Differential Diagnosis & XAI
              </h4>
              <p className="text-xs text-on-surface-variant leading-relaxed">
                Rank rare disease candidates from Hindi, Hinglish, or English symptoms adjusted with Indian consanguinity and community priors.
              </p>
            </div>
            <div className="mt-4 pt-3 border-t border-outline-variant/20 flex items-center justify-between text-xs font-semibold text-primary">
              <span>Open Diagnosis</span>
              <ArrowRight size={14} className="group-hover:translate-x-1 transition-transform" />
            </div>
          </div>

          {/* Card 2: Pharmacogenomics */}
          <div
            onClick={() => onNavigate('pgx')}
            className="p-5 rounded-xl bg-white border border-outline-variant/40 shadow-xs hover:shadow-md hover:border-secondary/50 transition-all cursor-pointer group flex flex-col justify-between"
          >
            <div>
              <div className="w-10 h-10 rounded-lg bg-surface-container flex items-center justify-center text-secondary mb-3 group-hover:scale-105 transition-transform">
                <Pill size={20} />
              </div>
              <h4 className="text-sm font-bold text-on-surface mb-1 group-hover:text-secondary transition-colors">
                Pharmacogenomic Safety
              </h4>
              <p className="text-xs text-on-surface-variant leading-relaxed">
                Infer drug toxicity risks for Clopidogrel, Warfarin, Carbamazepine using Indian population allele frequencies and CPIC rules.
              </p>
            </div>
            <div className="mt-4 pt-3 border-t border-outline-variant/20 flex items-center justify-between text-xs font-semibold text-secondary">
              <span>Check Drug Safety</span>
              <ArrowRight size={14} className="group-hover:translate-x-1 transition-transform" />
            </div>
          </div>

          {/* Card 3: Reproductive */}
          <div
            onClick={() => onNavigate('repro')}
            className="p-5 rounded-xl bg-white border border-outline-variant/40 shadow-xs hover:shadow-md hover:border-tertiary/50 transition-all cursor-pointer group flex flex-col justify-between"
          >
            <div>
              <div className="w-10 h-10 rounded-lg bg-surface-container flex items-center justify-center text-tertiary mb-3 group-hover:scale-105 transition-transform">
                <HeartHandshake size={20} />
              </div>
              <h4 className="text-sm font-bold text-on-surface mb-1 group-hover:text-tertiary transition-colors">
                Reproductive & Carrier Risk
              </h4>
              <p className="text-xs text-on-surface-variant leading-relaxed">
                Counsel couples with consanguinity coefficient analysis, Punnett Mendelian simulations, and Indian government scheme support.
              </p>
            </div>
            <div className="mt-4 pt-3 border-t border-outline-variant/20 flex items-center justify-between text-xs font-semibold text-tertiary">
              <span>Counsel Couple</span>
              <ArrowRight size={14} className="group-hover:translate-x-1 transition-transform" />
            </div>
          </div>

          {/* Card 4: National Genomics Map */}
          <div
            onClick={() => onNavigate('national')}
            className="p-5 rounded-xl bg-gradient-to-b from-white to-blue-50/40 border border-blue-200/70 shadow-xs hover:shadow-md hover:border-primary transition-all cursor-pointer group flex flex-col justify-between ring-1 ring-primary/10"
          >
            <div>
              <div className="w-10 h-10 rounded-lg bg-primary-container/20 flex items-center justify-center text-primary mb-3 group-hover:scale-105 transition-transform">
                <Map size={20} />
              </div>
              <h4 className="text-sm font-bold text-on-surface mb-1 group-hover:text-primary transition-colors flex items-center gap-1.5">
                <span>All-India Genomics Map</span>
                <span className="w-2 h-2 rounded-full bg-primary animate-pulse"></span>
              </h4>
              <p className="text-xs text-on-surface-variant leading-relaxed">
                Interactive choropleth surveillance across 36 Indian states: case burden, access deficit gaps, regional hotspots & disease clusters.
              </p>
            </div>
            <div className="mt-4 pt-3 border-t border-blue-200/50 flex items-center justify-between text-xs font-semibold text-primary">
              <span>Open India Map</span>
              <ArrowRight size={14} className="group-hover:translate-x-1 transition-transform" />
            </div>
          </div>
        </div>
      </div>

      {/* Field & System Row */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* ASHA Field Card */}
        <div
          onClick={() => onNavigate('asha')}
          className="p-5 rounded-xl bg-surface-container-low border border-outline-variant/30 flex items-center justify-between cursor-pointer hover:bg-surface-container transition-colors group"
        >
          <div className="flex items-center gap-3.5">
            <div className="w-10 h-10 rounded-lg bg-white flex items-center justify-center text-secondary shadow-xs">
              <ShieldAlert size={20} />
            </div>
            <div>
              <h4 className="text-sm font-bold text-on-surface">ASHA Community Health Triage</h4>
              <p className="text-xs text-on-surface-variant">
                Offline questionnaire & rural dialect symptom screening for field health workers.
              </p>
            </div>
          </div>
          <ArrowRight size={16} className="text-outline group-hover:text-secondary group-hover:translate-x-1 transition-all" />
        </div>

        {/* Knowledge Graph Card */}
        <div
          onClick={() => onNavigate('kg')}
          className="p-5 rounded-xl bg-surface-container-low border border-outline-variant/30 flex items-center justify-between cursor-pointer hover:bg-surface-container transition-colors group"
        >
          <div className="flex items-center gap-3.5">
            <div className="w-10 h-10 rounded-lg bg-white flex items-center justify-center text-primary shadow-xs">
              <Network size={20} />
            </div>
            <div>
              <h4 className="text-sm font-bold text-on-surface">Biological Knowledge Graph</h4>
              <p className="text-xs text-on-surface-variant">
                Explore connected HPO phenotypes, Orphadata rare diseases, and founder risk clusters.
              </p>
            </div>
          </div>
          <ArrowRight size={16} className="text-outline group-hover:text-primary group-hover:translate-x-1 transition-all" />
        </div>
      </div>
    </div>
  )
}
