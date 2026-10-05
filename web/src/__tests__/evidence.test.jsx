import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import search from './fixtures/evidence_search.json'
import sources from './fixtures/evidence_sources.json'

vi.mock('../api.js', async (importOriginal) => {
  const actual = await importOriginal()
  const names = ['evidenceSources', 'evidenceSearch', 'evidenceVariant', 'evidenceCase', 'evidenceSave', 'evidencePatch', 'evidenceDelete', 'listPatients']
  return { ...actual, api: Object.fromEntries(names.map((n) => [n, vi.fn()])) }
})
import { api } from '../api.js'
import EvidenceView from '../views/EvidenceView.jsx'

beforeEach(() => {
  vi.clearAllMocks()
  api.evidenceSources.mockResolvedValue(sources)
  api.listPatients.mockResolvedValue([{ patient_id: 'PT-1' }])
  api.evidenceCase.mockResolvedValue({ items: [] })
  api.evidenceSearch.mockResolvedValue(search)
})

describe('Evidence & Literature', () => {
  it('shows honest source status including ClinGen not configured', async () => {
    render(<EvidenceView />)
    expect(await screen.findByText(/ClinGen: not configured/)).toBeTruthy()
    expect(screen.getByText(/Nothing is shown until a query is run/)).toBeTruthy()
  })

  it('renders real PubMed cards with PMID and relevance note', async () => {
    render(<EvidenceView />)
    await userEvent.type(screen.getByLabelText('Search literature'), 'ATP7B Wilson')
    await userEvent.click(screen.getByRole('button', { name: /^Search$/ }))
    const cards = await screen.findAllByTestId('evidence-card')
    expect(cards).toHaveLength(search.results.length)
    expect(screen.getAllByText(new RegExp(`PMID ${search.results[0].pmid}`)).length).toBeGreaterThan(0)
  })

  it('shows unavailable distinctly and never fabricates results', async () => {
    api.evidenceSearch.mockResolvedValue({ status: 'unavailable', results: [], total: 0, message: 'PubMed timed out' })
    render(<EvidenceView />)
    await userEvent.type(screen.getByLabelText('Search literature'), 'ATP7B')
    await userEvent.click(screen.getByRole('button', { name: /^Search$/ }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/Literature unavailable/)
    expect(screen.queryAllByTestId('evidence-card')).toHaveLength(0)
  })

  it('shows no-results state', async () => {
    api.evidenceSearch.mockResolvedValue({ status: 'no_results', results: [], total: 0 })
    render(<EvidenceView />)
    await userEvent.type(screen.getByLabelText('Search literature'), 'zzzz')
    await userEvent.click(screen.getByRole('button', { name: /^Search$/ }))
    expect(await screen.findByText(/No matching publications found/)).toBeTruthy()
  })

  it('saves to a case after selecting one', async () => {
    api.evidenceSave.mockResolvedValue({})
    render(<EvidenceView />)
    await userEvent.selectOptions(await screen.findByLabelText('Case'), 'PT-1')
    await userEvent.type(screen.getByLabelText('Search literature'), 'ATP7B')
    await userEvent.click(screen.getByRole('button', { name: /^Search$/ }))
    const btns = await screen.findAllByRole('button', { name: /Save to case/ })
    await userEvent.click(btns[0])
    await waitFor(() => expect(api.evidenceSave).toHaveBeenCalledWith('PT-1', expect.objectContaining({ in_report: false })))
  })

  it('expands provenance', async () => {
    render(<EvidenceView />)
    await userEvent.type(screen.getByLabelText('Search literature'), 'ATP7B')
    await userEvent.click(screen.getByRole('button', { name: /^Search$/ }))
    await userEvent.click((await screen.findAllByText(/Abstract & provenance/))[0])
    expect(screen.getByTestId('evidence-provenance')).toHaveTextContent(/NCBI E-utilities/)
  })
})
