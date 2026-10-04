import React, { useEffect, useState } from 'react'
import { api } from '../api.js'
import { Settings, Shield, Server, CheckCircle2, Database, Key } from 'lucide-react'

export default function SettingsView({ user }) {
  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.platformStatus()
      .then((data) => setStatus(data))
      .catch((ex) => setError(ex.message))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold font-headline-sm text-on-surface">Platform Settings & Engine Status</h2>
        <p className="text-xs text-on-surface-variant mt-0.5">
          Runtime infrastructure, service registry health, and active authentication session.
        </p>
      </div>

      {error && (
        <div className="p-3.5 rounded-lg bg-red-50 border border-red-200 text-red-700 text-xs">
          {error}
        </div>
      )}

      {/* Session Details */}
      <div className="panel">
        <h3>Authenticated Clinical Session</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
          <div className="p-3 rounded-lg bg-surface-container-low border border-outline-variant/30">
            <span className="text-outline uppercase text-[10px] font-semibold block mb-0.5">Username</span>
            <span className="font-bold text-on-surface font-mono">{user?.username || '—'}</span>
          </div>
          <div className="p-3 rounded-lg bg-surface-container-low border border-outline-variant/30">
            <span className="text-outline uppercase text-[10px] font-semibold block mb-0.5">Assigned Role</span>
            <span className="font-bold text-secondary font-mono uppercase">{user?.role || 'doctor'}</span>
          </div>
          <div className="p-3 rounded-lg bg-surface-container-low border border-outline-variant/30">
            <span className="text-outline uppercase text-[10px] font-semibold block mb-0.5">JWT Authorization</span>
            <span className="font-bold text-primary font-mono">Bearer (HS256)</span>
          </div>
        </div>
      </div>

      {/* Platform & Module Health */}
      <div className="panel">
        <h3>Service Registry & AI Engines (`/api/v1/platform/status`)</h3>
        {loading ? (
          <div className="text-xs text-outline">Checking module status...</div>
        ) : (
          <div className="space-y-4">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
              <div className="p-3 rounded-lg bg-surface-container-low">
                <span className="text-outline text-[11px] block">Graph Nodes</span>
                <span className="text-base font-bold font-mono text-primary">{status?.graph_nodes || 0}</span>
              </div>
              <div className="p-3 rounded-lg bg-surface-container-low">
                <span className="text-outline text-[11px] block">Graph Edges</span>
                <span className="text-base font-bold font-mono text-secondary">{status?.graph_edges || 0}</span>
              </div>
              <div className="p-3 rounded-lg bg-surface-container-low">
                <span className="text-outline text-[11px] block">NER Backend</span>
                <span className="text-base font-bold font-mono text-on-surface">{status?.ner_backend || 'LexicalRuleNER'}</span>
              </div>
              <div className="p-3 rounded-lg bg-surface-container-low">
                <span className="text-outline text-[11px] block">Bi-Encoder Status</span>
                <span className="text-base font-bold font-mono text-tertiary">{status?.hpo_embedding_rerank ? 'Active' : 'Fallback'}</span>
              </div>
            </div>

            {/* Checkpoints */}
            {status?.trained_checkpoints && (
              <div className="pt-2">
                <span className="text-xs font-semibold text-on-surface block mb-2">Trained Checkpoints Status:</span>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs font-mono">
                  {Object.entries(status.trained_checkpoints).map(([name, exists]) => (
                    <div
                      key={name}
                      className={`p-2 rounded-lg border text-center ${
                        exists
                          ? 'bg-green-50 border-green-200 text-green-700'
                          : 'bg-surface-container-low border-outline-variant/30 text-outline'
                      }`}
                    >
                      <div className="font-semibold">{name}</div>
                      <div className="text-[10px] mt-0.5">{exists ? 'Present' : 'Not Found'}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
