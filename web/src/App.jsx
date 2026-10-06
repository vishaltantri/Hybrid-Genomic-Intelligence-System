import React, { Suspense, lazy, useEffect, useState } from 'react'
import { verifySession, getUser, logout } from './api.js'

// Components
import LandingPage from './components/LandingPage.jsx'
import LoginModal from './components/LoginModal.jsx'
import AppShell from './components/AppShell.jsx'
import ErrorBoundary from './components/ErrorBoundary.jsx'

// Existing Functional Views
const DiagnosisView = lazy(() => import('./views/DiagnosisView.jsx'))
const PgxView = lazy(() => import('./views/PgxView.jsx'))
const AnalyticsView = lazy(() => import('./views/AnalyticsView.jsx'))
const ReproView = lazy(() => import('./views/ReproView.jsx'))
const NationalView = lazy(() => import('./views/NationalView.jsx'))
const KgView = lazy(() => import('./views/KgView.jsx'))

// Enhanced & Connected Module Views
const OverviewView = lazy(() => import('./views/OverviewView.jsx'))
const PatientsView = lazy(() => import('./views/PatientsView.jsx'))
const PhenotypesView = lazy(() => import('./views/PhenotypesView.jsx'))
const AshaView = lazy(() => import('./views/AshaView.jsx'))
const FhirView = lazy(() => import('./views/FhirView.jsx'))
const ReportsView = lazy(() => import('./views/ReportsView.jsx'))
const SettingsView = lazy(() => import('./views/SettingsView.jsx'))
const VariantsView = lazy(() => import('./views/VariantsView.jsx'))
const AssistantView = lazy(() => import('./views/AssistantView.jsx'))
const DigitalTwinView = lazy(() => import('./views/DigitalTwinView.jsx'))
const PedigreeView = lazy(() => import('./views/PedigreeView.jsx'))
const EvidenceView = lazy(() => import('./views/EvidenceView.jsx'))
const ClinicalTextView = lazy(() => import('./views/ClinicalTextView.jsx'))
const DiagnosisIntelView = lazy(() => import('./views/DiagnosisIntelView.jsx'))
const DemoView = lazy(() => import('./views/DemoView.jsx'))

// Helper to extract initial route from hash or URL query parameter
function getInitialRoute() {
  if (typeof window === 'undefined') return 'overview'
  const hash = window.location.hash.replace(/^#\/?/, '').trim()
  if (hash) return hash
  const params = new URLSearchParams(window.location.search)
  return params.get('route') || params.get('view') || 'overview'
}

function ViewLoading() {
  return (
    <div role="status" aria-live="polite" className="p-8 flex items-center gap-3 text-sm text-primary">
      <span className="w-5 h-5 border-2 border-primary/20 border-t-primary rounded-full animate-spin" aria-hidden="true" />
      Loading module...
    </div>
  )
}

export default function App() {
  const [user, setUser] = useState(getUser())
  const [route, setRoute] = useState(getInitialRoute())
  const [showLoginModal, setShowLoginModal] = useState(false)
  const [initialLoading, setInitialLoading] = useState(true)
  const [pendingRoute, setPendingRoute] = useState(null)
  const [demoActive, setDemoActiveState] = useState(() => { try { return localStorage.getItem('genomera_demo_active') === '1' } catch { return false } })
  const [presentation, setPresentation] = useState(false)
  const setDemoActive = (v) => {
    setDemoActiveState(!!v)
    try { if (v) localStorage.setItem('genomera_demo_active', '1'); else localStorage.removeItem('genomera_demo_active') } catch { /* storage unavailable */ }
  }

  // Verify active JWT against /api/v1/auth/me on mount with strict timeout guard
  useEffect(() => {
    let done = false
    const timeout = setTimeout(() => {
      if (!done) {
        done = true
        setInitialLoading(false)
      }
    }, 1500)

    verifySession()
      .then((verifiedUser) => {
        if (verifiedUser) {
          setUser(verifiedUser)
        }
      })
      .finally(() => {
        if (!done) {
          done = true
          clearTimeout(timeout)
          setInitialLoading(false)
        }
      })
  }, [])

  // Keep route synced with browser window.location.hash
  useEffect(() => {
    const handleHash = () => {
      const h = window.location.hash.replace(/^#\/?/, '').trim()
      if (h) setRoute(h)
    }
    window.addEventListener('hashchange', handleHash)
    return () => window.removeEventListener('hashchange', handleHash)
  }, [])

  const handleNavigate = (newRoute) => {
    setRoute(newRoute)
    if (window.location.hash !== `#${newRoute}`) {
      window.location.hash = newRoute
    }
  }

  const handleLogout = () => {
    logout()
    setUser(null)
    handleNavigate('overview')
  }

  // Landing page shortcuts never sign anyone in: they open the normal sign-in and continue to the chosen module afterwards.
  const handleExploreDemo = (targetRoute = 'national') => {
    setPendingRoute(targetRoute)
    setShowLoginModal(true)
  }

  // Handle patient selection from PatientsView to auto-populate Diagnosis
  const handleSelectPatientForDiagnosis = (patient) => {
    handleNavigate('diagnosis')
  }

  // If initial auth check is ongoing, display a clean splash spinner
  if (initialLoading) {
    return (
      <div className="h-screen w-screen flex flex-col items-center justify-center bg-background text-on-surface">
        <div className="w-8 h-8 border-3 border-primary/20 border-t-primary rounded-full animate-spin mb-4"></div>
        <div className="text-xs font-semibold text-primary font-mono tracking-wider uppercase">
          Initializing Genomera Session...
        </div>
      </div>
    )
  }

  // Unauthenticated: Public Genomera Landing Page with Sign In modal & Quick Demo
  if (!user) {
    return (
      <>
        <LandingPage
          onSignIn={() => setShowLoginModal(true)}
          onExploreDemo={handleExploreDemo}
        />
        <LoginModal
          isOpen={showLoginModal}
          onClose={() => setShowLoginModal(false)}
          onSuccess={(authenticatedUser) => {
            setUser(authenticatedUser)
            setShowLoginModal(false)
            if (pendingRoute) { handleNavigate(pendingRoute); setPendingRoute(null) }
          }}
        />
      </>
    )
  }

  // Authenticated: Render active view inside Genomera AppShell
  const renderActiveView = () => {
    switch (route) {
      case 'overview':
        return <OverviewView onNavigate={handleNavigate} user={user} />
      case 'patients':
      case 'cases':
        return <PatientsView onSelectPatientForDiagnosis={handleSelectPatientForDiagnosis} />
      case 'phenotypes':
        return <PhenotypesView onNavigateToDiagnosis={(text) => handleNavigate('diagnosis')} />
      case 'clinical-text':
        return <ClinicalTextView onNavigate={handleNavigate} />
      case 'dx-intel':
        return <DiagnosisIntelView onNavigate={handleNavigate} />
      case 'diagnosis':
        return <DiagnosisView />
      case 'variants':
        return (
          <VariantsView
            onNavigateToDiagnosis={handleNavigate}
            onNavigateToKg={handleNavigate}
            onNavigateToReport={handleNavigate}
          />
        )
      case 'kg':
        return <KgView onNavigate={handleNavigate} />
      case 'pedigree':
        return <PedigreeView onNavigate={handleNavigate} />
      case 'digital-twin':
        return <DigitalTwinView onNavigate={handleNavigate} />
      case 'ai-assistant':
        return (
          <AssistantView
            onNavigateToDiagnosis={handleNavigate}
            onNavigateToVariants={handleNavigate}
            onNavigateToReport={handleNavigate}
          />
        )
      case 'evidence':
        return <EvidenceView onNavigate={handleNavigate} />
      case 'pgx':
        return <PgxView onNavigate={handleNavigate} />
      case 'repro':
        return <ReproView onNavigate={handleNavigate} />
      case 'analytics':
        return <AnalyticsView />
      case 'national':
        return <NationalView />
      case 'reports':
        return <ReportsView />
      case 'asha':
        return <AshaView />
      case 'fhir':
        return <FhirView />
      case 'demo':
        return (
          <DemoView onNavigate={handleNavigate} onDemoActive={setDemoActive}
            presentation={presentation} onPresentation={setPresentation} />
        )
      case 'settings':
        return <SettingsView user={user} />
      default:
        return <OverviewView onNavigate={handleNavigate} user={user} />
    }
  }

  return (
    <AppShell
      activeRoute={route}
      onRouteChange={handleNavigate}
      user={user}
      onLogout={handleLogout}
      demoActive={demoActive}
      onExitDemo={() => { setDemoActive(false); setPresentation(false) }}
      presentation={presentation}
      onPresentation={setPresentation}
    >
      <ErrorBoundary resetKey={route}>
        <Suspense fallback={<ViewLoading />}>
          {renderActiveView()}
        </Suspense>
      </ErrorBoundary>
    </AppShell>
  )
}
