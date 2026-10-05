import React from 'react'
import {
  Menu,
  Search,
  ShieldCheck,
  User,
  LogOut,
  Sparkles,
} from 'lucide-react'
import NotificationBell from './NotificationBell.jsx'

export default function TopBar({
  activeTitle,
  categoryTitle,
  onMobileMenuOpen,
  onOpenSearch,
  user,
  onLogout,
}) {
  return (
    <header className="h-16 bg-white border-b border-outline-variant/40 px-4 lg:px-8 flex items-center justify-between gap-4 sticky top-0 z-30 shadow-[0_1px_4px_rgba(0,28,55,0.02)]">
      {/* Left: Mobile Toggle & Breadcrumbs */}
      <div className="flex items-center gap-3 min-w-0">
        <button
          onClick={onMobileMenuOpen}
          className="lg:hidden p-2 rounded-lg text-on-surface-variant hover:bg-surface-container-high transition-colors"
          aria-label="Open Navigation"
        >
          <Menu size={20} />
        </button>

        <div className="flex items-center gap-2 min-w-0 text-xs">
          <span className="text-outline uppercase font-label-sm font-semibold tracking-wider hidden sm:inline truncate">
            {categoryTitle || 'WORKSPACE'}
          </span>
          <span className="text-outline-variant hidden sm:inline">/</span>
          <h1 className="font-headline-sm text-sm lg:text-base font-bold text-on-surface truncate">
            {activeTitle || 'Overview'}
          </h1>
        </div>
      </div>

      {/* Center: Global Search Bar Placeholder */}
      <div className="hidden md:flex items-center flex-1 max-w-md mx-4">
        <div
          onClick={onOpenSearch}
          className="relative w-full cursor-pointer group"
        >
          <Search
            size={16}
            className="absolute left-3.5 top-1/2 -translate-y-1/2 text-outline group-hover:text-primary transition-colors"
          />
          <input
            type="text"
            readOnly
            placeholder="Search cases, diseases, genes, phenotypes... (⌘K)"
            className="w-full h-9 pl-9 pr-12 rounded-lg bg-surface-container-low/70 border border-outline-variant/40 text-xs text-on-surface placeholder:text-outline focus:outline-none focus:border-primary/50 cursor-pointer pointer-events-none group-hover:border-primary/40 transition-colors"
          />
          <kbd className="absolute right-2.5 top-1/2 -translate-y-1/2 px-1.5 py-0.5 rounded bg-white text-[10px] font-mono text-outline border border-outline-variant/40 shadow-xs">
            ⌘K
          </kbd>
        </div>
      </div>

      {/* Right: Actions, Notifications & User Info */}
      <div className="flex items-center gap-3 shrink-0">
        {/* Compliance / Status Pill */}
        <div className="hidden xl:flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-secondary-container/20 text-secondary text-[11px] font-semibold border border-secondary/20">
          <ShieldCheck size={14} />
          <span>CLINICAL V1.0</span>
        </div>

        <NotificationBell />

        {/* User Badge */}
        <div className="flex items-center gap-2.5 pl-2 border-l border-outline-variant/30">
          <div className="flex flex-col text-right hidden sm:flex">
            <span className="text-xs font-bold text-on-surface leading-tight">
              {user?.full_name || user?.username || 'Clinician'}
            </span>
            <span className="text-[10px] font-mono uppercase font-semibold text-secondary">
              {user?.role || 'doctor'}
            </span>
          </div>

          <button
            onClick={onLogout}
            title="Sign out"
            className="p-1.5 rounded-lg text-outline hover:text-red-600 hover:bg-red-50 transition-colors"
          >
            <LogOut size={16} />
          </button>
        </div>
      </div>
    </header>
  )
}
