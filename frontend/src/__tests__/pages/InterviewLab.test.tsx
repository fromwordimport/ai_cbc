import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import InterviewLab from '@/pages/InterviewLab'

const getPersonas = vi.fn()
const converse = vi.fn()
const runInterview = vi.fn()

vi.mock('@/services/api', () => ({
  getPersonas: (...args: any[]) => getPersonas(...args),
  converse: (...args: any[]) => converse(...args),
  runInterview: (...args: any[]) => runInterview(...args),
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

describe('InterviewLab', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  const renderPage = () =>
    render(
      <MemoryRouter>
        <InterviewLab />
      </MemoryRouter>,
    )

  it('sends single-turn question', async () => {
    getPersonas.mockResolvedValue({
      personas: [{ persona_id: 'p1', segment: 'A' }],
    })
    converse.mockResolvedValue({
      researcher_question: 'why',
      consumer_response: 'because',
      emotion_tag: 'neutral',
      inconsistency_flag: false,
    })

    renderPage()
    await waitFor(() => expect(getPersonas).toHaveBeenCalledWith(1, 100))

    fireEvent.mouseDown(screen.getByText('选择虚拟消费者'))
    await waitFor(() => expect(screen.getByText('p1 (A)')).toBeInTheDocument())
    fireEvent.click(screen.getByText('p1 (A)'))

    fireEvent.change(screen.getByPlaceholderText('输入研究员的问题...'), { target: { value: 'why?' } })
    fireEvent.click(screen.getByText('发送问题'))
    await waitFor(() => expect(converse).toHaveBeenCalledWith('p1', { question: 'why?', context: {} }))
    await waitFor(() => expect(screen.getByText('because')).toBeInTheDocument())
  })

  it('runs multi-round interview', async () => {
    getPersonas.mockResolvedValue({ personas: [{ persona_id: 'p1', segment: 'A' }] })
    runInterview.mockResolvedValue({
      turns: [
        { researcher_question: 'q1', consumer_response: 'a1', emotion_tag: 'happy', inconsistency_flag: true },
      ],
    })

    renderPage()
    await waitFor(() => expect(screen.getByText('多轮访谈')).toBeInTheDocument())
    fireEvent.click(screen.getByText('多轮访谈'))

    fireEvent.mouseDown(screen.getByText('选择虚拟消费者'))
    await waitFor(() => expect(screen.getByText('p1 (A)')).toBeInTheDocument())
    fireEvent.click(screen.getByText('p1 (A)'))

    fireEvent.change(screen.getByPlaceholderText('访谈问题 1'), { target: { value: 'q1' } })
    fireEvent.click(screen.getByText('运行多轮访谈'))
    await waitFor(() => expect(runInterview).toHaveBeenCalledWith('p1', { questions: ['q1'], context: {} }))
    await waitFor(() => expect(screen.getByText('矛盾警告')).toBeInTheDocument())
  })

  it('adds and removes interview questions', async () => {
    getPersonas.mockResolvedValue({ personas: [] })
    renderPage()
    await waitFor(() => expect(screen.getByText('多轮访谈')).toBeInTheDocument())
    fireEvent.click(screen.getByText('多轮访谈'))
    fireEvent.click(screen.getByText('添加问题'))
    expect(screen.getAllByPlaceholderText(/访谈问题/).length).toBe(2)
  })
})
