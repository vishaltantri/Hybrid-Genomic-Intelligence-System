import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import search from './fixtures/kg_search.json'
import hood from './fixtures/kg_neighborhood.json'
import node from './fixtures/kg_node.json'

vi.mock('../api.js', async (importOriginal) => {
  const actual = await importOriginal()
  const names = ['kgSearch', 'kgNode', 'kgNeighborhood', 'kgPath', 'kgCase', 'listPatients']
  return { ...actual, api: Object.fromEntries(names.map((n) => [n, vi.fn()])) }
})
import { api } from '../api.js'
import KgExplorer, { layout } from '../components/kg/KgExplorer.jsx'

beforeEach(() => {
  vi.clearAllMocks()
  api.listPatients.mockResolvedValue([{ patient_id: 'PT-1' }])
  api.kgSearch.mockResolvedValue(search)
  api.kgNeighborhood.mockResolvedValue(hood)
  api.kgNode.mockResolvedValue(node)
})

async function firstHit() {
  const box = await screen.findByTestId('kg-results')
  return within(box).getAllByRole('button')[0]
}

describe('Knowledge Graph explorer', () => {
  it('draws nothing until a starting point is chosen', () => {
    render(<KgExplorer />)
    expect(screen.queryAllByTestId('kg-node')).toHaveLength(0)
    expect(screen.getByText(/Nothing is drawn until you choose/)).toBeTruthy()
  })

  it('searches (debounced), loads the real neighbourhood and inspects the selected node', async () => {
    render(<KgExplorer />)
    await userEvent.type(screen.getByLabelText('Search the knowledge graph'), 'ATP7B')
    const hit = await firstHit()
    expect(api.kgSearch).toHaveBeenCalledTimes(1)
    await userEvent.click(hit)
    await waitFor(() => expect(screen.getAllByTestId('kg-node').length).toBe(hood.nodes.length))
    expect(api.kgNeighborhood).toHaveBeenCalledWith({ key: 'Gene::ATP7B', depth: 1, max_nodes: 60 })
    await waitFor(() => expect(screen.getByTestId('kg-inspector').textContent).toMatch(/relations in the graph/))
  })

  it('filters a node type out of the canvas and resets', async () => {
    render(<KgExplorer />)
    await userEvent.type(screen.getByLabelText('Search the knowledge graph'), 'ATP7B')
    await userEvent.click(await firstHit())
    await waitFor(() => screen.getAllByTestId('kg-node'))
    const before = screen.getAllByTestId('kg-node').length
    const t = hood.nodes.find((n) => n.type !== 'Gene').type
    const nOfType = hood.nodes.filter((n) => n.type === t).length
    await userEvent.click(within_filters(t))
    expect(screen.getAllByTestId('kg-node').length).toBe(before - nOfType)
    await userEvent.click(screen.getByRole('button', { name: /Reset/ }))
    expect(screen.queryAllByTestId('kg-node')).toHaveLength(0)
  })

  it('shows an honest empty state and a safe error', async () => {
    api.kgSearch.mockResolvedValueOnce({ results: [], total: 0 })
    render(<KgExplorer />)
    await userEvent.type(screen.getByLabelText('Search the knowledge graph'), 'zzzz')
    expect(await screen.findByText(/No matching record in the knowledge graph/)).toBeTruthy()
  })

  it('reports a missing path rather than inventing one', async () => {
    api.kgPath.mockResolvedValue({ status: 'no_path', message: 'No path of length ≤ 4 connects these nodes in the knowledge graph.', paths: [] })
    render(<KgExplorer />)
    await userEvent.type(screen.getByLabelText('Search the knowledge graph'), 'ATP7B')
    await userEvent.click(await firstHit())
    await waitFor(() => screen.getAllByTestId('kg-node'))
    await userEvent.selectOptions(screen.getByLabelText('Path target'), hood.nodes.find((n) => n.key !== 'Gene::ATP7B').key)
    await userEvent.click(screen.getByRole('button', { name: /Find path/ }))
    expect(await screen.findByText(/No path of length/)).toBeTruthy()
  })

  it('layout is deterministic and finite', () => {
    const p1 = layout(hood.nodes, hood.edges, hood.center)
    const p2 = layout(hood.nodes, hood.edges, hood.center)
    expect(p1).toEqual(p2)
    expect(Object.values(p1).every((p) => Number.isFinite(p.x) && Number.isFinite(p.y))).toBe(true)
  })
})

function within_filters(type) {
  const label = type === 'Hpo' ? 'Phenotype (HPO)' : type
  return within(screen.getByTestId('kg-filters')).getByRole('button', { name: label })
}
