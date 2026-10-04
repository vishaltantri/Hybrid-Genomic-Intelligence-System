import React, { useEffect, useState } from 'react'
import { verifySession, getUser, logout } from './api.js'

// Components
import LandingPage from './components/LandingPage.jsx'
import LoginModal from './components/LoginModal.jsx'
import AppShell from './components/AppShell.jsx'

// Existing Functional Views
import DiagnosisView from './views/DiagnosisView.jsx'
import PgxView from './views/PgxView.jsx'
import ReproView from './views/ReproView.jsx'
import NationalView from './views/NationalView.jsx'
import KgView from './views/KgView.jsx'

// Enhanced & Connected Module Views
import OverviewView from './views/OverviewView.jsx'
import PatientsView from './views/PatientsView.jsx'
import PhenotypesView from './views/PhenotypesView.jsx'
import AshaView from './views/AshaView.jsx'
import FhirView from './views/FhirView.jsx'
import ReportsView from './views/ReportsView.jsx'
import SettingsView from './views/SettingsView.jsx'
import PlaceholderView from './views/PlaceholderView.jsx'

// Helper to extract initial route from hash or URL query parameter
function getInitialRoute() {
  if (typeof window === 'undefined') return 'overview'
  const hash = window.location.hash.replace(/^#\/?/, '').trim()
  if (hash) return hash
  const params = new URLSearchParams(window.location.search)
  return params.get('route') || params.get('view') || 'overview'
}

export default function App() {
  const [user, setUser] = useState(getUser())
  const [route, setRoute] = useState(getInitialRoute())
  const [showLoginModal, setShowLoginModal] = useState(false)
  const [initialLoading, setInitialLoading] = useState(true)

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

  // Quick demo launch from Landing Page (e.g. "All-India Genomics Map" or "Live Demo")
  const handleExploreDemo = async (targetRoute = 'national') => {
    try {
      // Auto-authenticate as demo clinician
      const demoUser = await login('clinician', 'changeme')
      setUser(demoUser)
      handleNavigate(targetRoute)
    } catch {
      setShowLoginModal(true)
    }
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
      case 'diagnosis':
        return <DiagnosisView />
      case 'variants':
        return <PlaceholderView moduleId="variants" onNavigateToDiagnosis={handleNavigate} />
      case 'kg':
        return <KgView />
      case 'digital-twin':
        return <PlaceholderView moduleId="digital-twin" onNavigateToDiagnosis={handleNavigate} />
      case 'ai-assistant':
        return <PlaceholderView moduleId="ai-assistant" onNavigateToDiagnosis={handleNavigate} />
      case 'evidence':
        return <PlaceholderView moduleId="evidence" onNavigateToDiagnosis={handleNavigate} />
      case 'pgx':
        return <PgxView />
      case 'repro':
        return <ReproView />
      case 'national':
        return <NationalView />
      case 'reports':
        return <ReportsView />
      case 'asha':
        return <AshaView />
      case 'fhir':
        return <FhirView />
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
    >
      {renderActiveView()}
    </AppShell>
  )
}
