import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import userEvent from '@testing-library/user-event'
import MarketSimulator from '@/pages/MarketSimulator'
import { useAppStore } from '@/stores/appStore'

// Mock API module
const mockGetStudies = vi.fn()
const mockGetStudyDesign = vi.fn()
const mockGetAnalysisResult = vi.fn()
const mockSimulateMarket = vi.fn()

vi.mock('@/services/api', () => ({
  getStudies: (...args: any[]) => mockGetStudies(...args),
  getStudyDesign: (...args: any[]) => mockGetStudyDesign(...args),
  getAnalysisResult: (...args: any[]) => mockGetAnalysisResult(...args),
  simulateMarket: (...args: any[]) => mockSimulateMarket(...args),
}))

const renderMarketSimulator = () =>
  render(
    <MemoryRouter initialEntries={['/?study=s1&analysis=a1']}>
      <Routes>
        <Route path="/" element={<MarketSimulator />} />
      </Routes>
    </MemoryRouter>,
  )

describe('MarketSimulator render', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAppStore.setState({
      ...useAppStore.getInitialState(),
      selectedStudyId: 's1',
      selectedAnalysisId: 'a1',
      studies: [{ study_id: 's1', product_category: '洗碗机', research_goal: '', target_segments: [], created_at: '', status: 'READY' }],
    })
    mockGetStudies.mockResolvedValue({ studies: [{ study_id: 's1', product_category: '洗碗机', research_goal: '', target_segments: [], created_at: '', status: 'READY' }] })
    mockGetStudyDesign.mockResolvedValue({
      study_id: 's1',
      attributes: [
        { id: 'price', name: '价格', type: 'price', levels: [] },
        { id: 'brand', name: '品牌', type: 'categorical', levels: [{ value: 'midea', label: '美的' }, { value: 'siemens', label: '西门子' }] },
      ],
    })
    mockGetAnalysisResult.mockResolvedValue({
      analysis_id: 'a1',
      study_id: 's1',
      status: 'COMPLETED',
      model_type: 'hb',
      convergence: { converged: true, rhat_max: 1.05 },
      population_params: { mu: {}, sigma: {} },
      individual_utilities: {},
      importance: {},
      wtp: {},
      processing_time_seconds: 1,
      completed_at: null,
    })
  })

  it('renders with study design', async () => {
    renderMarketSimulator()
    await waitFor(() => expect(screen.getByText('市场份额模拟器')).toBeInTheDocument())
  })

  it('renders with fallback when study design fails', async () => {
    mockGetStudyDesign.mockRejectedValue(new Error('fail'))
    renderMarketSimulator()
    await waitFor(() => expect(screen.getByText('市场份额模拟器')).toBeInTheDocument())
  })
})

describe('MarketSimulator scenario management', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAppStore.setState({
      ...useAppStore.getInitialState(),
      selectedStudyId: 's1',
      selectedAnalysisId: 'a1',
      studies: [{ study_id: 's1', product_category: '洗碗机', research_goal: '', target_segments: [], created_at: '', status: 'READY' }],
    })
    mockGetStudies.mockResolvedValue({ studies: [{ study_id: 's1', product_category: '洗碗机', research_goal: '', target_segments: [], created_at: '', status: 'READY' }] })
    mockGetStudyDesign.mockResolvedValue({
      study_id: 's1',
      attributes: [
        { id: 'price', name: '价格', type: 'price', levels: [] },
        { id: 'brand', name: '品牌', type: 'categorical', levels: [{ value: 'midea', label: '美的' }, { value: 'siemens', label: '西门子' }] },
      ],
    })
    mockGetAnalysisResult.mockResolvedValue({
      analysis_id: 'a1',
      study_id: 's1',
      status: 'COMPLETED',
      model_type: 'hb',
      convergence: { converged: true, rhat_max: 1.05 },
      population_params: { mu: {}, sigma: {} },
      individual_utilities: {},
      importance: {},
      wtp: {},
      processing_time_seconds: 1,
      completed_at: null,
    })
  })

  it('adds a new scenario', async () => {
    renderMarketSimulator()
    await waitFor(() => expect(screen.getByText('市场份额模拟器')).toBeInTheDocument())

    const addBtn = screen.getByText('添加场景')
    await userEvent.click(addBtn)

    // After adding, there should be more scenarios
    await waitFor(() => {
      const inputs = screen.getAllByPlaceholderText('场景名称')
      expect(inputs.length).toBeGreaterThan(2)
    })
  })

  it('updates scenario name', async () => {
    renderMarketSimulator()
    await waitFor(() => expect(screen.getByText('市场份额模拟器')).toBeInTheDocument())

    const nameInputs = screen.getAllByPlaceholderText('场景名称')
    expect(nameInputs.length).toBeGreaterThan(0)

    await userEvent.clear(nameInputs[0])
    await userEvent.type(nameInputs[0], '新产品A')

    expect(nameInputs[0]).toHaveValue('新产品A')
  })
})

describe('MarketSimulator simulation', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAppStore.setState({
      ...useAppStore.getInitialState(),
      selectedStudyId: 's1',
      selectedAnalysisId: 'a1',
      studies: [{ study_id: 's1', product_category: '洗碗机', research_goal: '', target_segments: [], created_at: '', status: 'READY' }],
    })
    mockGetStudies.mockResolvedValue({ studies: [{ study_id: 's1', product_category: '洗碗机', research_goal: '', target_segments: [], created_at: '', status: 'READY' }] })
    mockGetStudyDesign.mockResolvedValue({
      study_id: 's1',
      attributes: [
        { id: 'price', name: '价格', type: 'price', levels: [] },
        { id: 'brand', name: '品牌', type: 'categorical', levels: [{ value: 'midea', label: '美的' }, { value: 'siemens', label: '西门子' }] },
      ],
    })
    mockGetAnalysisResult.mockResolvedValue({
      analysis_id: 'a1',
      study_id: 's1',
      status: 'COMPLETED',
      model_type: 'hb',
      convergence: { converged: true, rhat_max: 1.05 },
      population_params: { mu: {}, sigma: {} },
      individual_utilities: {},
      importance: {},
      wtp: {},
      processing_time_seconds: 1,
      completed_at: null,
    })
  })

  it('runs simulation successfully', async () => {
    mockSimulateMarket.mockResolvedValue({
      scenarios: [
        { name: '产品 A', predicted_share: 0.45, share_ci_95_lower: 0.40, share_ci_95_upper: 0.50 },
        { name: '产品 B', predicted_share: 0.55, share_ci_95_lower: 0.50, share_ci_95_upper: 0.60 },
      ],
    })

    renderMarketSimulator()
    await waitFor(() => expect(screen.getByText('市场份额模拟器')).toBeInTheDocument())

    // Run simulation
    const runBtn = screen.getByText('运行市场份额模拟')
    await userEvent.click(runBtn)

    await waitFor(() => {
      expect(screen.getByText('市场份额分布')).toBeInTheDocument()
      expect(screen.getByText('份额对比')).toBeInTheDocument()
      expect(screen.getByText('详细数据')).toBeInTheDocument()
    })
  })

  it('handles simulation error', async () => {
    mockSimulateMarket.mockRejectedValue(new Error('模拟失败'))

    renderMarketSimulator()
    await waitFor(() => expect(screen.getByText('市场份额模拟器')).toBeInTheDocument())

    const runBtn = screen.getByText('运行市场份额模拟')
    await userEvent.click(runBtn)

    await waitFor(() => {
      expect(screen.getByText('模拟失败')).toBeInTheDocument()
    })
  })
})

describe('MarketSimulator configuration', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAppStore.setState({
      ...useAppStore.getInitialState(),
      selectedStudyId: 's1',
      selectedAnalysisId: 'a1',
      studies: [{ study_id: 's1', product_category: '洗碗机', research_goal: '', target_segments: [], created_at: '', status: 'READY' }],
    })
    mockGetStudies.mockResolvedValue({ studies: [{ study_id: 's1', product_category: '洗碗机', research_goal: '', target_segments: [], created_at: '', status: 'READY' }] })
    mockGetStudyDesign.mockResolvedValue({
      study_id: 's1',
      attributes: [
        { id: 'price', name: '价格', type: 'price', levels: [] },
        { id: 'brand', name: '品牌', type: 'categorical', levels: [{ value: 'midea', label: '美的' }, { value: 'siemens', label: '西门子' }] },
      ],
    })
    mockGetAnalysisResult.mockResolvedValue({
      analysis_id: 'a1',
      study_id: 's1',
      status: 'COMPLETED',
      model_type: 'hb',
      convergence: { converged: true, rhat_max: 1.05 },
      population_params: { mu: {}, sigma: {} },
      individual_utilities: {},
      importance: {},
      wtp: {},
      processing_time_seconds: 1,
      completed_at: null,
    })
  })

  it('shows analysis result convergence info', async () => {
    renderMarketSimulator()
    await waitFor(() => expect(screen.getByText('市场份额模拟器')).toBeInTheDocument())

    // Convergence info should be displayed
    await waitFor(() => {
      expect(screen.getByText(/收敛/)).toBeInTheDocument()
    })
  })

  it('shows empty state before simulation', async () => {
    renderMarketSimulator()
    await waitFor(() => expect(screen.getByText('市场份额模拟器')).toBeInTheDocument())

    expect(screen.getByText('配置产品场景并点击运行模拟')).toBeInTheDocument()
  })
})

describe('MarketSimulator helper functions', () => {
  it('buildDefaultScenario creates correct structure', async () => {
    const mod = await import('@/pages/MarketSimulator')
    const attributes = [
      { id: 'price', name: '价格', type: 'price', levels: [] },
      { id: 'brand', name: '品牌', type: 'categorical', levels: [{ value: 'a', label: 'A' }] },
    ] as any
    const scenario = mod.buildDefaultScenario(attributes)
    expect(scenario.name).toBe('产品 A')
    expect(scenario.attributes.price).toBe(3999)
    expect(scenario.attributes.brand).toBe('a')
  })

  it('buildScenarioName generates correct names', async () => {
    const mod = await import('@/pages/MarketSimulator')
    expect(mod.buildScenarioName(0)).toBe('产品 A')
    expect(mod.buildScenarioName(1)).toBe('产品 B')
    expect(mod.buildScenarioName(9)).toBe('产品 J')
  })

  it('validateScenarios returns error for less than 2 scenarios', async () => {
    const mod = await import('@/pages/MarketSimulator')
    expect(mod.validateScenarios([{ name: 'A', attributes: {} }])).toBe('至少需要配置 2 个产品场景')
    expect(mod.validateScenarios([{ name: 'A', attributes: {} }, { name: 'B', attributes: {} }])).toBeNull()
  })

  it('buildSharePieOption creates pie chart config', async () => {
    const mod = await import('@/pages/MarketSimulator')
    const shares = [
      { name: '产品 A', predicted_share: 0.45, share_ci_95_lower: 0.40, share_ci_95_upper: 0.50 },
      { name: '产品 B', predicted_share: 0.55, share_ci_95_lower: 0.50, share_ci_95_upper: 0.60 },
    ] as any
    const option = mod.buildSharePieOption(shares)
    expect(option.series[0].type).toBe('pie')
    expect(option.series[0].data.length).toBe(2)
  })

  it('buildShareBarOption creates bar chart config', async () => {
    const mod = await import('@/pages/MarketSimulator')
    const shares = [
      { name: '产品 A', predicted_share: 0.45, share_ci_95_lower: 0.40, share_ci_95_upper: 0.50 },
      { name: '产品 B', predicted_share: 0.55, share_ci_95_lower: 0.50, share_ci_95_upper: 0.60 },
    ] as any
    const option = mod.buildShareBarOption(shares)
    expect(option.series[0].type).toBe('bar')
    expect(option.xAxis.data.length).toBe(2)
  })
})
