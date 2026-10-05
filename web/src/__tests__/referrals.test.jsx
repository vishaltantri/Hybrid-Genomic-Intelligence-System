import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import created from './fixtures/ref_created.json'
import worse from './fixtures/ref_worse.json'
import summary from './fixtures/ref_summary.json'

vi.mock('../api.js', async (importOriginal) => {
  const actual = await importOriginal()
  const names = ['refCreateText', 'refList', 'refSummary', 'refFollowUp', 'refHandoff']
  return { ...actual, api: Object.fromEntries(names.map((n) => [n, vi.fn()])) }
})
import { api } from '../api.js'
import ReferralsPanel from '../components/ReferralsPanel.jsx'

beforeEach(() => {
  vi.clearAllMocks()
  api.refList.mockResolvedValue([])
  api.refSummary.mockResolvedValue({ ...summary, total: 0 })
  api.refCreateText.mockResolvedValue(created)
  api.refFollowUp.mockResolvedValue(worse)
  api.refHandoff.mockRejectedValue(new Error("role 'asha' lacks permission 'referral:handoff'"))
})

describe('ASHA referrals', () => {
  it('creates a referral from the server result and shows the Hindi directive', async () => {
    render(<ReferralsPanel />)
    expect(await screen.findByText(/No referrals yet/)).toBeTruthy()
    await userEvent.type(screen.getByLabelText('Referral transcript'), 'bachche ko daura aate hain')
    await userEvent.click(screen.getByRole('button', { name: 'Create referral' }))
    const d = await screen.findByTestId('ref-detail')
    expect(d).toHaveTextContent(created.referral_id)
    expect(d.querySelector('[lang="hi"]').textContent).toBe(created.action.hi)
    expect(api.refCreateText.mock.calls[0][0].transcript).toMatch(/daura/)
  })

  it('records follow-up and surfaces backend errors for handoff', async () => {
    render(<ReferralsPanel />)
    await userEvent.type(await screen.findByLabelText('Referral transcript'), 'x')
    await userEvent.click(screen.getByRole('button', { name: 'Create referral' }))
    await screen.findByTestId('ref-detail')
    await userEvent.selectOptions(screen.getByLabelText('Follow-up outcome'), 'worse')
    await userEvent.click(screen.getByRole('button', { name: 'Record follow-up' }))
    expect(api.refFollowUp).toHaveBeenCalledWith(created.referral_id, { outcome: 'worse', note: '' })
    expect(await screen.findByText(/fever/)).toBeTruthy()
    await userEvent.click(screen.getByRole('button', { name: /Hand off/ }))
    expect((await screen.findByRole('alert')).textContent).toMatch(/lacks permission/)
  })
})
