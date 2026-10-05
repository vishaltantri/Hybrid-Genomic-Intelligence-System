import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import exported from './fixtures/fhir_export.json'
import abdm from './fixtures/abdm_status.json'
import preview from './fixtures/fhir_preview.json'

vi.mock('../api.js', async (importOriginal) => {
  const actual = await importOriginal()
  const names = ['fhirMetadata', 'abdmStatus', 'listPatients', 'fhirCaseExport', 'fhirImportPreview']
  return { ...actual, api: Object.fromEntries(names.map((n) => [n, vi.fn()])) }
})
import { api } from '../api.js'
import FhirView from '../views/FhirView.jsx'

beforeEach(() => {
  vi.clearAllMocks()
  api.fhirMetadata.mockResolvedValue({ resourceType: 'CapabilityStatement' })
  api.abdmStatus.mockResolvedValue(abdm)
  api.listPatients.mockResolvedValue([{ patient_id: 'P1', name: 'Fx' }])
  api.fhirCaseExport.mockResolvedValue(exported)
  api.fhirImportPreview.mockResolvedValue(preview)
})

describe('FHIR view', () => {
  it('shows ABDM as not connected and the structural-only validation scope on export', async () => {
    render(<FhirView />)
    expect(await screen.findByTestId('abdm-status')).toHaveTextContent(/Not connected/)
    await userEvent.selectOptions(await screen.findByLabelText('FHIR case'), 'P1')
    const v = await screen.findByTestId('fhir-validation')
    expect(v).toHaveTextContent(/Structurally valid/)
    expect(v).toHaveTextContent(/Not validated against NRCeS/)
    expect(api.fhirCaseExport).toHaveBeenCalledWith('P1')
  })

  it('rejects non-JSON locally and previews a valid Bundle without persisting', async () => {
    render(<FhirView />)
    const box = await screen.findByLabelText('FHIR Bundle JSON')
    await userEvent.type(box, 'not json')
    await userEvent.click(screen.getByRole('button', { name: 'Validate and preview' }))
    expect((await screen.findByRole('alert')).textContent).toMatch(/not valid JSON/)
    expect(api.fhirImportPreview).not.toHaveBeenCalled()
    await userEvent.clear(box)
    await userEvent.click(box)
    await userEvent.paste('{"resourceType":"Bundle","type":"collection"}')
    await userEvent.click(screen.getByRole('button', { name: 'Validate and preview' }))
    expect(await screen.findByText(/Nothing was written/)).toBeTruthy()
    expect(api.fhirImportPreview).toHaveBeenCalledTimes(1)
  })
})
