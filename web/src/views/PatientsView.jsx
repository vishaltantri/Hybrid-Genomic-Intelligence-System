import React, { useEffect, useState } from 'react'
import { api } from '../api.js'
import { Users, UserPlus, Stethoscope, Search, ShieldCheck } from 'lucide-react'

export default function PatientsView({ onSelectPatientForDiagnosis }) {
  const [patients, setPatients] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [showAddModal, setShowAddModal] = useState(false)
  const [search, setSearch] = useState('')

  // New Patient Form State
  const [ageYears, setAgeYears] = useState(4)
  const [sex, setSex] = useState('M')
  const [state, setState] = useState('Andhra Pradesh')
  const [district, setDistrict] = useState('Kurnool')
  const [community, setCommunity] = useState('Reddy')
  const [consanguineous, setConsanguineous] = useState(true)
  const [notes, setNotes] = useState('Child presenting with jaundice, brown corneal ring, and gait difficulty.')
  const [saving, setSaving] = useState(false)

  const loadPatients = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await api.listPatients()
      setPatients(data || [])
    } catch (ex) {
      setError(ex.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadPatients()
  }, [])

  const handleCreatePatient = async (e) => {
    e.preventDefault()
    setSaving(true)
    try {
      await api.createPatient({
        age_years: Number(ageYears),
        sex,
        state,
        district,
        community,
        consanguineous,
        notes,
      })
      setShowAddModal(false)
      loadPatients()
    } catch (ex) {
      setError(ex.message)
    } finally {
      setSaving(false)
    }
  }

  const filteredPatients = patients.filter((p) => {
    const s = search.toLowerCase()
    return (
      p.patient_id?.toLowerCase().includes(s) ||
      p.state?.toLowerCase().includes(s) ||
      p.community?.toLowerCase().includes(s) ||
      p.district?.toLowerCase().includes(s)
    )
  })

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold font-headline-sm text-on-surface">Patient Registry</h2>
          <p className="text-xs text-on-surface-variant mt-0.5">
            Registered clinical cases with Indian geographic and demographic stratification.
          </p>
        </div>
        <button
          onClick={() => setShowAddModal(true)}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-white text-xs font-semibold hover:bg-primary-container transition-all shadow-sm"
        >
          <UserPlus size={16} />
          <span>Register New Patient</span>
        </button>
      </div>

      {error && (
        <div className="p-3.5 rounded-lg bg-red-50 border border-red-200 text-red-700 text-xs">
          {error}
        </div>
      )}

      {/* Search and Filters */}
      <div className="p-4 rounded-xl bg-white border border-outline-variant/40 shadow-xs flex items-center gap-3">
        <Search size={18} className="text-outline shrink-0" />
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Filter by Patient ID, State, Community, or District..."
          className="w-full text-xs bg-transparent border-none outline-none focus:ring-0 p-0"
        />
      </div>

      {/* Patients Table */}
      <div className="rounded-xl bg-white border border-outline-variant/40 shadow-xs overflow-hidden">
        {loading ? (
          <div className="p-12 text-center text-xs text-outline">
            <span className="w-5 h-5 border-2 border-primary/30 border-t-primary rounded-full animate-spin inline-block mb-2"></span>
            <div>Loading patient records...</div>
          </div>
        ) : filteredPatients.length === 0 ? (
          <div className="p-12 text-center text-on-surface-variant">
            <Users size={32} className="mx-auto text-outline mb-2" />
            <h4 className="text-sm font-semibold text-on-surface">No Patient Records Found</h4>
            <p className="text-xs text-outline mt-1 mb-4">
              Register a new patient to begin phenotypic profiling and differential diagnosis.
            </p>
            <button
              onClick={() => setShowAddModal(true)}
              className="px-3.5 py-1.5 rounded-lg bg-primary text-white text-xs font-semibold"
            >
              Add First Patient
            </button>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table>
              <thead>
                <tr>
                  <th>Patient ID</th>
                  <th>Age / Sex</th>
                  <th>State & District</th>
                  <th>Community</th>
                  <th>Consanguinity</th>
                  <th>Registered</th>
                  <th className="text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredPatients.map((p) => (
                  <tr key={p.patient_id} className="hover:bg-surface-container-low/50">
                    <td className="font-mono font-semibold text-primary">
                      {p.patient_id}
                    </td>
                    <td>
                      {p.age_years ? `${p.age_years} yrs` : '—'} / {p.sex || '—'}
                    </td>
                    <td>
                      <div className="font-medium text-on-surface">{p.state || '—'}</div>
                      {p.district && <div className="text-[11px] text-outline">{p.district}</div>}
                    </td>
                    <td>
                      <span className="px-2 py-0.5 rounded bg-surface-container text-on-surface-variant text-xs font-mono">
                        {p.community || 'Not specified'}
                      </span>
                    </td>
                    <td>
                      {p.consanguineous ? (
                        <span className="pill amber text-[11px]">Yes (F≥0.0625)</span>
                      ) : (
                        <span className="pill green text-[11px]">No</span>
                      )}
                    </td>
                    <td className="text-xs text-outline font-mono">
                      {p.created_utc ? p.created_utc.split('T')[0] : '—'}
                    </td>
                    <td className="text-right">
                      <button
                        onClick={() => onSelectPatientForDiagnosis(p)}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-surface-container-low text-primary text-xs font-semibold hover:bg-primary hover:text-white transition-all"
                        title="Analyze in Differential Diagnosis"
                      >
                        <Stethoscope size={14} />
                        <span>Diagnose</span>
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Create Patient Modal */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm">
          <div className="w-full max-w-lg bg-white rounded-2xl shadow-xl overflow-hidden border border-outline-variant/40">
            <div className="bg-primary p-5 text-white flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <UserPlus size={20} />
                <h3 className="font-bold text-base font-headline-sm">Register New Patient</h3>
              </div>
              <button
                onClick={() => setShowAddModal(false)}
                className="text-white/80 hover:text-white"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleCreatePatient} className="p-6 space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label>Age (Years)</label>
                  <input
                    type="number"
                    min="0"
                    max="120"
                    value={ageYears}
                    onChange={(e) => setAgeYears(e.target.value)}
                    required
                  />
                </div>
                <div>
                  <label>Sex</label>
                  <select value={sex} onChange={(e) => setSex(e.target.value)}>
                    <option value="M">Male (M)</option>
                    <option value="F">Female (F)</option>
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label>State (Consanguinity Prior)</label>
                  <input
                    type="text"
                    value={state}
                    onChange={(e) => setState(e.target.value)}
                    placeholder="e.g. Andhra Pradesh"
                    required
                  />
                </div>
                <div>
                  <label>District</label>
                  <input
                    type="text"
                    value={district}
                    onChange={(e) => setDistrict(e.target.value)}
                    placeholder="e.g. Kurnool"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label>Community (Founder Prior)</label>
                  <input
                    type="text"
                    value={community}
                    onChange={(e) => setCommunity(e.target.value)}
                    placeholder="e.g. Reddy, Agarwal"
                  />
                </div>
                <div>
                  <label>Consanguineous Union</label>
                  <select
                    value={consanguineous ? 'yes' : 'no'}
                    onChange={(e) => setConsanguineous(e.target.value === 'yes')}
                  >
                    <option value="yes">Yes (Parents Related)</option>
                    <option value="no">No</option>
                  </select>
                </div>
              </div>

              <div>
                <label>Clinical Notes / Symptoms</label>
                <textarea
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  placeholder="Clinical presentation, observed symptoms, age of onset..."
                />
              </div>

              <div className="pt-2 flex items-center justify-end gap-3 border-t border-outline-variant/30">
                <button
                  type="button"
                  onClick={() => setShowAddModal(false)}
                  className="px-4 py-2 rounded-lg border border-outline-variant/50 text-xs font-semibold"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={saving}
                  className="px-4 py-2 rounded-lg bg-primary text-white text-xs font-semibold hover:bg-primary-container disabled:opacity-60"
                >
                  {saving ? 'Saving...' : 'Register Patient'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
