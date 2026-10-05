import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import analysis from './fixtures/nlp_analyze.json'

vi.mock('../api.js', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, api: { nlpAnalyze: vi.fn() } }
})
import { api } from '../api.js'
import ClinicalTextView from '../views/ClinicalTextView.jsx'

beforeEach(() => {
  vi.clearAllMocks()
  api.nlpAnalyze.mockResolvedValue(analysis)
})

async function run() {
  render(<ClinicalTextView />)
  await userEvent.type(screen.getByLabelText('Clinical note'), analysis.text)
  await userEvent.click(screen.getByRole('button', { name: /Analyse text/ }))
  await screen.findByTestId('nlp-highlighted')
}

describe('Clinical Text Intelligence', () => {
  it('disables analyse until text is entered', () => {
    render(<ClinicalTextView />)
    expect(screen.getByRole('button', { name: /Analyse text/ }).disabled).toBe(true)
  })

  it('highlights entities and marks negation', async () => {
    await run()
    const spans = screen.getAllByTestId('nlp-span')
    expect(spans.length).toBeGreaterThan(5)
    expect(spans.some((s) => s.dataset.assertion === 'absent')).toBe(true)
    expect(api.nlpAnalyze).toHaveBeenCalledWith({ text: analysis.text })
  })

  it('shows normalised HPO concept and family context', async () => {
    await run()
    expect(screen.getAllByText(/HP:0000952/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/Family: mother/).length).toBeGreaterThan(0)
    expect(screen.getByTestId('nlp-summary').textContent).toMatch(/Not extracted: PROCEDURE, ANATOMICAL_SITE/)
  })

  it('shows a safe error when analysis fails', async () => {
    api.nlpAnalyze.mockRejectedValue(new Error('boom'))
    render(<ClinicalTextView />)
    await userEvent.type(screen.getByLabelText('Clinical note'), 'tremor')
    await userEvent.click(screen.getByRole('button', { name: /Analyse text/ }))
    await waitFor(() => expect(screen.getByRole('alert').textContent).toMatch(/boom/))
  })
})
