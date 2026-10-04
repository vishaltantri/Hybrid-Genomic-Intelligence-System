import React, { useState, useEffect } from 'react'
import Sidebar, { NAVIGATION_SECTIONS } from './Sidebar.jsx'
import TopBar from './TopBar.jsx'
import { GlobalSearchModal } from './ui/GlobalSearchModal.jsx'

export default function AppShell({
  activeRoute,
  onRouteChange,
  user,
  onLogout,
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
    <div className="flex h-screen w-screen overflow-hidden bg-background">
      {/* Sidebar (Desktop + Mobile Drawer) */}
      <Sidebar
        activeRoute={activeRoute}
        onRouteChange={onRouteChange}
        collapsed={collapsed}
        onToggleCollapse={() => setCollapsed(!collapsed)}
        mobileOpen={mobileOpen}
        onMobileClose={() => setMobileOpen(false)}
        user={user}
        onLogout={onLogout}
      />

      {/* Main View Area */}
      <div className="flex-1 flex flex-col min-w-0 h-full overflow-hidden">
        {/* Reusable Header */}
        <TopBar
          activeTitle={activeTitle}
          categoryTitle={categoryTitle}
          onMobileMenuOpen={() => setMobileOpen(true)}
          onOpenSearch={() => setSearchOpen(true)}
          user={user}
          onLogout={onLogout}
        />

        {/* Scrollable Content Container */}
        <main className="flex-1 overflow-y-auto p-4 lg:p-8">
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
  )
}
