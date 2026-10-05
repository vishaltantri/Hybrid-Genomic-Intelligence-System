import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import ws from './fixtures/dx_case.json'
import why from './fixtures/dx_why.json'
import matrix from './fixtures/dx_matrix.json'
import disc from './fixtures/dx_disc.json'
import whatif from './fixtures/dx_whatif.json'

vi.mock('../api.js', async (importOriginal) => {
  const actual = await importOriginal()
  const names = ['dxCase', 'dxWhy', 'dxMatrix', 'dxDiscriminating', 'dxWhatIf', 'phenoImport', 'listPatients']
  return { ...actual, api: Object.fromEntries(names.map((n) => [n, vi.fn()])) }
})
import { api } from '../api.js'
import DiagnosisIntelView from '../views/DiagnosisIntelView.jsx'

const PID = ws.patient_id
beforeEach(() => {
  vi.clearAllMocks()
  api.listPatients.mockResolvedValue([{ patient_id: PID, name: 'Fx8' }])
  api.dxCase.mockResolvedValue(ws)
  api.dxWhy.mockResolvedValue(why)
  api.dxMatrix.mockResolvedValue(matrix)
  api.dxDiscriminating.mockResolvedValue(disc)
  api.dxWhatIf.mockResolvedValue(whatif)
  api.phenoImport.mockResolvedValue({ present: 1 })
})

async function open() {
  render(<DiagnosisIntelView onNavigate={vi.fn()} />)
  await userEvent.selectOptions(await screen.findByLabelText('Case'), PID)
  await screen.findByTestId('dx-differential')
}

describe('Diagnosis Intelligence', () => {
  it('shows the labelled CDS notice, summary and the engine differential', async () => {
    await open()
    expect(screen.getAllByText(/Clinical Decision Support/).length).toBeGreaterThan(0)
    expect(screen.getByTestId('dx-summary').textContent).toMatch(/Not analyzed/)
    const rows = within(screen.getByTestId('dx-differential')).getAllByRole('row')
    expect(rows.length).toBe(ws.differential.length + 1)
    expect(rows[1].textContent).toMatch(ws.top_diagnosis.disease_name)
  })

  it('explains why the top diagnosis ranked first using the engine factors', async () => {
    await open()
    const box = await screen.findByTestId('dx-why')
    await waitFor(() => expect(box.textContent).toMatch(/ranked first/))
    expect(box.textContent).toMatch(/Phenotype similarity/)
    expect(api.dxWhy).toHaveBeenCalledWith(PID, ws.top_diagnosis.disease_id)
  })

  it('marks missing findings Not documented and recording one reloads the case', async () => {
    await open()
    const f = await screen.findByTestId('dx-findings')
    expect(f.textContent).toMatch(/Not documented/)
    await userEvent.click(within(f).getAllByRole('button', { name: 'Present' })[0])
    await waitFor(() => expect(api.phenoImport).toHaveBeenCalled())
    await waitFor(() => expect(api.dxCase).toHaveBeenCalledTimes(2))
  })

  it('renders the matrix, discriminating findings and a real what-if comparison', async () => {
    await open()
    await userEvent.click(screen.getByRole('button', { name: /differential matrix/ }))
    expect((await screen.findByTestId('dx-matrix')).textContent).toMatch(matrix.rows[0].disease_name)
    await userEvent.click(screen.getByRole('button', { name: /Which finding would change/ }))
    expect((await screen.findByTestId('dx-discriminating')).textContent).toMatch(/Not documented/)
    await userEvent.click(within(screen.getByTestId('dx-findings')).getAllByRole('button', { name: /What if present/ })[0])
    const w = await screen.findByTestId('dx-whatif')
    expect(w.textContent).toMatch(/Baseline/)
    expect(w.textContent).toMatch(/Scenario/)
    expect(api.dxWhatIf.mock.calls[0][1].type).toBe('phenotype_add')
  })

  it('shows an insufficient-evidence state instead of inventing a ranking', async () => {
    api.dxCase.mockResolvedValue({ ...ws, available: false, differential: [], top_diagnosis: null, note: 'Insufficient data: a phenotype profile is required.' })
    render(<DiagnosisIntelView />)
    await userEvent.selectOptions(await screen.findByLabelText('Case'), PID)
    expect((await screen.findByTestId('dx-empty')).textContent).toMatch(/Insufficient/)
    expect(screen.queryByTestId('dx-differential')).toBeNull()
  })
})
