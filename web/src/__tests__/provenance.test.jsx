import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import ws from './fixtures/dx_case.json'

vi.mock('../api.js', async (importOriginal) => {
  const actual = await importOriginal()
  const names = ['dxCase', 'dxWhy', 'dxMatrix', 'dxDiscriminating', 'dxWhatIf', 'phenoImport', 'listPatients', 'dxConfirm']
  return { ...actual, api: Object.fromEntries(names.map((n) => [n, vi.fn()])) }
})
import { api } from '../api.js'
import DiagnosisIntelView from '../views/DiagnosisIntelView.jsx'

const PID = ws.patient_id
const withClaims = (confirmedId) => ({
  ...ws,
  interpretation: 'The differential is a model ranking (decision support), not a clinical diagnosis.',
  confidence_note: 'Probabilities are relative scores within this differential, not calibrated clinical confidence.',
  differential: ws.differential.map((d) => (d.disease_id === confirmedId
    ? { ...d, claim: 'Clinician-confirmed', confirmation: { confirmed_by: 'doc' } } : { ...d, claim: 'Model ranking', confirmation: null })),
})

beforeEach(() => {
  vi.clearAllMocks()
  api.listPatients.mockResolvedValue([{ patient_id: PID }])
  api.dxCase.mockResolvedValue(withClaims(null))
  api.dxWhy.mockResolvedValue({ lines: [], factors: [] })
  api.dxConfirm.mockResolvedValue({})
})

describe('model ranking vs clinician confirmation', () => {
  it('labels every row as a model ranking and states the interpretation', async () => {
    render(<DiagnosisIntelView onNavigate={vi.fn()} />)
    await userEvent.selectOptions(await screen.findByLabelText('Case'), PID)
    await screen.findByTestId('dx-differential')
    expect(screen.getByTestId('dx-interpretation').textContent).toMatch(/not a clinical diagnosis/)
    expect(screen.getByTestId('dx-interpretation').textContent).toMatch(/not calibrated/)
    expect(screen.getAllByText('Model ranking').length).toBe(ws.differential.length)
  })

  it('confirming records a clinician confirmation through the API and refreshes the label', async () => {
    render(<DiagnosisIntelView onNavigate={vi.fn()} />)
    await userEvent.selectOptions(await screen.findByLabelText('Case'), PID)
    await screen.findByTestId('dx-differential')
    const first = ws.differential[0]
    await userEvent.click(screen.getAllByText(first.disease_name)[0])
    api.dxCase.mockResolvedValue(withClaims(first.disease_id))
    await userEvent.click(await screen.findByRole('button', { name: new RegExp(`confirmation of ${first.disease_name}`) }))
    await waitFor(() => expect(api.dxConfirm).toHaveBeenCalledWith(PID, { disease_id: first.disease_id }))
    expect(await screen.findByText(/Clinician-confirmed by doc/)).toBeTruthy()
  })
})
