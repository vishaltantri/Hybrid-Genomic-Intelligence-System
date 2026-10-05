import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, within, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

// The fixtures are real payloads captured from the running backend (see tests/test_digital_twin.py
// for the server-side guarantees); the API client is mocked so each test controls timing and errors.
import twinFull from './fixtures/twin_full.json'
import twinEmpty from './fixtures/twin_empty.json'
import scenarioExclusion from './fixtures/scenario_exclusion.json'

vi.mock('../api.js', async (importOriginal) => {
  const actual = await importOriginal()
  return {
    ...actual,
    api: {
      listPatients: vi.fn(),
      twin: vi.fn(),
      twinScenarios: vi.fn(),
      twinCreateScenario: vi.fn(),
      twinScenario: vi.fn(),
      twinDeleteScenario: vi.fn(),
      twinSaveSnapshot: vi.fn(),
      twinReportHandoff: vi.fn(),
      assistantChat: vi.fn(),
    },
  }
})

import { api, consumeNavContext } from '../api.js'
import DigitalTwinView from '../views/DigitalTwinView.jsx'

const PATIENTS = [
  { patient_id: 'PT-CBDADDEA', age_years: 9, sex: 'M', state: 'Andhra Pradesh' },
  { patient_id: 'PT-062D1EDB', age_years: 11, sex: 'F', state: 'Chhattisgarh' },
]

function setup(onNavigate = vi.fn()) {
  api.listPatients.mockResolvedValue(PATIENTS)
  api.twin.mockImplementation((pid) =>
    Promise.resolve(pid === 'PT-CBDADDEA' ? twinFull : twinEmpty),
  )
  api.twinScenarios.mockResolvedValue([])
  const user = userEvent.setup()
  render(<DigitalTwinView onNavigate={onNavigate} />)
  return { user, onNavigate }
}

async function selectPatient(user, pid) {
  await screen.findByRole('option', { name: new RegExp(pid) })
  await user.selectOptions(screen.getByLabelText('Patient'), pid)
}

beforeEach(() => {
  vi.clearAllMocks()
  sessionStorage.clear()
})

describe('Digital Twin view', () => {
  it('lists patients and builds the Twin for the selected one from the API', async () => {
    const { user } = setup()
    await selectPatient(user, 'PT-CBDADDEA')
    await waitFor(() => expect(api.twin).toHaveBeenCalledWith('PT-CBDADDEA', undefined))
    const snap = await screen.findByTestId('twin-snapshot')
    const s = twinFull.snapshot
    const stat = (label) => within(snap).getByText(label).nextElementSibling
    expect(stat('Phenotypes')).toHaveTextContent(String(s.phenotypes))
    expect(stat('Variants')).toHaveTextContent(String(s.variants))
    expect(stat('Pathogenic')).toHaveTextContent(String(s.pathogenic))
    expect(stat('PGx findings')).toHaveTextContent(String(s.pgx_findings.length))
    expect(within(snap).getByText(s.top_diagnosis.disease_name)).toBeInTheDocument()
    expect(within(snap).getByText(new RegExp(s.snapshot_version))).toBeInTheDocument()
  })

  it('prompts for a patient before showing any state', async () => {
    setup()
    expect(await screen.findByText(/Select a patient to build their Digital Twin/)).toBeInTheDocument()
    expect(screen.queryByTestId('twin-snapshot')).not.toBeInTheDocument()
  })

  it('rebuilds on patient change and never shows the previous patient\'s state', async () => {
    const { user } = setup()
    await selectPatient(user, 'PT-CBDADDEA')
    await screen.findByTestId('twin-snapshot')
    expect(screen.getAllByText('Wilson disease').length).toBeGreaterThan(0)

    await selectPatient(user, 'PT-062D1EDB')
    await waitFor(() => expect(api.twin).toHaveBeenLastCalledWith('PT-062D1EDB', undefined))
    const snap = await screen.findByTestId('twin-snapshot')
    expect(within(snap).getByText('Insufficient data')).toBeInTheDocument()
    expect(screen.queryByText('Wilson disease')).not.toBeInTheDocument()
    expect(within(snap).getByText(/PT-062D1EDB/)).toBeInTheDocument()
  })

  it('ignores a late response that belongs to a previously selected patient', async () => {
    let resolveA
    api.listPatients.mockResolvedValue(PATIENTS)
    api.twinScenarios.mockResolvedValue([])
    api.twin.mockImplementation((pid) =>
      pid === 'PT-CBDADDEA'
        ? new Promise((res) => { resolveA = () => res(twinFull) })
        : Promise.resolve(twinEmpty),
    )
    const user = userEvent.setup()
    render(<DigitalTwinView onNavigate={vi.fn()} />)
    await selectPatient(user, 'PT-CBDADDEA') // never resolves yet
    await selectPatient(user, 'PT-062D1EDB')
    await screen.findByTestId('twin-snapshot')
    resolveA() // A answers after B was selected
    await new Promise((r) => setTimeout(r, 50))
    expect(screen.queryByText('Wilson disease')).not.toBeInTheDocument()
    expect(within(screen.getByTestId('twin-snapshot')).getByText(/PT-062D1EDB/)).toBeInTheDocument()
  })

  it('shows explicit insufficient-data notes instead of fabricated state', async () => {
    const { user } = setup()
    await selectPatient(user, 'PT-062D1EDB')
    await screen.findByTestId('twin-snapshot')
    const inspector = screen.getByTestId('state-inspector')
    expect(within(inspector).getByText(/Insufficient data: no HPO phenotypes/)).toBeInTheDocument()
    await user.click(within(inspector).getByRole('tab', { name: /PGx/ }))
    expect(within(inspector).getByText('No PGx findings available for this case.')).toBeInTheDocument()
    await user.click(within(inspector).getByRole('tab', { name: /Family/ }))
    expect(within(inspector).getByText('Family/inheritance information unavailable.')).toBeInTheDocument()
    await user.click(within(inspector).getByRole('tab', { name: /Timeline/ }))
    expect(within(inspector).getByText(/Longitudinal history is limited/)).toBeInTheDocument()
  })

  it('inspects real underlying data when a state node is clicked and links to Variant Intelligence', async () => {
    const { user, onNavigate } = setup()
    await selectPatient(user, 'PT-CBDADDEA')
    await screen.findByTestId('twin-snapshot')
    await user.click(screen.getByTestId('twin-node-genomic'))
    const inspector = screen.getByTestId('state-inspector')
    const counts = within(inspector).getByTestId('genomic-counts')
    expect(within(counts).getByText(String(twinFull.genomic.counts.total))).toBeInTheDocument()
    const first = twinFull.genomic.variants[0]
    expect(within(inspector).getByTestId(`variant-row-${first.variant_id}`)).toHaveTextContent(first.gene_symbol)

    await user.click(within(inspector).getByTestId('open-variants'))
    expect(onNavigate).toHaveBeenCalledWith('variants')
    expect(consumeNavContext('variants')).toMatchObject({
      patient_id: 'PT-CBDADDEA',
      analysis_id: twinFull.genomic.analysis_id,
    })
  })

  it('shows phenotype provenance and states that onset/severity are not recorded', async () => {
    const { user } = setup()
    await selectPatient(user, 'PT-CBDADDEA')
    await screen.findByTestId('twin-snapshot')
    const first = twinFull.phenotype.observed[0]
    const row = screen.getByTestId(`phenotype-${first.hpo_id}`)
    expect(row).toHaveTextContent(first.sources[0].ref)
    expect(row).toHaveTextContent('Onset: not recorded')
    await user.click(screen.getByRole('tab', { name: 'Provenance' }))
    const prov = screen.getByTestId('provenance')
    const sections = within(prov).getAllByRole('row').map((r) => r.children[0].textContent)
    expect(sections).toEqual(expect.arrayContaining(['identity', 'phenotype', 'genomic', 'diagnosis']))
    expect(within(prov).getAllByText(twinFull.genomic.analysis_id).length).toBeGreaterThan(0)
  })

  it('opens the Knowledge Graph at the selected disease', async () => {
    const { user, onNavigate } = setup()
    await selectPatient(user, 'PT-CBDADDEA')
    await screen.findByTestId('twin-snapshot')
    await user.click(screen.getByTestId('twin-node-diagnosis'))
    const kg = within(screen.getByTestId('differential')).getAllByRole('button', { name: 'Knowledge Graph' })[0]
    await user.click(kg)
    expect(onNavigate).toHaveBeenCalledWith('kg')
    expect(consumeNavContext('kg')).toMatchObject({ disease_id: twinFull.diagnosis.top_diagnosis.disease_id })
  })

  it('surfaces a load error without leaving a stale Twin on screen', async () => {
    api.listPatients.mockResolvedValue(PATIENTS)
    api.twinScenarios.mockResolvedValue([])
    api.twin.mockRejectedValue(new Error('Patient not found'))
    const user = userEvent.setup()
    render(<DigitalTwinView onNavigate={vi.fn()} />)
    await selectPatient(user, 'PT-CBDADDEA')
    expect(await screen.findByRole('alert')).toHaveTextContent('Patient not found')
    expect(screen.queryByTestId('twin-snapshot')).not.toBeInTheDocument()
  })
})

describe('What-if simulation', () => {
  async function openWithTwin(user) {
    await selectPatient(user, 'PT-CBDADDEA')
    await screen.findByTestId('twin-snapshot')
    return screen.getByTestId('scenario-workspace')
  }

  it('creates a scenario via the backend and renders baseline vs scenario with explanations', async () => {
    api.twinCreateScenario.mockResolvedValue(scenarioExclusion)
    const { user } = setup()
    const ws = await openWithTwin(user)
    const atp7b = twinFull.genomic.variants.find((v) => v.gene_symbol === 'ATP7B')
    await user.selectOptions(within(ws).getByLabelText('Variant'), atp7b.variant_id)
    await user.type(within(ws).getByLabelText('Scenario name'), 'Exclude ATP7B')
    await user.click(within(ws).getByTestId('run-scenario'))

    await waitFor(() => expect(api.twinCreateScenario).toHaveBeenCalledTimes(1))
    expect(api.twinCreateScenario).toHaveBeenCalledWith('PT-CBDADDEA', {
      type: 'variant_exclusion',
      name: 'Exclude ATP7B',
      params: { variant_ids: [atp7b.variant_id] },
      analysis_id: twinFull.genomic.analysis_id,
    })
    const result = await screen.findByTestId('scenario-result')
    const table = within(result).getByTestId('comparison-table')
    const row = within(table).getByText('Variants analysed').closest('tr')
    expect(row).toHaveTextContent('8')
    expect(row).toHaveTextContent('7')
    const expl = within(result).getByTestId('explanation')
    expect(expl).toHaveTextContent('Excluded ATP7B')
    expect(expl).toHaveTextContent('does not move it')
    expect(within(result).getByText(/Computational decision-support simulation/)).toBeInTheDocument()
  })

  it('refuses to run an incomplete scenario and does not call the backend', async () => {
    const { user } = setup()
    const ws = await openWithTwin(user)
    await user.click(within(ws).getByTestId('run-scenario'))
    expect(await within(ws).findByRole('alert')).toHaveTextContent('Complete the scenario inputs')
    expect(api.twinCreateScenario).not.toHaveBeenCalled()
  })

  it('shows the backend error for an invalid scenario and no result', async () => {
    api.twinCreateScenario.mockRejectedValue(new Error('Variant is already classified as Pathogenic'))
    const { user } = setup()
    const ws = await openWithTwin(user)
    await user.selectOptions(within(ws).getByLabelText('Scenario type'), 'variant_reclassification')
    await user.selectOptions(within(ws).getByLabelText('Variant'), twinFull.genomic.variants[0].variant_id)
    await user.click(within(ws).getByTestId('run-scenario'))
    expect(await within(ws).findByRole('alert')).toHaveTextContent('already classified')
    expect(screen.queryByTestId('scenario-result')).not.toBeInTheDocument()
  })

  it('resets the workspace', async () => {
    api.twinCreateScenario.mockResolvedValue(scenarioExclusion)
    const { user } = setup()
    const ws = await openWithTwin(user)
    await user.selectOptions(within(ws).getByLabelText('Variant'), twinFull.genomic.variants[0].variant_id)
    await user.click(within(ws).getByTestId('run-scenario'))
    await screen.findByTestId('scenario-result')
    await user.click(within(ws).getByTestId('reset-scenario'))
    expect(screen.queryByTestId('scenario-result')).not.toBeInTheDocument()
    expect(within(ws).getByLabelText('Variant')).toHaveValue('')
  })

  it('does not offer variant scenarios when no analysis is linked (insufficient data)', async () => {
    const { user } = setup()
    await selectPatient(user, 'PT-062D1EDB')
    await screen.findByTestId('twin-snapshot')
    const ws = screen.getByTestId('scenario-workspace')
    expect(within(ws).getByText(/Insufficient data: no Variant Intelligence analysis/)).toBeInTheDocument()
    expect(within(ws).queryByLabelText('Variant')).not.toBeInTheDocument()
  })

  it('adds a scenario to the report through the backend and reports the stored event id', async () => {
    api.twinCreateScenario.mockResolvedValue(scenarioExclusion)
    api.twinReportHandoff.mockResolvedValue({
      event_id: 'EV-123', snapshot_version: twinFull.snapshot.snapshot_version, scenarios: [{}],
    })
    const { user } = setup()
    const ws = await openWithTwin(user)
    await user.selectOptions(within(ws).getByLabelText('Variant'), twinFull.genomic.variants[0].variant_id)
    await user.click(within(ws).getByTestId('run-scenario'))
    await user.click(await screen.findByTestId('add-scenario-to-report'))
    await waitFor(() => expect(api.twinReportHandoff).toHaveBeenCalledWith('PT-CBDADDEA', {
      scenario_ids: [scenarioExclusion.scenario_id], analysis_id: null, // null = the Twin's default (latest) analysis
    }))
    expect(await screen.findByText(/Added to the clinical record as EV-123/)).toBeInTheDocument()
  })

  it('surfaces a failed report hand-off instead of showing fake success', async () => {
    api.twinReportHandoff.mockRejectedValue(new Error('Scenario not found'))
    const { user } = setup()
    await openWithTwin(user)
    await user.click(screen.getByTestId('add-snapshot-to-report'))
    expect(await screen.findByText(/Could not add to report: Scenario not found/)).toBeInTheDocument()
    expect(screen.queryByText(/Added to the clinical record/)).not.toBeInTheDocument()
  })

  it('sends the Twin and scenario ids to the AI Assistant backend', async () => {
    api.twinCreateScenario.mockResolvedValue(scenarioExclusion)
    api.assistantChat.mockResolvedValue({
      response: 'grounded answer', citations: [{ source_type: 'Digital Twin', identifier: 'TS-1' }],
      context_summary: { twin_snapshot: 'TS-1', twin_scenario: scenarioExclusion.scenario_id },
    })
    const { user } = setup()
    const ws = await openWithTwin(user)
    await user.selectOptions(within(ws).getByLabelText('Variant'), twinFull.genomic.variants[0].variant_id)
    await user.click(within(ws).getByTestId('run-scenario'))
    await user.click(await screen.findByRole('button', { name: /Ask AI about this scenario/ }))
    const panel = screen.getByTestId('twin-assistant')
    await user.click(within(panel).getByRole('button', { name: /^Ask$/ }))
    await waitFor(() => expect(api.assistantChat).toHaveBeenCalledWith(expect.objectContaining({
      patient_id: 'PT-CBDADDEA', include_twin: true, twin_scenario_id: scenarioExclusion.scenario_id,
    })))
    expect(await within(panel).findByText('grounded answer')).toBeInTheDocument()
    expect(within(panel).getByText(/Grounded in Twin snapshot/)).toBeInTheDocument()
  })
})
