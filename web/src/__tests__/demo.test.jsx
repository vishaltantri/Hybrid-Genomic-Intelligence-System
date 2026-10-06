import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

const steps = [
  { id: 'patient', label: 'Explore patient', route: 'patients', done: true, detail: 'Sample patient record' },
  { id: 'pgx', label: 'Review pharmacogenomics', route: 'pgx', done: true, detail: 'From the VCF' },
  { id: 'reports', label: 'Generate report', route: 'reports', done: false, detail: '0 report version(s)' },
]
vi.mock('../api.js', () => ({
  api: { demoStatus: vi.fn(), demoSeed: vi.fn(), demoReset: vi.fn() },
  setNavContext: vi.fn(),
}))
import { api, setNavContext } from '../api.js'
import DemoView from '../views/DemoView.jsx'

beforeEach(() => { Object.values(api).forEach((f) => f.mockReset()); setNavContext.mockReset() })

describe('DemoView', () => {
  it('offers to create the case when none exists, then shows the real steps', async () => {
    api.demoStatus.mockResolvedValueOnce({ exists: false, steps: [], notice: 'sample' })
      .mockResolvedValue({ exists: true, case_id: 'CASE-DOC', steps, notice: 'sample' })
    api.demoSeed.mockResolvedValue({})
    const onActive = vi.fn()
    render(<DemoView onNavigate={() => {}} onDemoActive={onActive} />)
    fireEvent.click(await screen.findByRole('button', { name: /create guided case/i }))
    await waitFor(() => expect(screen.getByTestId('demo-case-id').textContent).toBe('CASE-DOC'))
    expect(api.demoSeed).toHaveBeenCalledTimes(1)
    expect(onActive).toHaveBeenCalledWith(true)
    expect(screen.getByText('2 of 3 steps have data')).toBeTruthy()
    expect(screen.getByText('No data yet')).toBeTruthy()
  })

  it('opening a step navigates to the real module with the demo case', async () => {
    api.demoStatus.mockResolvedValue({ exists: true, case_id: 'CASE-DOC', steps })
    const go = vi.fn()
    render(<DemoView onNavigate={go} onDemoActive={() => {}} />)
    const buttons = await screen.findAllByRole('button', { name: 'Open' })
    fireEvent.click(buttons[1])
    expect(setNavContext).toHaveBeenCalledWith('pgx', { patient_id: 'CASE-DOC' })
    expect(go).toHaveBeenCalledWith('pgx')
  })

  it('reset needs confirmation and is not called by the first click', async () => {
    api.demoStatus.mockResolvedValue({ exists: true, case_id: 'CASE-DOC', steps })
    api.demoReset.mockResolvedValue({ reset: true })
    render(<DemoView onNavigate={() => {}} onDemoActive={() => {}} />)
    fireEvent.click(await screen.findByRole('button', { name: /reset guided case/i }))
    expect(api.demoReset).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: /confirm reset/i }))
    await waitFor(() => expect(api.demoReset).toHaveBeenCalledTimes(1))
  })

  it('AI shortcut passes the demo prompt and case', async () => {
    api.demoStatus.mockResolvedValue({ exists: true, case_id: 'CASE-DOC', steps })
    const go = vi.fn()
    render(<DemoView onNavigate={go} onDemoActive={() => {}} />)
    fireEvent.click(await screen.findByRole('button', { name: /ask ai assistant/i }))
    expect(setNavContext).toHaveBeenCalledWith('ai-assistant', expect.objectContaining({ patient_id: 'CASE-DOC', prompt: 'Explain the primary finding in this case.' }))
    expect(go).toHaveBeenCalledWith('ai-assistant')
  })
})
