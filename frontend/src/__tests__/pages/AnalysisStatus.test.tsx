import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import AnalysisStatus from '@/pages/AnalysisStatus'
import { useAppStore } from '@/stores/appStore'

const getStudies = vi.fn()
const analyzeStudy = vi.fn()
const getAnalysisStatus = vi.fn()
const getConvergence = vi.fn()
const listAnalyses = vi.fn()

vi.mock('@/services/api', () => ({
  getStudies: (...args: any[]) => getStudies(...args),
  analyzeStudy: (...args: any[]) => analyzeStudy(...args),
  getAnalysisStatus: (...args: any[]) => getAnalysisStatus(...args),
  getConvergence: (...args: any[]) => getConvergence(...args),
  getAnalysisVisualization: vi.fn(),
  runLatentClassAnalysis: vi.fn(),
  listAnalyses: (...args: any[]) => listAnalyses(...args),
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

describe('AnalysisStatus', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAppStore.setState(useAppStore.getInitialState())
  })

  const renderPage = () =>
    render(
      <MemoryRouter>
        <AnalysisStatus />
      </MemoryRouter>,
    )

  it('loads studies and starts analysis', async () => {
    getStudies.mockResolvedValue({
      studies: [{ study_id: 's1', product_category: '洗碗机' }],
    })
    analyzeStudy.mockResolvedValue({
      analysis_id: 'a1',
      study_id: 's1',
      status: 'RUNNING',
      model_type: 'hb',
      progress_percent: 0,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    })

    renderPage()
    await waitFor(() => expect(getStudies).toHaveBeenCalled())

    fireEvent.mouseDown(screen.getByText('选择研究项目运行分析'))
    await waitFor(() => expect(screen.getByText('s1 (洗碗机)')).toBeInTheDocument())
    fireEvent.click(screen.getByText('s1 (洗碗机)'))

    fireEvent.click(screen.getByText('启动分析'))
    await waitFor(() => expect(analyzeStudy).toHaveBeenCalledWith('s1', 'hb'))
  })

  it('shows completed job with action buttons', async () => {
    getStudies.mockResolvedValue({ studies: [] })

    useAppStore.setState({
      ...useAppStore.getInitialState(),
      completedJobs: [
        {
          analysis_id: 'a1',
          study_id: 's1',
          status: 'COMPLETED',
          model_type: 'hb',
          progress_percent: 100,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        } as any,
      ],
    })

    renderPage()
    await waitFor(() => expect(screen.getByText('a1')).toBeInTheDocument())
    expect(screen.getByText('报告')).toBeInTheDocument()
    expect(screen.getByText('可视化')).toBeInTheDocument()
    expect(screen.getByText('LCM')).toBeInTheDocument()
  })

  it('loads existing analysis jobs on mount', async () => {
    getStudies.mockResolvedValue({
      studies: [{ study_id: 's1', product_category: '洗碗机' }],
    })
    listAnalyses.mockResolvedValue([
      {
        analysis_id: 'a2',
        study_id: 's1',
        status: 'COMPLETED',
        model_type: 'hb',
        progress_percent: 100,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
    ])

    renderPage()
    await waitFor(() => expect(listAnalyses).toHaveBeenCalledWith('s1'))
    await waitFor(() => expect(screen.getByText('a2')).toBeInTheDocument())
  })
})
