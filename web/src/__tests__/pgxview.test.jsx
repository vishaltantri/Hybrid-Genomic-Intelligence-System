import React from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import check from './fixtures/pgx_check.json'

vi.mock('../api.js', async (importOriginal) => {
  const actual = await importOriginal()
  const names = ['pgxCoverage', 'pgxCheck', 'listPatients', 'pgxCase', 'pgxCaseDrug']
  return { ...actual, api: Object.fromEntries(names.map((n) => [n, vi.fn(async () => ({}))])) }
})
import { api } from '../api.js'
import PgxView from '../views/PgxView.jsx'

describe('PGx prescription screening', () => {
  it('renders the real check response instead of a blank page', async () => {
    api.pgxCoverage.mockResolvedValue({ rows: [] })
    api.listPatients.mockResolvedValue([])
    api.pgxCheck.mockResolvedValue(check)
    render(<PgxView onNavigate={() => {}} />)
    await userEvent.click(screen.getByRole('button', { name: /Assess Prescription Risk/ }))
    expect(await screen.findByText(/Pharmacogenomic Actionable Alerts/)).toBeTruthy()
  })
})
