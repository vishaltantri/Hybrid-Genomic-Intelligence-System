import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import ws from './fixtures/pgx_case.json'
import drug from './fixtures/pgx_drug.json'

vi.mock('../api.js', async (importOriginal) => {
  const actual = await importOriginal()
  const names = ['pgxCase', 'pgxCaseDrug', 'listPatients']
  return { ...actual, api: Object.fromEntries(names.map((n) => [n, vi.fn()])) }
})
import { api } from '../api.js'
import PgxCasePanel from '../components/PgxCasePanel.jsx'

beforeEach(() => {
  vi.clearAllMocks()
  api.listPatients.mockResolvedValue([{ patient_id: ws.patient_id, name: 'Fx' }])
  api.pgxCase.mockResolvedValue(ws)
  api.pgxCaseDrug.mockResolvedValue(drug)
})

describe('Case PGx panel', () => {
  it('shows the safety label, derived genotype/phenotype and the drug matrix', async () => {
    render(<PgxCasePanel />)
    expect(screen.getByText(/Clinical prescribing decisions require qualified clinician review/)).toBeTruthy()
    await userEvent.selectOptions(await screen.findByLabelText('PGx case'), ws.patient_id)
    const g = await screen.findByTestId('pgx-genotypes')
    expect(g.textContent).toMatch(ws.genes[0].gene)
    expect(g.textContent).toMatch(ws.genes[0].diplotype)
    expect(g.textContent).toMatch(/not this patient's genotype/)
    expect(within(screen.getByTestId('pgx-matrix')).getAllByRole('row').length).toBe(ws.matrix.length + 1)
  })

  it('states genotype unavailable instead of inventing one', async () => {
    api.pgxCase.mockResolvedValue({ available: false, note: 'PGx genotype unavailable: no variant analysis has been run for this case (Not analyzed).', genes: [], matrix: [] })
    render(<PgxCasePanel />)
    await userEvent.selectOptions(await screen.findByLabelText('PGx case'), ws.patient_id)
    expect((await screen.findByTestId('pgx-case-empty')).textContent).toMatch(/unavailable/)
    expect(screen.queryByTestId('pgx-matrix')).toBeNull()
  })

  it('looks a drug up against the case', async () => {
    render(<PgxCasePanel />)
    await userEvent.selectOptions(await screen.findByLabelText('PGx case'), ws.patient_id)
    await screen.findByTestId('pgx-matrix')
    await userEvent.type(screen.getByLabelText('Drug name'), 'clopidogrel')
    await userEvent.click(screen.getByRole('button', { name: /Check drug/ }))
    await waitFor(() => expect(api.pgxCaseDrug).toHaveBeenCalledWith(ws.patient_id, 'clopidogrel'))
    expect((await screen.findByTestId('pgx-lookup')).textContent).toMatch(/CYP2C19/)
  })
})
