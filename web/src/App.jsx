import React, { useEffect, useState } from 'react'
import { api, login, logout, getUser, getToken } from './api.js'
import DiagnosisView from './views/DiagnosisView.jsx'
import PgxView from './views/PgxView.jsx'
import ReproView from './views/ReproView.jsx'
import NationalView from './views/NationalView.jsx'
import KgView from './views/KgView.jsx'

const NAV = [
  { id: 'diagnosis', label: 'Diagnosis', el: DiagnosisView },
  { id: 'pgx', label: 'Drug Safety', el: PgxView },
  { id: 'repro', label: 'Family Planning', el: ReproView },
  { id: 'national', label: 'National View', el: NationalView },
  { id: 'kg', label: 'Knowledge Graph', el: KgView },
]

export default function App() {
  const [user, setUser] = useState(getUser())
  const [route, setRoute] = useState('diagnosis')

  useEffect(() => {
    // restore session role if the token survived a reload
    if (getToken() && !user) setUser({ username: 'clinician', role: 'clinician' })
  }, [])

  if (!user) return <Login onDone={setUser} />

  const Active = NAV.find(n => n.id === route)?.el || DiagnosisView
  return (
    <div className="app">
      <aside className="sidebar">
        <h1>Genomind-India</h1>
        <div className="sub">Rare disease decision support</div>
        {NAV.map(n => (
          <button key={n.id} className={route === n.id ? 'active' : ''} onClick={() => setRoute(n.id)}>
            {n.label}
          </button>
        ))}
        <div className="who">
          <b>{user.username}</b>
          {user.role}
          <div style={{ marginTop: 10 }}>
            <button style={{ padding: '4px 0', fontSize: 13 }} onClick={() => { logout(); setUser(null) }}>
              Sign out
            </button>
          </div>
        </div>
      </aside>
      <main className="main">
        <Active user={user} />
      </main>
    </div>
  )
}

function Login({ onDone }) {
  const [username, setUsername] = useState('clinician')
  const [password, setPassword] = useState('changeme')
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)

  async function submit(e) {
    e.preventDefault()
    setBusy(true); setErr(null)
    try {
      onDone(await login(username, password))
    } catch (ex) {
      setErr(ex.message)
    } finally { setBusy(false) }
  }
  return (
    <div style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', background: '#0d1b2a' }}>
      <form onSubmit={submit} className="panel" style={{ width: 360 }}>
        <h2 style={{ marginBottom: 2 }}>Genomind-India</h2>
        <p className="lede">Clinician & researcher console</p>
        {err && <div className="alert error">{err}</div>}
        <label>Username</label>
        <input value={username} onChange={e => setUsername(e.target.value)} autoFocus />
        <label style={{ marginTop: 12 }}>Password</label>
        <input type="password" value={password} onChange={e => setPassword(e.target.value)} />
        <button className="primary" style={{ width: '100%', marginTop: 16 }} disabled={busy}>
          {busy ? 'Signing in…' : 'Sign in'}
        </button>
        <p className="note">Default dev account: clinician / changeme</p>
      </form>
    </div>
  )
}
