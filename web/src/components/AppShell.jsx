import React, { useState, useEffect } from 'react'
import Sidebar, { NAVIGATION_SECTIONS } from './Sidebar.jsx'
import TopBar from './TopBar.jsx'
import { GlobalSearchModal } from './ui/GlobalSearchModal.jsx'

export default function AppShell({
  activeRoute,
  onRouteChange,
  user,
  onLogout,
  demoActive = false,
  onExitDemo,
  presentation = false,
  onPresentation,
  children,
}) {
  const [collapsed, setCollapsed] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const [searchOpen, setSearchOpen] = useState(false)

  // Listen for Cmd+K / Ctrl+K keyboard shortcut
  useEffect(() => {
    const handleKeyDown = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        setSearchOpen((prev) => !prev)
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [])

  // Presentation mode uses real full-screen where the browser allows it; leaving full-screen leaves the mode.
  useEffect(() => {
    if (presentation && document.fullscreenEnabled && !document.fullscreenElement) {
      document.documentElement.requestFullscreen?.().catch(() => { /* still presentable without full-screen */ })
    }
    if (!presentation && document.fullscreenElement) document.exitFullscreen?.().catch(() => {})
  }, [presentation])
  useEffect(() => {
    const onFs = () => { if (!document.fullscreenElement && presentation) onPresentation?.(false) }
    document.addEventListener('fullscreenchange', onFs)
    return () => document.removeEventListener('fullscreenchange', onFs)
  }, [presentation, onPresentation])

  // Find active title and section
  let activeTitle = 'Overview'
  let categoryTitle = 'WORKSPACE'

  for (const section of NAVIGATION_SECTIONS) {
    const found = section.items.find((item) => item.id === activeRoute)
    if (found) {
      activeTitle = found.label
      categoryTitle = section.title
      break
    }
  }

  return (
    <div className="flex flex-col h-screen w-full overflow-hidden bg-background">
      {demoActive && (
        <div role="status" className="shrink-0 flex flex-wrap items-center justify-between gap-2 px-4 py-1.5 bg-amber-100 border-b border-amber-300 text-amber-900 text-xs font-semibold">
          <span>Sample record — not a real patient. Not for clinical use.</span>
          <span className="flex gap-2">
            {presentation && <button type="button" onClick={() => onPresentation?.(false)} className="underline">Exit presentation</button>}
            <button type="button" onClick={onExitDemo} className="underline">Close guided case</button>
          </span>
        </div>
      )}
      <div className="flex flex-1 min-h-0 w-full overflow-hidden">
      <a href="#main-content" onClick={(e) => { e.preventDefault(); document.getElementById('main-content')?.focus() }}
        className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-[100] focus:px-3 focus:py-2 focus:rounded-lg focus:bg-white focus:text-primary focus:shadow-lg">
        Skip to main content
      </a>
      {/* Sidebar (Desktop + Mobile Drawer) */}
      {!presentation && <Sidebar
        activeRoute={activeRoute}
        onRouteChange={onRouteChange}
        collapsed={collapsed}
        onToggleCollapse={() => setCollapsed(!collapsed)}
        mobileOpen={mobileOpen}
        onMobileClose={() => setMobileOpen(false)}
        user={user}
        onLogout={onLogout}
      />}

      {/* Main View Area */}
      <div className="flex-1 flex flex-col min-w-0 h-full overflow-hidden">
        {/* Reusable Header */}
        {!presentation && <TopBar
          activeTitle={activeTitle}
          categoryTitle={categoryTitle}
          onMobileMenuOpen={() => setMobileOpen(true)}
          onOpenSearch={() => setSearchOpen(true)}
          user={user}
          onLogout={onLogout}
        />}

        {/* Scrollable Content Container */}
        <main id="main-content" tabIndex={-1} aria-label={activeTitle} className="flex-1 overflow-y-auto p-4 lg:p-8 focus:outline-none">
          <div className="max-w-7xl mx-auto">{children}</div>
        </main>
      </div>

      {/* Global Search Modal */}
      <GlobalSearchModal
        isOpen={searchOpen}
        onClose={() => setSearchOpen(false)}
        onNavigate={(route) => {
          setSearchOpen(false)
          onRouteChange(route)
        }}
      />
      </div>
    </div>
  )
}
