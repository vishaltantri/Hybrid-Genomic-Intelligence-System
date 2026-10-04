import React from 'react'
import Logo from './Logo.jsx'
import {
  LayoutDashboard,
  Users,
  FolderKanban,
  FileText,
  Stethoscope,
  Dna,
  Network,
  Cpu,
  Bot,
  BookOpen,
  Pill,
  HeartHandshake,
  Map,
  FileCheck,
  ShieldAlert,
  Server,
  Settings,
  ChevronLeft,
  ChevronRight,
  LogOut,
  X,
} from 'lucide-react'

export const NAVIGATION_SECTIONS = [
  {
    title: 'WORKSPACE',
    items: [
      { id: 'overview', label: 'Overview', icon: LayoutDashboard },
      { id: 'patients', label: 'Patients', icon: Users },
      { id: 'cases', label: 'Cases', icon: FolderKanban },
    ],
  },
  {
    title: 'CLINICAL INTELLIGENCE',
    items: [
      { id: 'phenotypes', label: 'Phenotypes', icon: FileText },
      { id: 'diagnosis', label: 'Diagnosis', icon: Stethoscope },
      { id: 'variants', label: 'Variants', icon: Dna, badge: 'Phase 2' },
      { id: 'kg', label: 'Knowledge Graph', icon: Network },
    ],
  },
  {
    title: 'ADVANCED',
    items: [
      { id: 'digital-twin', label: 'Digital Twin', icon: Cpu, badge: 'Phase 4' },
      { id: 'ai-assistant', label: 'AI Assistant', icon: Bot, badge: 'Phase 3' },
      { id: 'evidence', label: 'Evidence', icon: BookOpen, badge: 'Phase 2' },
    ],
  },
  {
    title: 'CLINICAL TOOLS',
    items: [
      { id: 'pgx', label: 'Pharmacogenomics', icon: Pill },
      { id: 'repro', label: 'Reproductive', icon: HeartHandshake },
    ],
  },
  {
    title: 'NATIONAL INSIGHTS',
    items: [
      { id: 'national', label: 'National View', icon: Map },
    ],
  },
  {
    title: 'OUTPUT',
    items: [
      { id: 'reports', label: 'Reports', icon: FileCheck },
    ],
  },
  {
    title: 'FIELD / INTEGRATION',
    items: [
      { id: 'asha', label: 'ASHA Triage', icon: ShieldAlert },
      { id: 'fhir', label: 'FHIR / EMR', icon: Server },
    ],
  },
  {
    title: 'SYSTEM',
    items: [
      { id: 'settings', label: 'Settings & Status', icon: Settings },
    ],
  },
]

export default function Sidebar({
  activeRoute,
  onRouteChange,
  collapsed,
  onToggleCollapse,
  mobileOpen,
  onMobileClose,
  user,
  onLogout,
}) {
  return (
    <>
      {/* Mobile Backdrop */}
      {mobileOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm lg:hidden"
          onClick={onMobileClose}
          aria-hidden="true"
        />
      )}

      {/* Sidebar Container */}
      <aside
        className={`fixed top-0 bottom-0 left-0 z-50 flex flex-col bg-white border-r border-outline-variant/40 shadow-sm transition-all duration-300 ease-in-out lg:static ${
          collapsed ? 'w-20' : 'w-64'
        } ${mobileOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}`}
      >
        {/* Brand Header */}
        <div className="h-16 flex items-center justify-between px-4 border-b border-outline-variant/30 bg-surface-container-low/40">
          <div className="flex items-center gap-3 min-w-0">
            <Logo size={32} className="shrink-0" />
            {!collapsed && (
              <div className="flex flex-col min-w-0 overflow-hidden">
                <span className="font-headline-sm text-base font-bold text-on-surface truncate tracking-tight">
                  GENOMERA
                </span>
                <span className="font-label-sm text-[9px] font-semibold text-secondary uppercase tracking-wider truncate -mt-0.5">
                  CLINICAL CONSOLE
                </span>
              </div>
            )}
          </div>

          {/* Mobile close button */}
          <button
            onClick={onMobileClose}
            className="lg:hidden p-1.5 rounded-lg text-on-surface-variant hover:bg-surface-container-high transition-colors"
          >
            <X size={18} />
          </button>
        </div>

        {/* Navigation Items (Scrollable) */}
        <div className="flex-1 overflow-y-auto px-2.5 py-3 space-y-4">
          {NAVIGATION_SECTIONS.map((section, sIdx) => (
            <div key={sIdx} className="space-y-0.5">
              {!collapsed && (
                <div className="px-3 py-1 text-[10px] font-bold text-outline font-label-sm uppercase tracking-wider">
                  {section.title}
                </div>
              )}
              {collapsed && sIdx > 0 && (
                <div className="my-2 border-t border-outline-variant/30" />
              )}
              {section.items.map((item) => {
                const Icon = item.icon
                const isActive = activeRoute === item.id

                return (
                  <button
                    key={item.id}
                    onClick={() => {
                      onRouteChange(item.id)
                      if (onMobileClose) onMobileClose()
                    }}
                    title={collapsed ? item.label : undefined}
                    className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-xs font-semibold transition-all group ${
                      isActive
                        ? 'bg-primary text-white shadow-sm'
                        : 'text-on-surface-variant hover:bg-surface-container-low hover:text-primary'
                    } ${collapsed ? 'justify-center px-0' : ''}`}
                  >
                    <Icon
                      size={18}
                      className={`shrink-0 transition-colors ${
                        isActive
                          ? 'text-white'
                          : 'text-outline group-hover:text-primary'
                      }`}
                    />
                    {!collapsed && (
                      <span className="flex-1 text-left truncate">{item.label}</span>
                    )}
                    {!collapsed && item.badge && (
                      <span
                        className={`text-[9px] px-1.5 py-0.5 rounded font-mono font-medium ${
                          isActive
                            ? 'bg-white/20 text-white'
                            : 'bg-surface-container text-on-surface-variant'
                        }`}
                      >
                        {item.badge}
                      </span>
                    )}
                  </button>
                )
              })}
            </div>
          ))}
        </div>

        {/* Footer / User Profile & Collapse Toggle */}
        <div className="p-3 border-t border-outline-variant/30 bg-surface-container-lowest flex flex-col gap-2">
          {/* User profile row */}
          <div
            className={`flex items-center gap-2.5 p-2 rounded-xl bg-surface-container-low border border-outline-variant/30 ${
              collapsed ? 'justify-center p-1.5' : ''
            }`}
          >
            <div className="w-8 h-8 rounded-full bg-primary-container text-white flex items-center justify-center font-bold text-xs shrink-0">
              {user?.username ? user.username.charAt(0).toUpperCase() : 'U'}
            </div>
            {!collapsed && (
              <div className="flex-1 min-w-0">
                <div className="text-xs font-bold text-on-surface truncate">
                  {user?.full_name || user?.username || 'Clinician'}
                </div>
                <div className="text-[10px] text-secondary font-mono uppercase font-semibold truncate">
                  {user?.role || 'doctor'}
                </div>
              </div>
            )}
            {!collapsed && (
              <button
                onClick={onLogout}
                title="Sign out"
                className="p-1.5 rounded-lg text-outline hover:text-red-600 hover:bg-red-50 transition-colors"
              >
                <LogOut size={16} />
              </button>
            )}
          </div>

          {/* Desktop Collapse Toggle */}
          <button
            onClick={onToggleCollapse}
            className="hidden lg:flex w-full items-center justify-center gap-2 py-1.5 text-xs text-outline hover:text-primary hover:bg-surface-container-low rounded-lg transition-colors"
          >
            {collapsed ? (
              <ChevronRight size={16} />
            ) : (
              <>
                <ChevronLeft size={16} />
                <span className="font-label-sm text-[11px] font-medium">Collapse</span>
              </>
            )}
          </button>
        </div>
      </aside>
    </>
  )
}
