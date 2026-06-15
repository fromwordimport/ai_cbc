import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import QuestionnaireConfig from '@/pages/QuestionnaireConfig'

const getStudies = vi.fn()
const getQuestionnaire = vi.fn()
const generateQuestionnaire = vi.fn()
const deleteStudy = vi.fn()

vi.mock('@/services/api', () => ({
  getStudies: (...args: any[]) => getStudies(...args),
  getQuestionnaire: (...args: any[]) => getQuestionnaire(...args),
  generateQuestionnaire: (...args: any[]) => generateQuestionnaire(...args),
  deleteStudy: (...args: any[]) => deleteStudy(...args),
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

describe('QuestionnaireConfig', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  const renderPage = () =>
    render(
      <MemoryRouter>
        <QuestionnaireConfig />
      </MemoryRouter>,
    )

  it('renders study list with questionnaire details', async () => {
    getStudies.mockResolvedValue({
      studies: [{ study_id: 's1', product_category: '洗碗机', research_goal: 'goal', status: 'READY' }],
    })
    getQuestionnaire.mockResolvedValue({
      design_params: { algorithm: 'd_optimal', n_attributes: 5, n_choice_sets: 3, n_alternatives: 3, include_none: false, d_efficiency: 0.88 },
      choice_sets: [
        {
          choice_set_id: 'cs1',
          alternatives: [{ alt_id: 'a1', alt_index: 0, attributes: { price: 2999 } }],
        },
      ],
    })

    renderPage()
    await waitFor(() => expect(screen.getByText('s1')).toBeInTheDocument())
    await waitFor(() => expect(screen.getByText('已生成')).toBeInTheDocument())
    expect(screen.getByText('0.880')).toBeInTheDocument()
  })

  it('generates questionnaire for study without one', async () => {
    getStudies.mockResolvedValue({
      studies: [{ study_id: 's2', product_category: '洗碗机', research_goal: 'goal', status: 'INIT' }],
    })
    generateQuestionnaire.mockResolvedValue({ d_efficiency: 0.9 })
    getQuestionnaire.mockRejectedValue(new Error('not found'))

    renderPage()
    await waitFor(() => expect(screen.getByText('生成问卷')).toBeInTheDocument())
    fireEvent.click(screen.getByText('生成问卷'))
    await waitFor(() => expect(generateQuestionnaire).toHaveBeenCalledWith('s2'))
  })

  it('deletes study after confirm', async () => {
    getStudies.mockResolvedValue({
      studies: [{ study_id: 's1', product_category: '洗碗机', research_goal: 'goal', status: 'INIT' }],
    })
    deleteStudy.mockResolvedValue(undefined)

    renderPage()
    await waitFor(() => expect(screen.getByText('删除')).toBeInTheDocument())
    fireEvent.click(screen.getByText('删除'))
    await waitFor(() => expect(screen.getByRole('button', { name: '确认删除' })).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: '确认删除' }))
    await waitFor(() => expect(deleteStudy).toHaveBeenCalledWith('s1'))
  })
})
