import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import StudyCreate from '@/pages/StudyCreate'

const createStudy = vi.fn()
const generateQuestionnaire = vi.fn()

vi.mock('@/services/api', () => ({
  createStudy: (...args: any[]) => createStudy(...args),
  generateQuestionnaire: (...args: any[]) => generateQuestionnaire(...args),
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

describe('StudyCreate', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  const renderPage = () =>
    render(
      <MemoryRouter>
        <StudyCreate />
      </MemoryRouter>,
    )

  it('creates study and generates questionnaire with default attributes', async () => {
    createStudy.mockResolvedValue({ study_id: 's1' })
    generateQuestionnaire.mockResolvedValue({ d_efficiency: 0.9 })

    renderPage()
    fireEvent.change(screen.getByPlaceholderText('例如：dishwasher-2024q3'), { target: { value: 's1' } })
    fireEvent.change(screen.getByPlaceholderText('例如：洗碗机、扫地机器人'), { target: { value: '洗碗机' } })
    fireEvent.change(screen.getByPlaceholderText('例如：评估消费者对洗碗机各属性水平的偏好，指导新品定价与功能配置'), { target: { value: 'goal' } })

    fireEvent.click(screen.getByText('创建研究并生成问卷'))
    await waitFor(() => expect(createStudy).toHaveBeenCalledWith(expect.objectContaining({ study_id: 's1', product_category: '洗碗机', research_goal: 'goal' })))
    await waitFor(() => expect(generateQuestionnaire).toHaveBeenCalledWith('s1'))
  })

  it('shows error when study creation fails', async () => {
    createStudy.mockRejectedValue(new Error('duplicate id'))
    renderPage()
    fireEvent.change(screen.getByPlaceholderText('例如：dishwasher-2024q3'), { target: { value: 's1' } })
    fireEvent.change(screen.getByPlaceholderText('例如：洗碗机、扫地机器人'), { target: { value: '洗碗机' } })
    fireEvent.change(screen.getByPlaceholderText('例如：评估消费者对洗碗机各属性水平的偏好，指导新品定价与功能配置'), { target: { value: 'goal' } })

    fireEvent.click(screen.getByText('创建研究并生成问卷'))
    await waitFor(() => expect(screen.getByText('duplicate id')).toBeInTheDocument())
  })

  it('toggles custom attributes', async () => {
    renderPage()
    fireEvent.click(screen.getByText('自定义属性'))
    await waitFor(() => expect(screen.getByPlaceholderText('例如 price')).toBeInTheDocument())
  })
})
