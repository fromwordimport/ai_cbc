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

const mockAdminSettings = {
  environment: 'test',
  log_level: 'INFO',
  llm: { provider: 'anthropic', model: 'claude-sonnet-4-6', temperature: 0.7, max_tokens: 4096 },
  providers: {
    anthropic: { enabled: true, api_key_set: true, base_url: 'https://api.anthropic.com', model: 'claude-sonnet-4-6' },
    openai: { enabled: false, api_key_set: false, base_url: 'https://api.openai.com/v1', model: 'gpt-4o' },
    deepseek: { enabled: false, api_key_set: false, base_url: 'https://api.deepseek.com/v1', model: 'deepseek-chat' },
    qwen: { enabled: false, api_key_set: false, base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1', model: 'qwen-max' },
    glm: { enabled: false, api_key_set: false, base_url: 'https://open.bigmodel.cn/api/paas/v4', model: 'glm-4' },
  },
  cost_fuse: { daily_cny: 50, monthly_cny: 1000 },
  authenticity: { pass_threshold: 9, excellent_threshold: 12 },
}

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
    getAdminSettings.mockResolvedValue(mockAdminSettings)

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
    getAdminSettings.mockResolvedValue(mockAdminSettings)
    updateAdminSettings.mockResolvedValue({ status: 'ok' })

    renderSettings()
    await waitFor(() => expect(screen.getByText('保存设置')).toBeInTheDocument())
    fireEvent.click(screen.getByText('保存设置'))
    await waitFor(() => expect(updateAdminSettings).toHaveBeenCalled())
    const payload = updateAdminSettings.mock.calls[0][0]
    expect(payload.llm_provider).toBe('anthropic')
    expect(payload.providers.anthropic.api_key).toBeUndefined()
    expect(JSON.parse(localStorage.getItem('aicbc_settings') || '{}').pass_threshold).toBe(9)
  })

  it('falls back to local storage when backend save fails', async () => {
    getCostStatus.mockResolvedValue({ total_cost_cny: 0, daily_cost_cny: 0, fuse_status: 'NORMAL' })
    getHealthCheck.mockResolvedValue({ status: 'healthy', environment: 'test', version: '0.1.0' })
    getAdminSettings.mockResolvedValue(mockAdminSettings)
    updateAdminSettings.mockRejectedValue(new Error('backend down'))

    renderSettings()
    await waitFor(() => expect(screen.getByText('保存设置')).toBeInTheDocument())
    fireEvent.click(screen.getByText('保存设置'))
    await waitFor(() => expect(localStorage.getItem('aicbc_settings')).not.toBeNull())
  })
})
