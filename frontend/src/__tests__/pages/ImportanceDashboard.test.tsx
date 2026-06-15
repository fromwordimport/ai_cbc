import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import ImportanceDashboard from '@/pages/ImportanceDashboard'
import { useAppStore } from '@/stores/appStore'

const getStudies = vi.fn()
const getImportance = vi.fn()
const getConvergence = vi.fn()
const getWTP = vi.fn()
const analyzeStudy = vi.fn()

vi.mock('@/services/api', () => ({
  getStudies: (...args: any[]) => getStudies(...args),
  getImportance: (...args: any[]) => getImportance(...args),
  getConvergence: (...args: any[]) => getConvergence(...args),
  getWTP: (...args: any[]) => getWTP(...args),
  analyzeStudy: (...args: any[]) => analyzeStudy(...args),
}))

const renderDashboard = () =>
  render(
    <MemoryRouter initialEntries={['/?study=s1&analysis=a1']}>
      <Routes>
        <Route path="/" element={<ImportanceDashboard />} />
      </Routes>
    </MemoryRouter>,
  )

describe('ImportanceDashboard render', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAppStore.setState({
      ...useAppStore.getInitialState(),
      selectedStudyId: 's1',
      selectedAnalysisId: 'a1',
      studies: [{ study_id: 's1', product_category: '洗碗机', research_goal: '', target_segments: [], created_at: '', status: 'READY' }],
    })
    getStudies.mockResolvedValue({ studies: [] })
    getImportance.mockResolvedValue({
      overall: {
        price: { mean: 0.5, std: 0.05, median: 0.5, min: 0, max: 1, q25: 0.4, q75: 0.6, ci_95_lower: 0.4, ci_95_upper: 0.6 },
        brand: { mean: 0.3, std: 0.04, median: 0.3, min: 0, max: 1, q25: 0.2, q75: 0.4, ci_95_lower: 0.2, ci_95_upper: 0.4 },
      },
    })
    getConvergence.mockResolvedValue({
      rhat_max: 1.05,
      rhat_by_param: {},
      ess_bulk_min: 100,
      ess_tail_min: 100,
      ess_by_param: {},
      converged: true,
      reliable_ess: true,
      divergences: 0,
      tree_depth_max: 10,
    })
    getWTP.mockResolvedValue({
      wtp_values: {},
      price_coefficient_summary: { mean: -0.5, median: -0.5, std: 0.1, negative_rate: 0.95, n_positive_outliers: 0 },
    })
  })

  it('renders with results', async () => {
    renderDashboard()
    await waitFor(() => expect(screen.getByText('属性重要性可视化看板')).toBeInTheDocument())
  })
})
