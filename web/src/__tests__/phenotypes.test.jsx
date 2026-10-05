import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import search from './fixtures/pheno_search.json'
import term from './fixtures/pheno_term.json'
import pcase from './fixtures/pheno_case.json'
import compare from './fixtures/pheno_compare.json'

vi.mock('../api.js', async (importOriginal) => {
  const actual = await importOriginal()
  const names = ['phenoSearch', 'phenoTerm', 'phenoCase', 'phenoCompare', 'phenoImport', 'listPatients']
  return { ...actual, api: Object.fromEntries(names.map((n) => [n, vi.fn()])) }
})
import { api, setNavContext } from '../api.js'
import PhenotypesView from '../views/PhenotypesView.jsx'

beforeEach(() => {
  vi.clearAllMocks()
  api.listPatients.mockResolvedValue([{ patient_id: pcase.patient_id, name: 'Fx' }])
  api.phenoSearch.mockResolvedValue(search)
  api.phenoTerm.mockResolvedValue(term)
  api.phenoCase.mockResolvedValue(pcase)
  api.phenoCompare.mockResolvedValue(compare)
  api.phenoImport.mockResolvedValue({ present: 1, negated_or_uncertain: 0 })
})

describe('Phenotype Intelligence', () => {
  it('searches HPO with debounce and shows the match type', async () => {
    render(<PhenotypesView />)
    await userEvent.type(screen.getByLabelText('Search HPO terms'), 'tremor')
    const list = await screen.findByTestId('hpo-results')
    expect(within(list).getAllByText('Tremor').length).toBeGreaterThan(0)
    expect(api.phenoSearch).toHaveBeenCalledTimes(1)
    expect(api.phenoSearch).toHaveBeenCalledWith('tremor')
  })

  it('opens term detail with hierarchy and gene chain', async () => {
    render(<PhenotypesView />)
    await userEvent.type(screen.getByLabelText('Search HPO terms'), 'tremor')
    await userEvent.click(await screen.findByRole('button', { name: 'Tremor' }))
    const d = await screen.findByTestId('term-detail')
    expect(d.textContent).toMatch(/Hierarchy/)
    expect(d.textContent).toMatch(/ATP7B/)
  })

  it('shows observed, absent, and not-documented states for a case', async () => {
    render(<PhenotypesView />)
    await userEvent.selectOptions(await screen.findByLabelText('Case'), pcase.patient_id)
    const obs = await screen.findByTestId('observed')
    expect(obs.textContent).toMatch(/Tremor/)
    expect(obs.textContent).toMatch(/Not documented/)
    expect(screen.getByTestId('negated').textContent).toMatch(/Seizure/)
    expect(screen.getByTestId('undocumented').textContent).toMatch(/Not documented/)
  })

  it('compares with a disease using engine output', async () => {
    render(<PhenotypesView />)
    await userEvent.selectOptions(await screen.findByLabelText('Case'), pcase.patient_id)
    await userEvent.click(await within(await screen.findByTestId('compare-panel')).findByRole('button', { name: /Wilson/ }))
    const r = await screen.findByTestId('compare-result')
    expect(r.textContent).toMatch(/Wilson disease/)
    expect(api.phenoCompare).toHaveBeenCalledWith(pcase.patient_id, 'ORPHA:915')
  })

  it('requires explicit confirmation before saving NLP-derived findings', async () => {
    setNavContext('phenotypes', { nlp_import: { present: [{ hpo_id: 'HP:0001337', name: 'Tremor' }], absent: [], possible: [], conflicts: [] } })
    render(<PhenotypesView />)
    const box = await screen.findByTestId('nlp-import')
    expect(api.phenoImport).not.toHaveBeenCalled()
    expect(within(box).getByRole('button', { name: /Confirm/ }).disabled).toBe(true)
    await userEvent.selectOptions(screen.getByLabelText('Case'), pcase.patient_id)
    await userEvent.click(within(box).getByRole('button', { name: /Confirm/ }))
    await waitFor(() => expect(api.phenoImport).toHaveBeenCalledWith(pcase.patient_id, [{ hpo_id: 'HP:0001337', assertion: 'present', evidence_text: undefined }]))
  })
})
