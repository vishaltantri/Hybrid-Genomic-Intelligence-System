import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import members from './fixtures/repro_members.json'
import res from './fixtures/repro_case.json'
import mc from './fixtures/repro_mc.json'
import scn from './fixtures/repro_scn.json'
import explain from './fixtures/repro_explain.json'

vi.mock('../api.js', async (importOriginal) => {
  const actual = await importOriginal()
  const names = ['listPatients', 'reproMembers', 'reproCase', 'reproMonteCarlo', 'reproScenario', 'reproExplain']
  return { ...actual, api: Object.fromEntries(names.map((n) => [n, vi.fn()])) }
})
import { api } from '../api.js'
import ReproCasePanel from '../components/ReproCasePanel.jsx'

beforeEach(() => {
  vi.clearAllMocks()
  api.listPatients.mockResolvedValue([{ patient_id: 'P1', name: 'Fx' }])
  api.reproMembers.mockResolvedValue(members)
  api.reproCase.mockResolvedValue(res)
  api.reproMonteCarlo.mockResolvedValue(mc)
  api.reproScenario.mockResolvedValue(scn)
  api.reproExplain.mockResolvedValue(explain)
})

async function open() {
  render(<ReproCasePanel onNavigate={vi.fn()} />)
  await userEvent.selectOptions(await screen.findByLabelText('Repro case'), 'P1')
  await screen.findByTestId('repro-detail')
}

describe('Case reproductive genetics', () => {
  it('shows carrier table, probabilities, Bayesian prior/posterior and a dynamic Punnett square', async () => {
    await open()
    expect(screen.getByTestId('repro-carriers').textContent).toMatch(/ATP7B/)
    expect(screen.getByTestId('repro-probs').textContent).toMatch(/Child affected/)
    expect(screen.getByTestId('repro-bayes').textContent).toMatch(/Prior/)
    expect(screen.getByTestId('repro-punnett')).toBeTruthy()
    expect(screen.getAllByText(/not a clinical outcome prediction/).length).toBeGreaterThan(0)
  })

  it('runs Monte Carlo and a scenario through the API with the chosen parameters', async () => {
    await open()
    await userEvent.click(screen.getByRole('button', { name: 'Run Monte Carlo' }))
    expect((await screen.findByTestId('repro-mc')).textContent).toMatch(/95% interval/)
    expect(api.reproMonteCarlo.mock.calls[0][1].n).toBe(20000)
    await userEvent.click(screen.getByRole('button', { name: 'Compare scenario' }))
    expect((await screen.findByTestId('repro-scenario')).textContent).toMatch(/Baseline/)
    expect(api.reproScenario.mock.calls[0][1].status_a).toBe('carrier')
  })

  it('shows the patient-friendly explanation and an insufficient-data state', async () => {
    await open()
    await userEvent.click(screen.getByRole('button', { name: 'Patient-friendly explanation' }))
    expect((await screen.findByTestId('repro-explain')).textContent).toMatch(/clinician/i)
  })

  it('shows an insufficient-data state instead of inventing a risk', async () => {
    api.reproCase.mockResolvedValue({ available: false, note: 'Insufficient data: no parents recorded', risks: [], partners: [] })
    render(<ReproCasePanel />)
    await userEvent.selectOptions(await screen.findByLabelText('Repro case'), 'P1')
    expect((await screen.findByTestId('repro-empty')).textContent).toMatch(/Insufficient/)
    expect(screen.queryByTestId('repro-detail')).toBeNull()
  })
})
