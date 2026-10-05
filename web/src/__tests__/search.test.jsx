import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

vi.mock('../api.js', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, api: { searchGlobal: vi.fn() } }
})
import { api, consumeNavContext } from '../api.js'
import { GlobalSearchModal } from '../components/ui/GlobalSearchModal.jsx'

const res = (results, extra = {}) => ({ query: 'wil', total: Object.values(results).flat().length, results, unavailable: [], not_permitted: [], state: 'results', ...extra })

beforeEach(() => vi.clearAllMocks())

describe('Command palette', () => {
  it('searches the backend, navigates with the keyboard and passes context', async () => {
    api.searchGlobal.mockResolvedValue(res({
      commands: [{ type: 'command', id: 'variants', label: 'Variants', sub: 'Go to', route: 'variants', context: {} }],
      genes: [{ type: 'gene', id: 'ATP7B', label: 'ATPase copper transporting beta', sub: 'ATP7B', route: 'kg', context: {} }],
    }))
    const nav = vi.fn(), close = vi.fn()
    render(<GlobalSearchModal isOpen onClose={close} onNavigate={nav} debounceMs={0} />)
    await userEvent.type(screen.getByLabelText('Search'), 'wil')
    expect(await screen.findByText('ATPase copper transporting beta')).toBeTruthy()
    expect(api.searchGlobal).toHaveBeenLastCalledWith('wil')
    await userEvent.keyboard('{ArrowDown}{Enter}')
    expect(nav).toHaveBeenCalledWith('kg')
    expect(close).toHaveBeenCalled()
    expect(consumeNavContext('kg')).toMatchObject({ gene: 'ATP7B' })
  })

  it('shows the distinct no-match state and backend errors; does not query under 2 chars', async () => {
    api.searchGlobal.mockResolvedValue(res({}, { query: 'zzz', state: 'No matching result' }))
    render(<GlobalSearchModal isOpen onClose={() => {}} onNavigate={() => {}} debounceMs={0} />)
    await userEvent.type(screen.getByLabelText('Search'), 'z')
    expect(api.searchGlobal).not.toHaveBeenCalled()
    await userEvent.type(screen.getByLabelText('Search'), 'zz')
    expect((await screen.findByTestId('no-match')).textContent).toMatch(/No matching result for "zzz"/)
    api.searchGlobal.mockRejectedValue(new Error('Session expired'))
    await userEvent.type(screen.getByLabelText('Search'), 'q')
    expect((await screen.findByRole('alert')).textContent).toMatch(/Session expired/)
  })
})
