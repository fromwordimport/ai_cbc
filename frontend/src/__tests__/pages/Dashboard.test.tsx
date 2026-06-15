import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import Dashboard from '@/pages/Dashboard'
import { useAppStore } from '@/stores/appStore'

const getDashboardSummary = vi.fn()
const getStudies = vi.fn()
const deleteStudy = vi.fn()
const generateQuestionnaire = vi.fn()

vi.mock('@/services/api', () => ({
  getDashboardSummary: (...args: any[]) => getDashboardSummary(...args),
  getStudies: (...args: any[]) => getStudies(...args),
  deleteStudy: (...args: any[]) => deleteStudy(...args),
  generateQuestionnaire: (...args: any[]) => generateQuestionnaire(...args),
}))

const renderDashboard = () =>
  render(
    <MemoryRouter>
      <Routes>
        <Route path="/" element={<Dashboard />} />
      </Routes>
    </MemoryRouter>,
  )

describe('Dashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAppStore.setState({ ...useAppStore.getInitialState(), runningJobs: [{ analysis_id: 'a1' } as any] })
  })

  it('renders summary statistics and study list', async () => {
    getDashboardSummary.mockResolvedValue({
      summary: { total_studies: 5, total_personas: 12, studies_by_status: { READY: 2 } },
    })
    getStudies.mockResolvedValue({
      studies: [
        {
          study_id: 's1',
          product_category: '洗碗机',
          research_goal: 'goal',
          created_at: '2026-06-14T10:00:00Z',
          status: 'INIT',
        },
      ],
    })

    renderDashboard()
    await waitFor(() => expect(screen.getByText('5')).toBeInTheDocument())
    expect(screen.getByText('12')).toBeInTheDocument()
    expect(screen.getByText('洗碗机')).toBeInTheDocument()
  })

  it('shows error message on fetch failure', async () => {
    getDashboardSummary.mockRejectedValue(new Error('network error'))
    getStudies.mockResolvedValue({ studies: [] })
    renderDashboard()
    await waitFor(() => expect(screen.getByText('network error')).toBeInTheDocument())
  })

  it('refreshes data on window focus', async () => {
    getDashboardSummary.mockResolvedValue({ summary: { total_studies: 1, total_personas: 0, studies_by_status: {} } })
    getStudies.mockResolvedValue({ studies: [] })
    renderDashboard()
    await waitFor(() => expect(getDashboardSummary).toHaveBeenCalledTimes(1))
    fireEvent.focus(window)
    await waitFor(() => expect(getDashboardSummary).toHaveBeenCalledTimes(2))
  })

  it('generates questionnaire for INIT study', async () => {
    getDashboardSummary.mockResolvedValue({ summary: { total_studies: 1, total_personas: 0, studies_by_status: {} } })
    getStudies.mockResolvedValue({
      studies: [{ study_id: 's1', product_category: '洗碗机', research_goal: '', created_at: new Date().toISOString(), status: 'INIT' }],
    })
    generateQuestionnaire.mockResolvedValue({ d_efficiency: 0.9 })
    renderDashboard()
    await waitFor(() => expect(screen.getByText('生成问卷')).toBeInTheDocument())
    fireEvent.click(screen.getByText('生成问卷'))
    await waitFor(() => expect(generateQuestionnaire).toHaveBeenCalledWith('s1'))
  })

  it('deletes study after confirm', async () => {
    getDashboardSummary.mockResolvedValue({ summary: { total_studies: 1, total_personas: 0, studies_by_status: {} } })
    getStudies.mockResolvedValue({
      studies: [{ study_id: 's1', product_category: '洗碗机', research_goal: '', created_at: new Date().toISOString(), status: 'READY' }],
    })
    deleteStudy.mockResolvedValue(undefined)
    renderDashboard()
    await waitFor(() => expect(screen.getByText('删除')).toBeInTheDocument())
    fireEvent.click(screen.getByText('删除'))
    await waitFor(() => expect(screen.getByText('确认删除')).toBeInTheDocument())
    fireEvent.click(screen.getByText('确认删除'))
    await waitFor(() => expect(deleteStudy).toHaveBeenCalledWith('s1'))
  })
})
