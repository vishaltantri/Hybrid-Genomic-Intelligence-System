import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

vi.mock('../api.js', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, api: { analytics: vi.fn() }, downloadAnalytics: vi.fn().mockResolvedValue(10) }
})
import { api, downloadAnalytics } from '../api.js'
import AnalyticsView, { BarList, TrendChart } from '../views/AnalyticsView.jsx'

const priv = { identifiers_included: false }
const base = (extra) => ({ range: {}, privacy: priv, state: 'ok', ...extra })
const ZERO = Object.fromEntries(['total_cases', 'active_cases', 'completed_cases', 'variants_in_analyses', 'variants_reviewed', 'diagnosis_runs', 'pgx_analyses', 'reproductive_analyses', 'reports_generated', 'pending_reviews'].map((k) => [k, 0]))

function responses(over = {}) {
  const r = {
    overview: base({ metrics: { ...ZERO, total_cases: 7, pending_reviews: 2 }, definitions: { active_cases: 'x' }, workflow_breakdown: {} }),
    timeseries: base({ title: 'Cases created', interval: 'day', points: [{ bucket: '2026-05-01', count: 2 }], total: 2, state: 'Insufficient data for a trend', note: 'needs 3' }),
    variants: base({ total_variants: 0, acmg: [], acmg_suppressed: 0, genes: [], genes_suppressed: 0, diseases: [], diseases_suppressed: 0, reviewed: 0, unreviewed: 0, state: 'No variant analyses in range' }),
    phenotypes: base({ cases: 7, cases_with_phenotypes: 0, coverage_pct: null, frequencies: [], frequencies_suppressed: 0, cooccurrence: null, cooccurrence_state: 'Insufficient data: x', state: 'No phenotyped cases in range' }),
    diagnoses: base({ top_diagnosis: [], top_diagnosis_suppressed: 0, model_score: { mean_top1: null, n: 0, label: 'Model score' }, unresolved: { no_diagnosis_run: 7, diagnosed_no_final_report: 0, with_final_report: 0 }, state: 'No diagnosis runs in range', note: 'Model score: not a clinical diagnosis' }),
    pgx: base({ analyses_run: {}, pgx_relevant_variants: 0, genes: [], genes_suppressed: 0, state: 'No PGx activity in range' }),
    reproductive: base({ analyses_run: 0, risk_bands: [], risk_bands_suppressed: 0, state: 'No reproductive analyses in range' }),
  }
  return { ...r, ...over }
}
beforeEach(() => { vi.clearAllMocks(); api.analytics.mockImplementation(async (s) => responses()[s]) })

describe('Analytics view', () => {
  it('shows backend numbers, honest empty states and the model-vs-clinical separation', async () => {
    render(<AnalyticsView />)
    expect((await screen.findByTestId('metric-total_cases')).textContent).toBe('7')
    expect(screen.getByTestId('metric-pending_reviews').textContent).toBe('2')
    expect(screen.getAllByTestId('empty-state').map((e) => e.textContent)).toEqual(expect.arrayContaining(['No variant analyses in range', 'No PGx activity in range']))
    expect(screen.getByText('Model score: top-ranked disease')).toBeTruthy()
    expect(screen.getByText('Clinical diagnosis status')).toBeTruthy()
    expect(screen.getAllByTestId('empty-state').some((e) => e.textContent === 'No phenotyped cases in range')).toBe(true)
  })

  it('passes the date range, exports through the backend and surfaces errors', async () => {
    render(<AnalyticsView />)
    await screen.findByTestId('metric-total_cases')
    await userEvent.type(screen.getByLabelText('From date'), '2026-01-01')
    await waitFor(() => expect(api.analytics).toHaveBeenCalledWith('overview', { from: '2026-01-01', to: '' }))
    await userEvent.click(screen.getByLabelText('Export Summary as CSV'))
    expect(downloadAnalytics).toHaveBeenCalledWith('overview', 'csv', { from: '2026-01-01', to: '' })
    api.analytics.mockRejectedValue(new Error("role 'patient' lacks permission 'analytics:read'"))
    await userEvent.click(screen.getByLabelText('Refresh analytics'))
    expect((await screen.findByRole('alert')).textContent).toMatch(/lacks permission/)
  })

  it('charts are accessible and report suppression', () => {
    render(<><BarList rows={[{ label: 'Pathogenic', count: 4 }]} suppressed={3} /><TrendChart title="T" points={[{ bucket: '2026-05-01', count: 2 }]} /></>)
    expect(screen.getByText(/3 observation\(s\).*hidden/)).toBeTruthy()
    expect(screen.getByRole('img').getAttribute('aria-label')).toMatch(/2026-05-01 2/)
  })
})
