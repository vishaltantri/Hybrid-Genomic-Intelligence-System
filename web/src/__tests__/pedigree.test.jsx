import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, within, waitFor, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

// Fixtures are real payloads captured from the running backend for the synthetic demo trio (verified VCF).
import pedTrio from './fixtures/pedigree_trio.json'
import anaAtp7b from './fixtures/pedigree_analysis_atp7b.json'
import anaVhl from './fixtures/pedigree_analysis_vhl.json'
import prio from './fixtures/pedigree_prioritization.json'
import repro from './fixtures/pedigree_repro.json'

vi.mock('../api.js', async (importOriginal) => {
  const actual = await importOriginal()
  const names = ['listPatients', 'pedigree', 'pedigreeAddMember', 'pedigreePatchMember', 'pedigreeDeleteMember', 'pedigreeSetProband', 'pedigreeSetPhenotypes',
    'pedigreeAddRelationship', 'pedigreeDeleteRelationship', 'pedigreeSetGenotype', 'pedigreeDeleteGenotype', 'pedigreeImportGenotypes', 'pedigreeAnalysis',
    'pedigreeOverview', 'pedigreePrioritization', 'pedigreeReproductive', 'pedigreeDemoFamily', 'pedigreeHpoSearch', 'assistantChat']
  return { ...actual, api: Object.fromEntries(names.map((n) => [n, vi.fn()])) }
})

import { api, consumeNavContext } from '../api.js'
import PedigreeView from '../views/PedigreeView.jsx'

const CASE = pedTrio.case_id
const ATP7B = 'chr13:51943246:C>G'
const VHL = 'chr3:10141973:C>G'
const mem = (label) => pedTrio.members.find((m) => m.label === label)
const EMPTY = { ...pedTrio, members: [], relationships: [], variants: [], proband_id: null, validation: [], synthetic: false, synthetic_banner: null, analyses_available: [] }

function setupApi(ped = pedTrio) {
  api.listPatients.mockResolvedValue([{ patient_id: CASE, age_years: 9, sex: 'F', state: 'Andhra Pradesh' }, { patient_id: 'PT-OTHER', age_years: 30, sex: 'M', state: 'Kerala' }])
  api.pedigree.mockImplementation((id) => Promise.resolve(id === CASE ? ped : { ...EMPTY, case_id: id }))
  api.pedigreeAnalysis.mockImplementation((_, k) => Promise.resolve(k === VHL ? anaVhl : anaAtp7b))
  api.pedigreePrioritization.mockResolvedValue(prio)
  api.pedigreeReproductive.mockResolvedValue(repro)
  api.pedigreeHpoSearch.mockResolvedValue([{ hpo_id: 'HP:0001337', name: 'Tremor' }])
}

async function openCase(ped, onNavigate = vi.fn()) {
  setupApi(ped)
  const user = userEvent.setup()
  render(<PedigreeView onNavigate={onNavigate} />)
  await screen.findByRole('option', { name: new RegExp(CASE) })
  await user.selectOptions(screen.getByLabelText('Case'), CASE)
  await screen.findByTestId('pedigree-canvas')
  return { user, onNavigate }
}

const node = (label) => screen.getByTestId(`ped-node-${mem(label).member_id}`)
const ty = (el) => Number(/translate\(([-\d.]+),([-\d.]+)\)/.exec(el.getAttribute('transform'))[2])

beforeEach(() => {
  vi.clearAllMocks()
  sessionStorage.clear()
  vi.spyOn(window, 'confirm').mockReturnValue(true)
})

describe('Pedigree canvas', () => {
  it('renders every recorded member with standard symbols, the proband and a legend', async () => {
    await openCase()
    expect(screen.getAllByTestId(/^ped-node-/)).toHaveLength(pedTrio.members.length)
    expect(node('Father')).toHaveAttribute('aria-label', expect.stringMatching(/male.*unaffected/))
    expect(node('Mother')).toHaveAttribute('aria-label', expect.stringMatching(/female.*unaffected/))
    expect(node('Proband')).toHaveAttribute('aria-label', expect.stringMatching(/female.*affected.*proband/))
    expect(node('Father').querySelector('rect')).not.toBeNull()          // square = male
    expect(node('Mother').querySelector('circle')).not.toBeNull()        // circle = female
    expect(screen.getByTestId('proband-name')).toHaveTextContent('Proband')
    const legend = screen.getByTestId('pedigree-legend')
    for (const t of ['Male', 'Female', 'Affected', 'Unaffected', 'Proband', 'Deceased']) expect(legend).toHaveTextContent(t)
  })

  it('lays generations out from the recorded relationships (parents above the proband, partners joined)', async () => {
    await openCase()
    expect(ty(node('Father'))).toBe(ty(node('Mother')))
    expect(ty(node('Father'))).toBeLessThan(ty(node('Proband')))
    const kinds = [...document.querySelectorAll('[data-kind]')].map((l) => l.dataset.kind)
    expect(kinds).toContain('partner')
    expect(kinds).toContain('descent')
  })

  it('shows the synthetic/test banner and no validation noise for a complete trio', async () => {
    await openCase()
    expect(screen.getByTestId('synthetic-banner')).toHaveTextContent('Sample Family — Not Clinical Data')
    expect(screen.queryByTestId('validation')).not.toBeInTheDocument()
  })

  it('zooms and fits the canvas', async () => {
    const { user } = await openCase()
    const vp = () => screen.getByTestId('pedigree-viewport')
    const fitted = vp().dataset.zoom
    await user.click(screen.getByTestId('ped-zoom-in'))
    expect(Number(vp().dataset.zoom)).toBeGreaterThan(Number(fitted))
    await user.click(screen.getByTestId('ped-zoom-out'))
    await user.click(screen.getByTestId('ped-zoom-out'))
    expect(Number(vp().dataset.zoom)).toBeLessThan(Number(fitted))
    await user.click(screen.getByTestId('ped-fit'))
    expect(vp().dataset.zoom).toBe(fitted)
  })

  it('persists a dragged position through the backend', async () => {
    api.pedigreePatchMember.mockResolvedValue({})
    await openCase()
    const n = node('Father')
    fireEvent.pointerDown(n, { clientX: 100, clientY: 100, pointerId: 1, button: 0 })
    fireEvent.pointerMove(screen.getByTestId('pedigree-canvas'), { clientX: 160, clientY: 130, pointerId: 1 })
    fireEvent.pointerUp(screen.getByTestId('pedigree-canvas'), { pointerId: 1 })
    await waitFor(() => expect(api.pedigreePatchMember).toHaveBeenCalledWith(CASE, mem('Father').member_id, expect.objectContaining({ layout_x: expect.any(Number), layout_y: expect.any(Number) })))
  })
})

describe('Selection and inspector', () => {
  it('selects a member on click and shows their real counts and relation', async () => {
    const { user } = await openCase()
    await user.click(node('Mother'))
    expect(node('Mother')).toHaveAttribute('data-selected', 'true')
    const insp = screen.getByTestId('member-inspector')
    expect(insp).toHaveTextContent('Mother')
    expect(insp).toHaveTextContent('mother of the proband')
    const counts = within(screen.getByTestId('member-counts'))
    expect(counts.getByText(String(Object.keys(mem('Mother').genotypes).length))).toBeInTheDocument()
  })

  it('selects with the keyboard and deselects by clicking the background', async () => {
    const { user } = await openCase()
    node('Father').focus()
    await user.keyboard('{Enter}')
    expect(node('Father')).toHaveAttribute('data-selected', 'true')
    await user.click(screen.getByRole('group', { name: 'Pedigree canvas' }))
    expect(node('Father')).toHaveAttribute('data-selected', 'false')
  })

  it('sets a new proband only after the backend confirms', async () => {
    api.pedigreeSetProband.mockResolvedValue({})
    const { user } = await openCase()
    await user.click(node('Mother'))
    await user.click(screen.getByTestId('set-proband'))
    await waitFor(() => expect(api.pedigreeSetProband).toHaveBeenCalledWith(CASE, mem('Mother').member_id))
    expect(api.pedigree.mock.calls.length).toBeGreaterThan(1)             // reloaded from the backend
  })

  it('opens the Digital Twin and Variant Intelligence for the selected case', async () => {
    const { user, onNavigate } = await openCase()
    await user.click(node('Proband'))
    await user.click(screen.getByRole('button', { name: 'View Digital Twin' }))
    expect(onNavigate).toHaveBeenCalledWith('digital-twin')
    expect(consumeNavContext('digital-twin')).toMatchObject({ patient_id: CASE })
    await user.click(screen.getByRole('button', { name: 'View Variants' }))
    expect(onNavigate).toHaveBeenCalledWith('variants')
    expect(consumeNavContext('variants')).toMatchObject({ patient_id: CASE })
  })
})

describe('Editing', () => {
  it('adds a member with a relationship through the backend and refreshes', async () => {
    api.pedigreeAddMember.mockResolvedValue({ member_id: 'MEM-NEW' })
    const { user } = await openCase()
    await user.click(node('Proband'))
    await user.click(screen.getByTestId('add-member'))
    const form = screen.getByTestId('add-member-form')
    await user.type(within(form).getByLabelText('Member label'), 'Brother')
    await user.selectOptions(within(form).getByLabelText('Member sex'), 'M')
    await user.selectOptions(within(form).getByLabelText('Member affected status'), 'unaffected')
    await user.selectOptions(within(form).getByLabelText('Relation to selected member'), 'partner')
    await user.click(within(form).getByTestId('add-member-submit'))
    await waitFor(() => expect(api.pedigreeAddMember).toHaveBeenCalledWith(CASE, expect.objectContaining({
      label: 'Brother', sex: 'M', affected: 'unaffected', relation: { to: mem('Proband').member_id, type: 'partner' },
    })))
    await waitFor(() => expect(screen.queryByTestId('add-member-form')).not.toBeInTheDocument())
    expect(api.pedigree.mock.calls.length).toBeGreaterThan(1)
  })

  it('shows the backend validation message and keeps the form when a member cannot be saved', async () => {
    api.pedigreeAddMember.mockRejectedValue(new Error('That would make a member their own ancestor'))
    const { user } = await openCase()
    await user.click(screen.getByTestId('add-member'))
    const form = screen.getByTestId('add-member-form')
    await user.type(within(form).getByLabelText('Member label'), 'X')
    await user.click(within(form).getByTestId('add-member-submit'))
    expect(await within(form).findByRole('alert')).toHaveTextContent('own ancestor')
    expect(screen.getByTestId('add-member-form')).toBeInTheDocument()
  })

  it('creates a relationship between two members', async () => {
    api.pedigreeAddRelationship.mockResolvedValue({})
    const { user } = await openCase()
    await user.click(node('Father'))
    const rels = screen.getByTestId('member-relationships')
    await user.selectOptions(within(rels).getByLabelText('Relationship type'), 'parent')
    await user.selectOptions(within(rels).getByLabelText('Relationship member'), mem('Proband').member_id)
    await user.click(within(rels).getByTestId('connect-members'))
    await waitFor(() => expect(api.pedigreeAddRelationship).toHaveBeenCalledWith(CASE, { type: 'parent', member_a: mem('Father').member_id, member_b: mem('Proband').member_id }))
  })

  it('does not report success when a relationship is rejected', async () => {
    api.pedigreeAddRelationship.mockRejectedValue(new Error('This relationship already exists.'))
    const { user } = await openCase()
    await user.click(node('Father'))
    const rels = screen.getByTestId('member-relationships')
    await user.selectOptions(within(rels).getByLabelText('Relationship member'), mem('Mother').member_id)
    await user.click(within(rels).getByTestId('connect-members'))
    expect(await screen.findByRole('alert')).toHaveTextContent('already exists')
    expect(api.pedigree.mock.calls.length).toBe(1)                          // no reload: nothing changed
  })

  it('assigns a phenotype from the HPO search and a genotype from a registered variant', async () => {
    api.pedigreeSetPhenotypes.mockResolvedValue({})
    api.pedigreeSetGenotype.mockResolvedValue({})
    const { user } = await openCase()
    await user.click(node('Proband'))
    const ph = screen.getByTestId('member-phenotypes')
    api.pedigreeHpoSearch.mockResolvedValue([{ hpo_id: 'HP:0001250', name: 'Seizures' }])
    await user.type(within(ph).getByLabelText('Search HPO term'), 'seiz')
    await user.click(await within(ph).findByRole('button', { name: /Seizures/ }))
    await waitFor(() => expect(api.pedigreeSetPhenotypes).toHaveBeenCalledWith(CASE, mem('Proband').member_id, [...mem('Proband').hpo_ids, 'HP:0001250']))
    const g = screen.getByTestId('member-genotypes')
    await user.selectOptions(within(g).getByLabelText('Genotype variant'), ATP7B)
    await user.selectOptions(within(g).getByLabelText('Genotype value'), '0/1')
    await user.click(within(g).getByTestId('genotype-assign'))
    await waitFor(() => expect(api.pedigreeSetGenotype).toHaveBeenCalledWith(CASE, mem('Proband').member_id, { genotype: '0/1', variant_key: ATP7B }))
  })

  it('deletes a member only after confirmation and surfaces proband protection', async () => {
    api.pedigreeDeleteMember.mockRejectedValue(new Error('The proband cannot be deleted while other members exist'))
    const { user } = await openCase()
    await user.click(node('Proband'))
    await user.click(screen.getByTestId('delete-member'))
    expect(window.confirm).toHaveBeenCalled()
    expect(await screen.findByRole('alert')).toHaveTextContent('proband cannot be deleted')
  })
})

describe('Variant-focused mode and analysis', () => {
  async function analyse(user, key = ATP7B) {
    await user.selectOptions(screen.getByLabelText('Selected variant'), key)
    return screen.findByTestId('inheritance-result')
  }

  it('highlights carriers, non-carriers and unknown genotypes from real genotype data', async () => {
    const { user } = await openCase()
    await analyse(user)
    expect(api.pedigreeAnalysis).toHaveBeenCalledWith(CASE, ATP7B)
    expect(screen.getByTestId('variant-mode-banner')).toHaveTextContent('ATP7B')
    expect(node('Proband')).toHaveAttribute('data-genotype', 'hom')
    expect(node('Mother')).toHaveAttribute('data-genotype', 'het')
    expect(node('Father')).toHaveAttribute('data-genotype', 'het')
    expect(node('Proband')).toHaveTextContent('hom')
    expect(screen.getByTestId('pedigree-legend')).toHaveTextContent('Genotype unknown')
    await user.click(screen.getByRole('button', { name: /Clear variant/ }))
    expect(node('Proband')).not.toHaveAttribute('data-genotype')
  })

  it('marks members without a recorded genotype as unknown, never as reference', async () => {
    const ped = JSON.parse(JSON.stringify(pedTrio))
    delete ped.members.find((m) => m.label === 'Father').genotypes[ATP7B]
    const { user } = await openCase(ped)
    api.pedigreeAnalysis.mockResolvedValue({ ...anaAtp7b, members: anaAtp7b.members.map((m) => (m.label === 'Father' ? { ...m, state: 'unknown' } : m)) })
    await analyse(user)
    expect(node('Father')).toHaveAttribute('data-genotype', 'unknown')
  })

  it('shows the inheritance verdict, evidence, completeness and the segregation table', async () => {
    const { user } = await openCase()
    await analyse(user)
    expect(screen.getByTestId('most-consistent')).toHaveTextContent('Autosomal recessive (consistent)')
    expect(screen.getByTestId('completeness')).toHaveTextContent(anaAtp7b.completeness.level)
    expect(screen.getByTestId('why')).toHaveTextContent('Both parents are heterozygous carriers')
    expect(within(screen.getByTestId('model-AR')).getAllByText(/./).length).toBeGreaterThan(2)
    await user.click(screen.getByTestId('tab-segregation'))
    const c = anaAtp7b.segregation.counts
    expect(screen.getByTestId('seg-affected-variant')).toHaveTextContent(String(c.affected_carrier))
    expect(screen.getByTestId('seg-unaffected-variant')).toHaveTextContent(String(c.unaffected_carrier))
    expect(screen.getByTestId('trio-Father')).toHaveTextContent('Heterozygous')
    expect(screen.getByTestId('trio-Proband')).toHaveTextContent('Homozygous')
    expect(screen.getByTestId('de-novo')).toHaveTextContent('Inherited')
  })

  it('reports a candidate de novo event with its caveat and never calls it definitive', async () => {
    const { user } = await openCase()
    await analyse(user, VHL)
    await user.click(screen.getByTestId('tab-segregation'))
    const dn = screen.getByTestId('de-novo')
    expect(dn).toHaveTextContent('Candidate de novo')
    expect(dn).toHaveTextContent('confirmatory validation recommended')
    expect(dn).toHaveTextContent('not verified')
  })

  it('shows PP1 as insufficient and does not apply it to the ACMG classification', async () => {
    const { user } = await openCase()
    await analyse(user)
    await user.click(screen.getByTestId('tab-evidence'))
    expect(screen.getByTestId('pp1-status')).toHaveTextContent('Insufficient')
    expect(screen.getByTestId('acmg-preview')).toHaveTextContent('Stored ACMG/AMP classification: Likely pathogenic')
    expect(screen.getByTestId('acmg-preview')).toHaveTextContent('PP1 is not applied')
    expect(screen.getByTestId('pp1')).toHaveTextContent('Pedigree segregation analysis')
    expect(screen.getByTestId('diagnosis-context')).toHaveTextContent('Pedigree pattern: consistent with autosomal recessive')
  })

  it('lists the transparent family prioritisation without altering the base score', async () => {
    const { user } = await openCase()
    await user.click(screen.getByTestId('tab-prioritisation'))
    const panel = await screen.findByTestId('prioritisation')
    const row = prio.rows.find((r) => r.gene === 'VHL')
    expect(within(panel).getByTestId('prio-VHL')).toHaveTextContent(String(row.base_priority_score))
    expect(within(panel).getByTestId('prio-VHL')).toHaveTextContent(String(row.family_adjusted_score))
    expect(panel).toHaveTextContent('never modified')
  })

  it('feeds the pedigree into the reproductive engine on request', async () => {
    const { user } = await openCase()
    await user.click(screen.getByTestId('tab-repro'))
    await user.click(screen.getByTestId('run-repro'))
    const res = await screen.findByTestId('repro-result')
    expect(api.pedigreeReproductive).toHaveBeenCalledWith(CASE)
    expect(res).toHaveTextContent('Father and Mother')
    expect(res).toHaveTextContent('Wilson disease')
  })

  it('opens Variant Intelligence, the Knowledge Graph and Diagnosis from the analysis', async () => {
    const { user, onNavigate } = await openCase()
    await analyse(user)
    await user.click(screen.getByRole('button', { name: 'Open Variant Intelligence' }))
    expect(consumeNavContext('variants')).toMatchObject({ patient_id: CASE, variant_id: ATP7B })
    await user.click(screen.getByRole('button', { name: 'Open Knowledge Graph' }))
    expect(consumeNavContext('kg')).toMatchObject({ genes: ['ATP7B'] })
    await user.click(screen.getByRole('button', { name: 'Open Diagnosis' }))
    expect(onNavigate).toHaveBeenCalledWith('diagnosis')
  })

  it('asks the AI Assistant with the pedigree and selected variant attached', async () => {
    api.assistantChat.mockResolvedValue({ response: 'grounded', citations: [{ source_type: 'Pedigree', identifier: CASE }], context_summary: { pedigree_variant: ATP7B } })
    const { user } = await openCase()
    await analyse(user)
    const p = screen.getByTestId('pedigree-assistant')
    await user.click(within(p).getByRole('button', { name: 'Could this variant be de novo?' }))
    await user.click(within(p).getByRole('button', { name: /^Ask$/ }))
    await waitFor(() => expect(api.assistantChat).toHaveBeenCalledWith(expect.objectContaining({
      message: 'Could this variant be de novo?', patient_id: CASE, include_pedigree: true, pedigree_variant_key: ATP7B })))
    expect(await within(p).findByText('grounded')).toBeInTheDocument()
  })

  it('shows analysis errors instead of stale results', async () => {
    const { user } = await openCase()
    api.pedigreeAnalysis.mockRejectedValue(new Error('Variant is not registered in this pedigree'))
    await user.selectOptions(screen.getByLabelText('Selected variant'), VHL)
    expect(await screen.findByText(/not registered in this pedigree/)).toBeInTheDocument()
    expect(screen.queryByTestId('inheritance-result')).not.toBeInTheDocument()
  })
})

describe('Empty and error states', () => {
  it('offers the labelled synthetic demo family for an empty pedigree and reloads after creating it', async () => {
    api.pedigreeDemoFamily.mockResolvedValue({})
    const { user } = await openCase(EMPTY)
    expect(screen.getByTestId('empty-pedigree')).toHaveTextContent('sample family')
    await user.click(screen.getByTestId('demo-family'))
    await waitFor(() => expect(api.pedigreeDemoFamily).toHaveBeenCalledWith(CASE))
    expect(api.pedigree.mock.calls.length).toBeGreaterThan(1)
  })

  it('displays server-side validation findings', async () => {
    const ped = { ...pedTrio, validation: [{ severity: 'error', code: 'MULTIPLE_PROBANDS', message: 'More than one proband is marked.', members: [] },
      { severity: 'warning', code: 'NO_PARENT_LINKS', message: 'No parent links.', members: [] }] }
    await openCase(ped)
    const v = screen.getByTestId('validation')
    expect(within(v).getByText(/More than one proband/).closest('[data-severity]')).toHaveAttribute('data-severity', 'error')
    expect(v).toHaveTextContent('No parent links')
  })

  it('shows a load error without leaving a stale pedigree on screen', async () => {
    setupApi()
    api.pedigree.mockRejectedValue(new Error('Case not found'))
    const user = userEvent.setup()
    render(<PedigreeView onNavigate={vi.fn()} />)
    await screen.findByRole('option', { name: new RegExp(CASE) })
    await user.selectOptions(screen.getByLabelText('Case'), CASE)
    expect(await screen.findByRole('alert')).toHaveTextContent('Case not found')
    expect(screen.queryByTestId('pedigree-canvas')).not.toBeInTheDocument()
  })

  it('switching case discards the previous pedigree, selection and analysis', async () => {
    const { user } = await openCase()
    await user.selectOptions(screen.getByLabelText('Selected variant'), ATP7B)
    await screen.findByTestId('inheritance-result')
    await user.selectOptions(screen.getByLabelText('Case'), 'PT-OTHER')
    await waitFor(() => expect(api.pedigree).toHaveBeenLastCalledWith('PT-OTHER'))
    await screen.findByTestId('empty-pedigree')
    expect(screen.queryByTestId('inheritance-result')).not.toBeInTheDocument()
    expect(screen.queryAllByTestId(/^ped-node-/)).toHaveLength(0)
  })
})
