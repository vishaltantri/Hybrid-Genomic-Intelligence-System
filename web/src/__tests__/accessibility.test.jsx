import React from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import AppShell from '../components/AppShell.jsx'

vi.mock('../api.js', async (orig) => ({ ...(await orig()), apiGet: vi.fn().mockResolvedValue({}) }))

const user = { username: 'doc', role: 'doctor' }

function shell(route = 'patients', onRouteChange = () => {}) {
  return render(
    <AppShell activeRoute={route} onRouteChange={onRouteChange} user={user} onLogout={() => {}}>
      <h1>Content</h1>
    </AppShell>,
  )
}

describe('shell accessibility', () => {
  it('has skip link, labelled main landmark and navigation landmark', () => {
    shell()
    expect(screen.getByText('Skip to main content')).toBeTruthy()
    expect(screen.getByRole('main')).toBeTruthy()
    expect(screen.getByRole('navigation', { name: 'Main navigation' })).toBeTruthy()
  })

  it('marks only the active route with aria-current', () => {
    shell('patients')
    const current = document.querySelectorAll('[aria-current="page"]')
    expect(current.length).toBe(1)
    expect(current[0].textContent).toContain('Patients')
  })

  it('every button in the shell has an accessible name', () => {
    shell()
    const unnamed = [...document.querySelectorAll('button')].filter(
      (b) => !(b.textContent.trim() || b.getAttribute('aria-label') || b.title),
    )
    expect(unnamed).toEqual([])
  })

  it('search trigger is a real button reachable by keyboard', () => {
    shell()
    const btn = screen.getByRole('button', { name: /open search/i })
    expect(btn.tabIndex).toBeGreaterThanOrEqual(0)
  })

  it('navigating from the sidebar calls onRouteChange', () => {
    const go = vi.fn()
    shell('patients', go)
    fireEvent.click(screen.getByRole('button', { name: /Analytics/ }))
    expect(go).toHaveBeenCalledWith('analytics')
  })
})
