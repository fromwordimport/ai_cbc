import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Settings from '@/pages/Settings'

const getAdminSettings = vi.fn()
const getCostStatus = vi.fn()
const getHealthCheck = vi.fn()
const updateAdminSettings = vi.fn()

vi.mock('@/services/api', () => ({
  getAdminSettings: (...args: any[]) => getAdminSettings(...args),
  getCostStatus: (...args: any[]) => getCostStatus(...args),
  getHealthCheck: (...args: any[]) => getHealthCheck(...args),
  updateAdminSettings: (...args: any[]) => updateAdminSettings(...args),
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

describe('Settings', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
  })

  const renderSettings = () =>
    render(
      <MemoryRouter>
        <Settings />
      </MemoryRouter>,
    )

  it('loads backend settings and renders status cards', async () => {
    getCostStatus.mockResolvedValue({ total_cost_cny: 12.5, daily_cost_cny: 3.0, fuse_status: 'NORMAL' })
    getHealthCheck.mockResolvedValue({ status: 'healthy', environment: 'test', version: '0.1.0' })
    getAdminSettings.mockResolvedValue({
      environment: 'test',
      log_level: 'INFO',
      llm: { temperature: 0.5, max_tokens: 2048 },
      cost_fuse: { daily_cny: 100, monthly_cny: 2000 },
      authenticity: { pass_threshold: 8, excellent_threshold: 11 },
      study_defaults: { n_choice_sets: 12, n_alternatives: 3, sample_size: 300, d_efficiency_target: 0.8 },
    })

    renderSettings()
    await waitFor(() => expect(screen.getByText('健康')).toBeInTheDocument())
    expect(screen.getAllByText('test').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('累计成本')).toBeInTheDocument()
    expect(screen.getByText('正常')).toBeInTheDocument()
  })

  it('shows error when all status endpoints fail', async () => {
    getCostStatus.mockRejectedValue(new Error('failed'))
    getHealthCheck.mockRejectedValue(new Error('failed'))
    getAdminSettings.mockRejectedValue(new Error('failed'))

    renderSettings()
    await waitFor(() => expect(screen.getByText('无法连接到后端服务，请确认服务已启动')).toBeInTheDocument())
  })

  it('saves settings to backend and localStorage', async () => {
    getCostStatus.mockResolvedValue({ total_cost_cny: 0, daily_cost_cny: 0, fuse_status: 'NORMAL' })
    getHealthCheck.mockResolvedValue({ status: 'healthy', environment: 'test', version: '0.1.0' })
    getAdminSettings.mockResolvedValue({
      environment: 'test',
      log_level: 'INFO',
      llm: { temperature: 0.7, max_tokens: 4096 },
      cost_fuse: { daily_cny: 50, monthly_cny: 1000 },
      authenticity: { pass_threshold: 9, excellent_threshold: 12 },
    })
    updateAdminSettings.mockResolvedValue({ status: 'ok' })

    renderSettings()
    await waitFor(() => expect(screen.getByText('保存设置')).toBeInTheDocument())
    fireEvent.click(screen.getByText('保存设置'))
    await waitFor(() => expect(updateAdminSettings).toHaveBeenCalled())
    expect(JSON.parse(localStorage.getItem('aicbc_settings') || '{}').pass_threshold).toBe(9)
  })

  it('falls back to local storage when backend save fails', async () => {
    getCostStatus.mockResolvedValue({ total_cost_cny: 0, daily_cost_cny: 0, fuse_status: 'NORMAL' })
    getHealthCheck.mockResolvedValue({ status: 'healthy', environment: 'test', version: '0.1.0' })
    getAdminSettings.mockResolvedValue({
      environment: 'test',
      log_level: 'INFO',
      llm: { temperature: 0.7, max_tokens: 4096 },
      cost_fuse: { daily_cny: 50, monthly_cny: 1000 },
      authenticity: { pass_threshold: 9, excellent_threshold: 12 },
    })
    updateAdminSettings.mockRejectedValue(new Error('backend down'))

    renderSettings()
    await waitFor(() => expect(screen.getByText('保存设置')).toBeInTheDocument())
    fireEvent.click(screen.getByText('保存设置'))
    await waitFor(() => expect(localStorage.getItem('aicbc_settings')).not.toBeNull())
  })
})
