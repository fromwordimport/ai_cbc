import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import PersonaManager from '@/pages/PersonaManager'

const getPersonas = vi.fn()
const generatePersonas = vi.fn()
const deletePersona = vi.fn()

vi.mock('@/services/api', () => ({
  getPersonas: (...args: any[]) => getPersonas(...args),
  generatePersonas: (...args: any[]) => generatePersonas(...args),
  deletePersona: (...args: any[]) => deletePersona(...args),
}))

vi.mock('antd', async () => {
  const actual = await vi.importActual('antd')
  return {
    ...actual,
    message: {
      success: vi.fn(),
      error: vi.fn(),
      warning: vi.fn(),
    },
  }
})

describe('PersonaManager', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  const renderPage = () =>
    render(
      <MemoryRouter>
        <PersonaManager />
      </MemoryRouter>,
    )

  it('renders persona list', async () => {
    getPersonas.mockResolvedValue({
      personas: [
        { persona_id: 'p1', segment: 'A', life_stage: '青年', city_tier: '一线', income_bracket: '高', authenticity_score: 9.5, bias_audit_status: 'PASS' },
      ],
      total: 1,
    })

    renderPage()
    await waitFor(() => expect(screen.getByText('p1')).toBeInTheDocument())
    expect(screen.getByText('A')).toBeInTheDocument()
  })

  it('deletes persona after confirm', async () => {
    getPersonas.mockResolvedValue({
      personas: [{ persona_id: 'p1', segment: 'A', life_stage: '', city_tier: '', income_bracket: '', authenticity_score: null, bias_audit_status: 'PENDING' }],
      total: 1,
    })
    deletePersona.mockResolvedValue(undefined)

    renderPage()
    await waitFor(() => expect(screen.getByText('删除')).toBeInTheDocument())
    fireEvent.click(screen.getByText('删除'))
    await waitFor(() => expect(screen.getByRole('button', { name: '确认删除' })).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: '确认删除' }))
    await waitFor(() => expect(deletePersona).toHaveBeenCalledWith('p1'))
  })

  it('opens generate modal and submits', async () => {
    getPersonas.mockResolvedValue({ personas: [], total: 0 })
    generatePersonas.mockResolvedValue({ generated: 5 })

    renderPage()
    await waitFor(() => expect(screen.getByText('批量生成')).toBeInTheDocument())
    fireEvent.click(screen.getByText('批量生成'))
    await waitFor(() => expect(screen.getByText('批量生成虚拟消费者')).toBeInTheDocument())

    fireEvent.change(screen.getByPlaceholderText('例如：dishwasher-2024q3'), { target: { value: 's1' } })
    fireEvent.click(screen.getByText('开始生成'))
    await waitFor(() => expect(generatePersonas).toHaveBeenCalledWith({ study_id: 's1', count: 2 }))
  })
})
