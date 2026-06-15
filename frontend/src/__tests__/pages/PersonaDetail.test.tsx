import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import PersonaDetail from '@/pages/PersonaDetail'

const getPersona = vi.fn()
const deletePersona = vi.fn()

vi.mock('@/services/api', () => ({
  getPersona: (...args: any[]) => getPersona(...args),
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
      loading: vi.fn(),
    },
  }
})

describe('PersonaDetail', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  const renderPage = () =>
    render(
      <MemoryRouter initialEntries={['/personas/p1']}>
        <Routes>
          <Route path="/personas/:personaId" element={<PersonaDetail />} />
        </Routes>
      </MemoryRouter>,
    )

  it('renders persona details and layers', async () => {
    getPersona.mockResolvedValue({
      persona_id: 'p1',
      segment: 'A',
      authenticity_score: 9.5,
      bias_audit_status: 'PASSED',
      created_at: '2026-06-14',
      generation_metadata: { model: 'deepseek', cost_cny: 0.5 },
      layer1_demographics: { age: 30, gender: '男', city: '北京', income: '20k', occupation: '工程师', education: '本科', marital_status: '已婚', living_type: '自有住房' },
      layer2_behavior: { price_sensitivity: '中', purchase_channels: ['线上'], decision_style: '理性', brand_loyalty: '中', information_source: ['社交媒体'] },
      layer3_psychology: { core_values: ['品质'], core_anxieties: ['时间'], tension_combination: { labels: ['节俭', '享受'], narrative_explanation: '矛盾' }, secret_motivation: '身份认同', defense_mechanism: '合理化' },
      layer4_scenarios: { daily_routine: '上班', purchase_trigger: '促销', stress_response: '购物', social_behavior: '社交' },
      language_samples: ['sample'],
      dishwasher_context: { purchase_constraints: ['空间'], decision_factors: ['价格'], ignored_factors: ['外观'] },
    })

    renderPage()
    await waitFor(() => expect(screen.getByText('画像详情 — p1')).toBeInTheDocument())
    expect(screen.getByText('9.5')).toBeInTheDocument()
    expect(screen.getByText('PASSED')).toBeInTheDocument()
    expect(screen.getByText('工程师')).toBeInTheDocument()
  })

  it('shows not found when persona is null', async () => {
    getPersona.mockResolvedValue(null)
    renderPage()
    await waitFor(() => expect(screen.getByText('画像不存在')).toBeInTheDocument())
  })

  it('deletes persona after confirm', async () => {
    getPersona.mockResolvedValue({ persona_id: 'p1', segment: 'A', authenticity_score: 8, bias_audit_status: 'PASSED', created_at: '' })
    deletePersona.mockResolvedValue(undefined)
    renderPage()
    await waitFor(() => expect(screen.getByText('删除画像')).toBeInTheDocument())
    fireEvent.click(screen.getByText('删除画像'))
    await waitFor(() => expect(screen.getByRole('button', { name: '确认删除' })).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: '确认删除' }))
    await waitFor(() => expect(deletePersona).toHaveBeenCalledWith('p1'))
  })
})
