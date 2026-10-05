import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, within, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import twinFull from './fixtures/twin_full.json'
import twinEmpty from './fixtures/twin_empty.json'
import scenarioExclusion from './fixtures/scenario_exclusion.json'

vi.mock('../api.js', async (importOriginal) => {
  const actual = await importOriginal()
  return {
    ...actual,
    api: {
      listPatients: vi.fn(), twin: vi.fn(), twinScenarios: vi.fn(), twinCreateScenario: vi.fn(),
      twinScenario: vi.fn(), twinDeleteScenario: vi.fn(), twinSaveSnapshot: vi.fn(),
      twinReportHandoff: vi.fn(), assistantChat: vi.fn(),
    },
  }
})

import { api, consumeNavContext } from '../api.js'
import DigitalTwinView from '../views/DigitalTwinView.jsx'

const PID = twinFull.snapshot.patient_id
const PATIENTS = [{ patient_id: PID, age_years: 9, sex: 'M', state: 'Andhra Pradesh' }, { patient_id: 'PT-EMPTY', age_years: 11, sex: 'F', state: 'X' }]
const ATP7B = twinFull.genomic.variants.find((v) => v.gene_symbol === 'ATP7B')

async function open(pid = PID, props = {}) {
  api.listPatients.mockResolvedValue(PATIENTS)
  api.twin.mockImplementation((id) => Promise.resolve(id === PID ? twinFull : twinEmpty))
  api.twinScenarios.mockResolvedValue([])
  const user = userEvent.setup()
  const onNavigate = vi.fn()
  render(<DigitalTwinView onNavigate={onNavigate} {...props} />)
  await screen.findByRole('option', { name: new RegExp(pid) })
  await user.selectOptions(screen.getByLabelText('Patient'), pid)
  await screen.findByTestId('twin-stage')
  return { user, onNavigate }
}

beforeEach(() => {
  vi.clearAllMocks()
  sessionStorage.clear()
})

describe('Twin stage and control bar', () => {
  it('shows the anatomical stage first and the state data as a secondary panel', async () => {
    await open()
    const stage = screen.getByTestId('twin-stage')
    expect(stage).toHaveAttribute('data-mode', 'anatomy')
    expect(stage).toHaveTextContent('Computational Digital Twin')
    expect(screen.getByLabelText('Clinical intelligence')).toContainElement(screen.getByTestId('twin-snapshot'))
  })

  it('falls back to a 2D schematic with a notice when WebGL is unavailable (jsdom has none)', async () => {
    await open()
    expect(screen.getByTestId('twin-stage')).toHaveAttribute('data-renderer', 'fallback-2d')
    expect(screen.getByTestId('body-fallback-2d')).toHaveTextContent('WebGL is unavailable')
    expect(screen.getByTestId('organ-liver')).toBeInTheDocument()
    expect(screen.getByTestId('twin-snapshot')).toBeInTheDocument() // the computational Twin keeps working
  })

  it('switches Anatomy -> Genome -> DNA -> Systems -> Timeline and each view changes the stage', async () => {
    const { user } = await open()
    const stage = () => screen.getByTestId('twin-stage')
    await user.click(screen.getByTestId('mode-genome'))
    expect(stage()).toHaveAttribute('data-mode', 'genome')
    expect(within(stage()).getByTestId('genome-view')).toBeInTheDocument()
    expect(within(stage()).getAllByTestId(/^chrom-chr/)).toHaveLength(24)
    await user.click(screen.getByTestId('mode-dna'))
    expect(within(stage()).getByTestId('dna-info')).toHaveTextContent('Selected gene: none')
    expect(within(stage()).getByTestId('dna-info')).toHaveTextContent('no patient variants are invented')
    await user.click(screen.getByTestId('mode-systems'))
    expect(screen.getByTestId('systems-rail')).toBeInTheDocument()
    await user.click(screen.getByTestId('mode-timeline'))
    expect(within(stage()).getByTestId('twin-timeline-visual')).toBeInTheDocument()
    await user.click(screen.getByTestId('mode-anatomy'))
    expect(within(stage()).getByTestId('body-fallback-2d')).toBeInTheDocument()
  })

  it('camera buttons set the active view and reset returns to the front', async () => {
    const { user } = await open()
    await user.click(screen.getByTestId('view-back'))
    expect(screen.getByTestId('view-back')).toHaveAttribute('aria-pressed', 'true')
    await user.click(screen.getByTestId('view-left'))
    expect(screen.getByTestId('view-left')).toHaveAttribute('aria-pressed', 'true')
    await user.click(screen.getByTestId('reset-view'))
    expect(screen.getByTestId('view-front')).toHaveAttribute('aria-pressed', 'true')
  })
})

describe('Systems and organs', () => {
  it('selecting an organ with case data shows only mapped findings, genes, variants and diseases', async () => {
    const { user } = await open()
    await user.click(screen.getByTestId('organ-liver'))
    const panel = screen.getByTestId('entity-panel')
    expect(panel).toHaveTextContent('Hepatic')
    expect(panel).toHaveTextContent('Hepatomegaly')
    expect(panel).toHaveTextContent('ATP7B')
    expect(panel).toHaveTextContent('Wilson disease')
    expect(panel).toHaveTextContent('not organ damage')
  })

  it('selecting an organ with no case data shows the neutral message, not an invented finding', async () => {
    const { user } = await open()
    await user.click(screen.getByTestId('organ-repro'))
    const panel = screen.getByTestId('entity-panel')
    expect(panel).toHaveTextContent('No case-specific genomic or phenotype findings mapped to this system.')
    expect(panel).toHaveTextContent('no organ-specific data available')
  })

  it('lists every body system as text with its data count (not only in 3D)', async () => {
    await open()
    const list = screen.getByTestId('system-list')
    expect(within(list).getAllByRole('button')).toHaveLength(twinFull.anatomy.systems.length)
    expect(list).toHaveTextContent('no case data')
  })
})

describe('Variant selection, genome and DNA views', () => {
  it('selecting a variant in the genome view opens real evidence and the variant -> gene -> system chain', async () => {
    const { user, onNavigate } = await open()
    await user.click(screen.getByTestId('mode-genome'))
    await user.click(screen.getByTestId(`genome-variant-${ATP7B.variant_id}`))
    const panel = screen.getByTestId('entity-panel')
    expect(panel).toHaveTextContent('ATP7B')
    expect(panel).toHaveTextContent(ATP7B.cdna)
    expect(panel).toHaveTextContent(ATP7B.acmg_classification)
    expect(panel).toHaveTextContent('Wilson disease')
    expect(within(panel).getByTestId('entity-chain')).toHaveTextContent('Hepatic')
    expect(panel).toHaveTextContent(ATP7B.criteria_met_pathogenic[0])
    await user.click(within(panel).getByTestId('view-acmg'))
    expect(onNavigate).toHaveBeenCalledWith('variants')
    expect(consumeNavContext('variants')).toMatchObject({ patient_id: PID, analysis_id: twinFull.genomic.analysis_id, variant_id: ATP7B.variant_id })
  })

  it('opens the Knowledge Graph from a selected variant', async () => {
    const { user, onNavigate } = await open()
    await user.click(screen.getByTestId('mode-genome'))
    await user.click(screen.getByTestId(`genome-variant-${ATP7B.variant_id}`))
    await user.click(screen.getByTestId('view-kg'))
    expect(onNavigate).toHaveBeenCalledWith('kg')
    expect(consumeNavContext('kg')).toMatchObject({ disease_id: 'ORPHA:915', genes: ['ATP7B'] })
  })

  it('chromosome drill-down lists the analysed variants of that chromosome', async () => {
    const { user } = await open()
    await user.click(screen.getByTestId('mode-genome'))
    await user.click(within(screen.getByTestId('chrom-chr13')).getByRole('button', { name: /Chromosome 13/ }))
    expect(screen.getByTestId('chrom-drill')).toHaveTextContent('chr13')
    expect(screen.getByTestId('chrom-drill')).toHaveTextContent('ATP7B')
  })

  it('DNA view shows the selected gene, variant and classification and no invented variants without a selection', async () => {
    const { user } = await open()
    await user.click(screen.getByTestId('mode-genome'))
    await user.click(screen.getByTestId(`genome-variant-${ATP7B.variant_id}`))
    await user.click(screen.getByTestId('mode-dna'))
    const info = screen.getByTestId('dna-info')
    expect(info).toHaveTextContent('Selected gene: ATP7B')
    expect(info).toHaveTextContent(ATP7B.cdna)
    expect(info).toHaveTextContent(ATP7B.acmg_classification)
  })

  it('the leading diagnosis can be selected and shows its supporting evidence', async () => {
    const { user, onNavigate } = await open()
    await user.click(screen.getByTestId('select-diagnosis'))
    const panel = screen.getByTestId('entity-panel')
    expect(panel).toHaveTextContent('Current leading diagnosis')
    expect(panel).toHaveTextContent(twinFull.diagnosis.top_diagnosis.disease_name)
    await user.click(within(panel).getByTestId('open-diagnosis-2'))
    expect(onNavigate).toHaveBeenCalledWith('diagnosis')
  })

  it('Ask AI from a selected variant sends that variant with the Twin context', async () => {
    api.assistantChat.mockResolvedValue({ response: 'ok', citations: [], context_summary: {} })
    const { user } = await open()
    await user.click(screen.getByTestId('mode-genome'))
    await user.click(screen.getByTestId(`genome-variant-${ATP7B.variant_id}`))
    await user.click(screen.getByTestId('ask-variant'))
    const panel = screen.getByTestId('twin-assistant')
    expect(within(panel).getByLabelText('Question for the AI Assistant')).toHaveValue("Why is this patient's ATP7B variant important?")
    await user.click(within(panel).getByRole('button', { name: /^Ask$/ }))
    await waitFor(() => expect(api.assistantChat).toHaveBeenCalledWith(expect.objectContaining({
      include_twin: true, selected_variant_id: ATP7B.variant_id, patient_id: PID,
    })))
  })

  it('switching patient clears the selection and returns to the anatomy view', async () => {
    const { user } = await open()
    await user.click(screen.getByTestId('mode-genome'))
    await user.click(screen.getByTestId(`genome-variant-${ATP7B.variant_id}`))
    await user.selectOptions(screen.getByLabelText('Patient'), 'PT-EMPTY')
    await waitFor(() => expect(api.twin).toHaveBeenLastCalledWith('PT-EMPTY', undefined))
    await screen.findByTestId('twin-stage')
    expect(screen.getByTestId('twin-stage')).toHaveAttribute('data-mode', 'anatomy')
    expect(screen.getByTestId('entity-panel')).toHaveTextContent('Select an organ system')
    expect(screen.queryByText('ATP7B')).not.toBeInTheDocument()
  })
})

describe('Simulation visuals', () => {
  async function run(user) {
    api.twinCreateScenario.mockResolvedValue(scenarioExclusion)
    const ws = screen.getByTestId('scenario-workspace')
    await user.selectOptions(within(ws).getByLabelText('Variant'), ATP7B.variant_id)
    await user.click(within(ws).getByTestId('run-scenario'))
    return screen.findByTestId('scenario-compare')
  }

  it('shows the real computation stages with server-measured durations', async () => {
    const { user } = await open()
    await run(user)
    const player = screen.getByTestId('stage-player')
    for (const s of scenarioExclusion.stages) {
      await waitFor(() => expect(within(player).getByTestId(`stage-${s.id}`)).toHaveAttribute('data-state', 'done'), { timeout: 3000 })
    }
    const genomic = scenarioExclusion.stages.find((s) => s.id === 'genomic')
    expect(within(player).getByTestId('stage-genomic')).toHaveTextContent(`${genomic.ms} ms (server)`)
  })

  it('renders baseline vs scenario side by side with the excluded variant ghosted and changed systems outlined', async () => {
    const { user } = await open()
    const compare = await run(user)
    expect(compare).toHaveTextContent('Baseline')
    const base = within(within(compare).getAllByTestId('genome-view')[0]).getByTestId(`genome-variant-${ATP7B.variant_id}`)
    const scen = within(within(compare).getAllByTestId('genome-view')[1]).getByTestId(`genome-variant-${ATP7B.variant_id}`)
    expect(base.getAttribute('aria-label')).not.toMatch(/excluded/)
    expect(scen.getAttribute('aria-label')).toMatch(/excluded in scenario/)
    expect(within(compare).getByTestId('impact-hepatic')).toHaveAttribute('data-changed', 'true')
    expect(within(compare).getByTestId('impact-hepatic')).toHaveTextContent('variants 1→0')
    const diff = within(compare).getByTestId('compare-diff')
    expect(diff).toHaveTextContent('Variants analysed')
    expect(diff).toHaveTextContent('→ 7')
  })

  it('reset removes the visual comparison', async () => {
    const { user } = await open()
    await run(user)
    await user.click(screen.getByTestId('reset-scenario'))
    expect(screen.queryByTestId('scenario-compare')).not.toBeInTheDocument()
    expect(screen.queryByTestId('simulation-visual')).not.toBeInTheDocument()
  })

  it('a failed scenario shows an error and no comparison', async () => {
    api.twinCreateScenario.mockRejectedValue(new Error('boom'))
    const { user } = await open()
    const ws = screen.getByTestId('scenario-workspace')
    await user.selectOptions(within(ws).getByLabelText('Variant'), ATP7B.variant_id)
    await user.click(within(ws).getByTestId('run-scenario'))
    expect(await within(ws).findByRole('alert')).toHaveTextContent('boom')
    expect(screen.queryByTestId('scenario-compare')).not.toBeInTheDocument()
  })
})
