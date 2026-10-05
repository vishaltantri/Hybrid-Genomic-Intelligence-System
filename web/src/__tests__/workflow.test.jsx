import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

vi.mock('../api.js', async (importOriginal) => {
  const actual = await importOriginal()
  const names = ['notifList', 'notifCount', 'notifRead', 'notifReadAll', 'listPatients', 'wfGet', 'wfStatus', 'wfAssign']
  return { ...actual, api: Object.fromEntries(names.map((n) => [n, vi.fn()])) }
})
import { api } from '../api.js'
import NotificationBell from '../components/NotificationBell.jsx'
import CaseWorkflowPanel from '../components/CaseWorkflowPanel.jsx'

const note = { id: 'NTF-1', kind: 'assignment', title: 'Case P1 assigned to you', body: 'please review', case_id: 'P1', created_utc: '2026-01-01T00:00:00Z', read_utc: null }

beforeEach(() => {
  vi.clearAllMocks()
  let read = false
  api.notifList.mockImplementation(async () => [{ ...note, read_utc: read ? 'now' : null }])
  api.notifCount.mockImplementation(async () => ({ unread: read ? 0 : 1 }))
  api.notifRead.mockImplementation(async () => { read = true; return { id: 'NTF-1', read: true } })
  api.notifReadAll.mockImplementation(async () => { read = true; return { marked: 1 } })
})

describe('Notification bell', () => {
  it('shows the real unread count, lists items and clears the badge once read', async () => {
    render(<NotificationBell pollMs={0} />)
    expect(await screen.findByTestId('notif-badge')).toHaveTextContent('1')
    await userEvent.click(screen.getByRole('button', { name: /Notifications, 1 unread/ }))
    await userEvent.click(await screen.findByText('Case P1 assigned to you'))
    expect(api.notifRead).toHaveBeenCalledWith('NTF-1')
    await waitFor(() => expect(screen.queryByTestId('notif-badge')).toBeNull())
  })

  it('shows an empty state and backend errors', async () => {
    api.notifList.mockResolvedValue([])
    api.notifCount.mockResolvedValue({ unread: 0 })
    render(<NotificationBell pollMs={0} />)
    await userEvent.click(await screen.findByRole('button', { name: /Notifications, 0 unread/ }))
    expect(await screen.findByText('No notifications.')).toBeTruthy()
    api.notifCount.mockRejectedValue(new Error('Session expired'))
    await userEvent.click(screen.getByRole('button', { name: /Notifications/ }))
    await userEvent.click(screen.getByRole('button', { name: /Notifications/ }))
    expect((await screen.findByRole('alert')).textContent).toMatch(/Session expired/)
  })
})

describe('Case workflow panel', () => {
  const wf = { case_id: 'P1', status: 'new', assignee: null, history: [], allowed_next: ['closed', 'in_review'] }
  it('offers only backend-allowed transitions, assigns, and shows the history', async () => {
    api.listPatients.mockResolvedValue([{ patient_id: 'P1' }])
    api.wfGet.mockResolvedValueOnce(wf).mockResolvedValue({ ...wf, status: 'in_review', allowed_next: ['closed'], assignee: 'drb',
      history: [{ id: 1, utc: 'u', actor: 'clinician', action: 'status', from_value: 'new', to_value: 'in_review', note: 'go' }] })
    api.wfStatus.mockResolvedValue({}); api.wfAssign.mockResolvedValue({})
    render(<CaseWorkflowPanel />)
    await userEvent.selectOptions(await screen.findByLabelText('Workflow case'), 'P1')
    expect(await screen.findByTestId('wf-state')).toHaveTextContent(/New.*Not assigned/)
    expect(screen.queryByRole('button', { name: /Report ready/ })).toBeNull()
    await userEvent.type(screen.getByLabelText('Workflow note'), 'go')
    await userEvent.click(screen.getByRole('button', { name: 'Move to In review' }))
    expect(api.wfStatus).toHaveBeenCalledWith('P1', { status: 'in_review', note: 'go' })
    expect(await screen.findByTestId('wf-history')).toHaveTextContent(/new → in_review/)
    await userEvent.type(screen.getByLabelText('Assignee username'), 'drb')
    await userEvent.click(screen.getByRole('button', { name: 'Assign' }))
    expect(api.wfAssign).toHaveBeenCalledWith('P1', { assignee: 'drb', note: '' })
  })

  it('surfaces a rejected transition', async () => {
    api.listPatients.mockResolvedValue([{ patient_id: 'P1' }])
    api.wfGet.mockResolvedValue(wf)
    api.wfStatus.mockRejectedValue(new Error("Cannot move a case from 'new' to 'closed'."))
    render(<CaseWorkflowPanel />)
    await userEvent.selectOptions(await screen.findByLabelText('Workflow case'), 'P1')
    await userEvent.click(await screen.findByRole('button', { name: 'Move to Closed' }))
    expect((await screen.findByRole('alert')).textContent).toMatch(/Cannot move/)
  })
})
