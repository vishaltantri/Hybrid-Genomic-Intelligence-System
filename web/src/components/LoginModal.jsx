import React, { useState } from 'react'
import { login } from '../api.js'
import Logo from './Logo.jsx'

export default function LoginModal({ isOpen, onClose, onSuccess }) {
  const [username, setUsername] = useState('clinician')
  const [password, setPassword] = useState('changeme')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  if (!isOpen) return null

  const handleQuickFill = (user, pass) => {
    setUsername(user)
    setPassword(pass)
    setError(null)
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const user = await login(username, password)
      onSuccess(user)
    } catch (ex) {
      setError(ex.message || 'Invalid username or password')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm animate-in fade-in duration-200">
      <div
        className="w-full max-w-md bg-white rounded-2xl shadow-2xl overflow-hidden border border-outline-variant/40 animate-in zoom-in-95 duration-200"
        role="dialog"
        aria-modal="true"
      >
        {/* Header */}
        <div className="bg-gradient-to-r from-primary to-primary-container p-6 text-white relative">
          <button
            onClick={onClose}
            className="absolute top-5 right-5 text-white/80 hover:text-white transition-colors"
            aria-label="Close"
          >
            <span className="material-symbols-outlined text-[20px]">close</span>
          </button>
          <div className="flex items-center gap-3 mb-2">
            <Logo size={36} className="shadow-xs shrink-0" />
            <div>
              <h2 className="text-xl font-bold font-headline-sm leading-tight">Sign in to Genomera</h2>
              <p className="text-xs text-white/80 font-label-sm uppercase tracking-wider">Clinical Intelligence Console</p>
            </div>
          </div>
        </div>

        {/* Form Body */}
        <form onSubmit={handleSubmit} className="p-6">
          {error && (
            <div className="mb-5 p-3 rounded-lg bg-red-50 border border-red-200 text-red-700 text-xs flex items-center gap-2">
              <span className="material-symbols-outlined text-[16px] text-red-600">error</span>
              <span>{error}</span>
            </div>
          )}

          <div className="mb-4">
            <label className="block text-xs font-semibold text-on-surface-variant mb-1.5 uppercase tracking-wider">
              Username
            </label>
            <input
              type="text"
              required
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full h-11 px-3.5 rounded-lg border border-outline-variant/60 focus:border-primary focus:ring-2 focus:ring-primary/20 outline-none text-sm font-body-md"
              placeholder="e.g. clinician"
              autoFocus
            />
          </div>

          <div className="mb-5">
            <label className="block text-xs font-semibold text-on-surface-variant mb-1.5 uppercase tracking-wider">
              Password
            </label>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full h-11 px-3.5 rounded-lg border border-outline-variant/60 focus:border-primary focus:ring-2 focus:ring-primary/20 outline-none text-sm font-body-md"
              placeholder="••••••••"
            />
          </div>

          {/* Quick Demo Credentials */}
          <div className="mb-6 p-3.5 rounded-xl bg-surface-container-low border border-outline-variant/30">
            <div className="flex items-center justify-between mb-2">
              <span className="text-[11px] font-semibold text-on-surface-variant uppercase tracking-wider">
                Demo Accounts (Click to Fill):
              </span>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => handleQuickFill('clinician', 'changeme')}
                className={`px-2.5 py-1 rounded-md text-xs font-semibold transition-all ${
                  username === 'clinician'
                    ? 'bg-primary text-white shadow-sm'
                    : 'bg-white text-primary border border-outline-variant/40 hover:bg-primary/5'
                }`}
              >
                Doctor / Clinician
              </button>
              <button
                type="button"
                onClick={() => handleQuickFill('admin', 'admin-password-change-me')}
                className={`px-2.5 py-1 rounded-md text-xs font-semibold transition-all ${
                  username === 'admin'
                    ? 'bg-primary text-white shadow-sm'
                    : 'bg-white text-primary border border-outline-variant/40 hover:bg-primary/5'
                }`}
              >
                Administrator
              </button>
              <button
                type="button"
                onClick={() => handleQuickFill('asha1', 'changeme')}
                className={`px-2.5 py-1 rounded-md text-xs font-semibold transition-all ${
                  username === 'asha1'
                    ? 'bg-primary text-white shadow-sm'
                    : 'bg-white text-primary border border-outline-variant/40 hover:bg-primary/5'
                }`}
              >
                ASHA Worker
              </button>
            </div>
          </div>

          {/* Action Buttons */}
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 h-11 rounded-lg border border-outline-variant/60 text-on-surface font-title-sm text-sm font-semibold hover:bg-surface-container-low transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={busy}
              className="flex-1 h-11 rounded-lg bg-primary text-white font-title-sm text-sm font-semibold hover:bg-primary-container transition-all shadow-[0_2px_8px_rgba(0,74,124,0.25)] flex items-center justify-center gap-2 disabled:opacity-60"
            >
              {busy ? (
                <>
                  <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></span>
                  <span>Authenticating...</span>
                </>
              ) : (
                <>
                  <span>Sign In</span>
                  <span className="material-symbols-outlined text-[16px]">arrow_forward</span>
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
