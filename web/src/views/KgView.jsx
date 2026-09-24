import React, { useEffect, useState } from 'react'
import { api } from '../api.js'

export default function KgView() {
  const [stats, setStats] = useState(null)
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState(null)

  useEffect(() => { api.kgStats().then(setStats).catch(ex => setErr(ex.message)) }, [])

  async function ingest() {
    setBusy(true); setMsg(null); setErr(null)
    try {
      const r = await api.learningIngest({ max_papers: 10 })
      setMsg(`Ingested ${r.papers_fetched ?? '?'} papers → ${r.updates_proposed ?? '?'} KG update proposals (awaiting clinician review).`)
    } catch (ex) { setErr(ex.message) } finally { setBusy(false) }
  }

  const nodeTypes = Object.entries(stats?.nodes || {}).sort((a, b) => b[1] - a[1])
  const edgeTypes = Object.entries(stats?.edges || {}).sort((a, b) => b[1] - a[1])
  const totalN = stats?.total_nodes ?? 0
  const totalE = stats?.total_edges ?? 0

  return (
    <>
      <h2>Knowledge Graph</h2>
      <p className="lede">What the AI knows: diseases, symptoms, genes, drugs, populations — and how they connect.</p>
      {err && <div className="alert error">{err}</div>}

      {stats && (
        <>
          <div className="stat-grid" style={{ marginBottom: 18 }}>
            <div className="stat"><div className="n">{totalN.toLocaleString('en-IN')}</div><div className="l">Nodes</div></div>
            <div className="stat"><div className="n">{totalE.toLocaleString('en-IN')}</div><div className="l">Edges</div></div>
            <div className="stat"><div className="n">{nodeTypes.length}</div><div className="l">Node types</div></div>
          </div>

          <div className="row">
            <div className="panel">
              <h3>Node types</h3>
              <table><tbody>
                {nodeTypes.map(([t, n]) => (
                  <tr key={t}><td>{t}</td><td style={{ textAlign: 'right' }}><b>{n.toLocaleString('en-IN')}</b></td></tr>
                ))}
              </tbody></table>
            </div>
            <div className="panel">
              <h3>Relationship types</h3>
              <table><tbody>
                {edgeTypes.slice(0, 12).map(([t, n]) => (
                  <tr key={t}><td>{t}</td><td style={{ textAlign: 'right' }}><b>{n.toLocaleString('en-IN')}</b></td></tr>
                ))}
              </tbody></table>
              {edgeTypes.length > 12 && <p className="note">+{edgeTypes.length - 12} more</p>}
            </div>
          </div>
        </>
      )}

      <div className="panel">
        <h3>Continuous learning</h3>
        <p className="kv" style={{ marginBottom: 12 }}>
          Pulls the latest rare-disease literature from PubMed and proposes knowledge-graph updates.
          Proposals wait for clinician review before entering the graph.
        </p>
        <button className="primary" onClick={ingest} disabled={busy}>{busy ? 'Fetching…' : 'Fetch new papers'}</button>
        {msg && <div className="alert info" style={{ marginTop: 12 }}>{msg}</div>}
      </div>
    </>
  )
}
