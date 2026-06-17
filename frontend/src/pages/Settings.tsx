import React, { useEffect, useState, useCallback } from 'react'
import {
  Card, Row, Col, Typography, Tag, Spin, Alert, Statistic,
  Descriptions, Slider, Select, Button, Divider, message,
  InputNumber, Input, Collapse,
} from 'antd'
import {
  SettingOutlined, CheckCircleOutlined, CloseCircleOutlined,
  WalletOutlined, RobotOutlined, HeartOutlined,
  ReloadOutlined, SaveOutlined,
} from '@ant-design/icons'
import { getAdminSettings, getCostStatus, getHealthCheck, updateAdminSettings } from '@/services/api'
import type { AdminSettings, CostStatus, HealthStatus, LLMSettings, ProviderConfig, SystemSettings } from '@/types/api'

const { Title } = Typography
const { Option } = Select
const { Panel } = Collapse

const PROVIDERS = [
  { key: 'anthropic', label: 'Anthropic' },
  { key: 'openai', label: 'OpenAI' },
  { key: 'deepseek', label: 'DeepSeek' },
  { key: 'qwen', label: '通义千问' },
  { key: 'glm', label: '智谱 GLM' },
]

const DEFAULT_PROVIDER_MODELS: Record<string, string[]> = {
  anthropic: ['claude-sonnet-4-6', 'claude-haiku-4-5'],
  openai: ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo'],
  deepseek: ['deepseek-chat', 'deepseek-reasoner'],
  qwen: ['qwen-max'],
  glm: ['glm-4'],
}

const DEFAULT_LLM: LLMSettings = {
  provider: 'anthropic',
  model: '',
  temperature: 0.7,
  max_tokens: 4096,
}

const DEFAULT_PROVIDERS: Record<string, ProviderConfig> = {
  anthropic: { enabled: false, api_key_set: false, base_url: 'https://api.anthropic.com', model: 'claude-sonnet-4-6' },
  openai: { enabled: false, api_key_set: false, base_url: 'https://api.openai.com/v1', model: 'gpt-4o' },
  deepseek: { enabled: false, api_key_set: false, base_url: 'https://api.deepseek.com/v1', model: 'deepseek-chat' },
  qwen: { enabled: false, api_key_set: false, base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1', model: 'qwen-max' },
  glm: { enabled: false, api_key_set: false, base_url: 'https://open.bigmodel.cn/api/paas/v4', model: 'glm-4' },
}

const DEFAULT_SYSTEM: SystemSettings = {
  llm: DEFAULT_LLM,
  cost_budget_daily: 50.0,
  cost_budget_monthly: 1000.0,
  pass_threshold: 9,
  excellent_threshold: 12,
}

const SETTINGS_STORAGE_KEY = 'aicbc_settings'

function loadLocalSettings(): SystemSettings {
  try {
    const raw = localStorage.getItem(SETTINGS_STORAGE_KEY)
    if (raw) return { ...DEFAULT_SYSTEM, ...JSON.parse(raw) }
  } catch { /* ignore */ }
  return DEFAULT_SYSTEM
}

function saveToLocal(settings: SystemSettings) {
  localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(settings))
}

function mergeBackendSettings(local: SystemSettings, backend: AdminSettings): SystemSettings {
  const providers: Record<string, ProviderConfig> = { ...DEFAULT_PROVIDERS }
  if (backend.providers) {
    for (const [key, cfg] of Object.entries(backend.providers)) {
      providers[key] = { ...providers[key], ...cfg }
    }
  }
  return {
    ...local,
    llm: {
      ...local.llm,
      provider: backend.llm?.provider ?? local.llm.provider,
      model: backend.llm?.model ?? local.llm.model,
      temperature: backend.llm?.temperature ?? local.llm.temperature,
      max_tokens: backend.llm?.max_tokens ?? local.llm.max_tokens,
    },
    providers,
    cost_budget_daily: backend.cost_fuse?.daily_cny ?? local.cost_budget_daily,
    cost_budget_monthly: backend.cost_fuse?.monthly_cny ?? local.cost_budget_monthly,
    pass_threshold: backend.authenticity?.pass_threshold ?? local.pass_threshold,
    excellent_threshold: backend.authenticity?.excellent_threshold ?? local.excellent_threshold,
  }
}

const Settings: React.FC = () => {
  const [costStatus, setCostStatus] = useState<CostStatus | null>(null)
  const [healthStatus, setHealthStatus] = useState<HealthStatus | null>(null)
  const [settings, setSettings] = useState<SystemSettings>(loadLocalSettings)
  const [backendSettings, setBackendSettings] = useState<AdminSettings | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [backendAvailable, setBackendAvailable] = useState(true)
  // Track per-provider API key input values (empty = unchanged, non-empty = update).
  const [apiKeyInputs, setApiKeyInputs] = useState<Record<string, string>>({})

  const fetchStatus = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [cost, health, admin] = await Promise.all([
        getCostStatus().catch(() => null),
        getHealthCheck().catch(() => null),
        getAdminSettings().catch(() => null),
      ])
      setCostStatus(cost)
      setHealthStatus(health)
      if (admin) {
        setBackendSettings(admin)
        setSettings((prev) => mergeBackendSettings(prev, admin))
        setBackendAvailable(true)
      }
      if (!cost && !health && !admin) {
        setError('无法连接到后端服务，请确认服务已启动')
        setBackendAvailable(false)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '获取状态失败')
      setBackendAvailable(false)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchStatus()
    const interval = setInterval(fetchStatus, 30000)
    return () => clearInterval(interval)
  }, [fetchStatus])

  const handleSave = async () => {
    setSaving(true)
    try {
      const providersPayload: Record<string, ProviderConfig> = {}
      const providers = settings.providers ?? DEFAULT_PROVIDERS
      for (const { key } of PROVIDERS) {
        const cfg = providers[key]
        if (!cfg) continue
        const update: ProviderConfig = {
          base_url: cfg.base_url,
          model: cfg.model,
        }
        const inputKey = apiKeyInputs[key]?.trim()
        if (inputKey !== undefined) {
          update.api_key = inputKey
        }
        providersPayload[key] = update
      }

      const payload: Record<string, unknown> = {
        llm_provider: settings.llm.provider,
        llm_model: settings.llm.model,
        temperature: settings.llm.temperature,
        max_tokens: settings.llm.max_tokens,
        providers: providersPayload,
        pass_threshold: settings.pass_threshold,
        excellent_threshold: settings.excellent_threshold,
      }
      const apiResult = await updateAdminSettings(payload)
      saveToLocal(settings)
      setApiKeyInputs({})
      if (apiResult.status === 'ok' || apiResult.status === 'partial') {
        message.success('设置已同步到后端和本地')
        if (apiResult.status === 'partial' && apiResult.rejected) {
          const rejectedKeys = Object.keys(apiResult.rejected).join(', ')
          message.warning(`部分字段未保存: ${rejectedKeys}`)
        }
      } else {
        message.success('设置已保存到本地（后端同步未确认）')
      }
    } catch {
      saveToLocal(settings)
      message.warning('设置已保存到本地（后端不可用）')
    } finally {
      setSaving(false)
    }
  }

  const fuseConfig: Record<string, { color: string; label: string }> = {
    NORMAL: { color: 'green', label: '正常' },
    WARNING: { color: 'orange', label: '警告' },
    DEGRADE: { color: 'orange', label: '降级' },
    FUSE: { color: 'red', label: '熔断' },
    EMERGENCY: { color: 'red', label: '紧急' },
  }

  const providers = settings.providers ?? DEFAULT_PROVIDERS
  const activeModels = DEFAULT_PROVIDER_MODELS[settings.llm.provider] ?? []

  return (
    <div>
      <Title level={4} style={{ marginBottom: 16 }}>
        <SettingOutlined /> 系统设置
      </Title>

      {error && (
        <Alert message="状态获取失败" description={error} type="error" showIcon closable
          style={{ marginBottom: 16 }} onClose={() => setError(null)} />
      )}

      {!backendAvailable && (
        <Alert message="后端连接不可用" description="当前显示本地缓存设置，保存后将写入本地。" type="warning" showIcon
          style={{ marginBottom: 16 }} />
      )}

      <Spin spinning={loading && !costStatus && !healthStatus}>
        <Row gutter={[16, 16]}>
          <Col xs={24} md={12}>
            <Card title={<><HeartOutlined /> 系统健康状态</>}
              extra={<Button size="small" icon={<ReloadOutlined />} onClick={fetchStatus}>刷新</Button>}>
              {healthStatus ? (
                <Descriptions size="small" column={1}>
                  <Descriptions.Item label="服务状态">
                    <Tag color={healthStatus.status === 'healthy' ? 'green' : 'red'}
                      icon={healthStatus.status === 'healthy' ? <CheckCircleOutlined /> : <CloseCircleOutlined />}>
                      {healthStatus.status === 'healthy' ? '健康' : '异常'}
                    </Tag>
                  </Descriptions.Item>
                  <Descriptions.Item label="环境">{healthStatus.environment}</Descriptions.Item>
                  <Descriptions.Item label="版本">{healthStatus.version}</Descriptions.Item>
                </Descriptions>
              ) : (
                <Typography.Text type="secondary">无法获取健康状态</Typography.Text>
              )}
            </Card>
          </Col>

          <Col xs={24} md={12}>
            <Card title={<><WalletOutlined /> 成本总览</>}
              extra={<Button size="small" icon={<ReloadOutlined />} onClick={fetchStatus}>刷新</Button>}>
              {costStatus ? (
                <Row gutter={16}>
                  <Col span={8}>
                    <Statistic title="累计成本" value={costStatus.total_cost_cny} precision={2} suffix="¥" valueStyle={{ fontSize: 18 }} />
                  </Col>
                  <Col span={8}>
                    <Statistic title="今日成本" value={costStatus.daily_cost_cny} precision={2} suffix="¥" valueStyle={{ fontSize: 18 }} />
                  </Col>
                  <Col span={8}>
                    <Statistic title="熔断状态" value={fuseConfig[costStatus.fuse_status]?.label ?? costStatus.fuse_status} valueStyle={{ fontSize: 18 }} />
                  </Col>
                </Row>
              ) : (
                <Typography.Text type="secondary">无法获取成本数据</Typography.Text>
              )}
            </Card>
          </Col>
        </Row>
      </Spin>

      {backendSettings && (
        <Card title={<><RobotOutlined /> 后端配置摘要</>} style={{ marginTop: 16 }} size="small">
          <Descriptions size="small" bordered column={{ xs: 1, sm: 2, md: 3 }}>
            <Descriptions.Item label="环境">{backendSettings.environment}</Descriptions.Item>
            <Descriptions.Item label="日志级别">{backendSettings.log_level}</Descriptions.Item>
            <Descriptions.Item label="默认选择集数">{backendSettings.study_defaults?.n_choice_sets}</Descriptions.Item>
            <Descriptions.Item label="默认选项数">{backendSettings.study_defaults?.n_alternatives}</Descriptions.Item>
            <Descriptions.Item label="默认样本量">{backendSettings.study_defaults?.sample_size}</Descriptions.Item>
            <Descriptions.Item label="D-efficiency 目标">{backendSettings.study_defaults?.d_efficiency_target}</Descriptions.Item>
          </Descriptions>
        </Card>
      )}

      <Card title={<><RobotOutlined /> LLM 模型配置</>} style={{ marginTop: 16 }}>
        <Descriptions size="small" bordered column={1} style={{ marginBottom: 16 }}>
          <Descriptions.Item label="当前模型提供商">
            <Select value={settings.llm.provider} style={{ width: 200 }}
              onChange={(v) => setSettings((prev) => ({
                ...prev,
                llm: { ...prev.llm, provider: v, model: DEFAULT_PROVIDER_MODELS[v]?.[0] ?? '' },
              }))}>
              {PROVIDERS.map((p) => (
                <Option key={p.key} value={p.key}>{p.label}</Option>
              ))}
            </Select>
          </Descriptions.Item>
          <Descriptions.Item label="当前模型名称">
            <Select value={settings.llm.model || activeModels[0] || ''} style={{ width: 300 }}
              onChange={(v) => setSettings((prev) => ({ ...prev, llm: { ...prev.llm, model: v } }))}>
              {activeModels.map((m) => (
                <Option key={m} value={m}>{m}</Option>
              ))}
            </Select>
          </Descriptions.Item>
          <Descriptions.Item label="温度 (Temperature)">
            <Slider min={0} max={2} step={0.05} value={settings.llm.temperature} style={{ width: 300 }}
              marks={{ 0: '0', 0.5: '0.5', 1: '1', 2: '2' }}
              onChange={(v) => setSettings((prev) => ({ ...prev, llm: { ...prev.llm, temperature: v } }))} />
          </Descriptions.Item>
          <Descriptions.Item label="最大 Token 数">
            <InputNumber min={256} max={32768} step={256} value={settings.llm.max_tokens}
              onChange={(v) => setSettings((prev) => ({ ...prev, llm: { ...prev.llm, max_tokens: v ?? 4096 } }))} />
          </Descriptions.Item>
        </Descriptions>

        <Divider orientation="left">供应商配置（密钥保存在后端并加密）</Divider>
        <Collapse defaultActiveKey={[settings.llm.provider]}>
          {PROVIDERS.map((p) => {
            const cfg = providers[p.key] ?? DEFAULT_PROVIDERS[p.key]
            const keyInput = apiKeyInputs[p.key]
            const displayKey = keyInput === undefined
              ? (cfg.api_key_set ? '*** 已设置 ***' : '')
              : keyInput
            return (
              <Panel header={`${p.label}${cfg.enabled ? '（已启用）' : '（未启用）'}`} key={p.key}>
                <Descriptions size="small" bordered column={1}>
                  <Descriptions.Item label="基地址 (Base URL)">
                    <Input value={cfg.base_url}
                      onChange={(e) => setSettings((prev) => ({
                        ...prev,
                        providers: {
                          ...providers,
                          [p.key]: { ...cfg, base_url: e.target.value },
                        },
                      }))} />
                  </Descriptions.Item>
                  <Descriptions.Item label="默认模型">
                    <Input value={cfg.model}
                      onChange={(e) => setSettings((prev) => ({
                        ...prev,
                        providers: {
                          ...providers,
                          [p.key]: { ...cfg, model: e.target.value },
                        },
                      }))} />
                  </Descriptions.Item>
                  <Descriptions.Item label="API Key">
                    <Input.Password
                      placeholder={cfg.api_key_set ? '已设置，留空保持不变' : '请输入 API Key'}
                      value={displayKey}
                      onChange={(e) => setApiKeyInputs((prev) => ({ ...prev, [p.key]: e.target.value }))}
                    />
                  </Descriptions.Item>
                </Descriptions>
              </Panel>
            )
          })}
        </Collapse>

        <Divider />

        <Descriptions size="small" bordered column={1} style={{ marginBottom: 16 }}>
          <Descriptions.Item label="日成本预算 (¥)">
            <InputNumber min={0} step={10} value={settings.cost_budget_daily}
              onChange={(v) => setSettings((prev) => ({ ...prev, cost_budget_daily: v ?? 50 }))} prefix="¥" />
          </Descriptions.Item>
          <Descriptions.Item label="月成本预算 (¥)">
            <InputNumber min={0} step={100} value={settings.cost_budget_monthly}
              onChange={(v) => setSettings((prev) => ({ ...prev, cost_budget_monthly: v ?? 1000 }))} prefix="¥" />
          </Descriptions.Item>
          <Descriptions.Item label="真实性通过阈值">
            <InputNumber min={0} max={20} step={1} value={settings.pass_threshold}
              onChange={(v) => setSettings((prev) => ({ ...prev, pass_threshold: v ?? 9 }))} />
          </Descriptions.Item>
          <Descriptions.Item label="真实性优秀阈值">
            <InputNumber min={0} max={20} step={1} value={settings.excellent_threshold}
              onChange={(v) => setSettings((prev) => ({ ...prev, excellent_threshold: v ?? 12 }))} />
          </Descriptions.Item>
        </Descriptions>

        <Button type="primary" icon={<SaveOutlined />} onClick={handleSave} loading={saving}>
          保存设置
        </Button>
      </Card>
    </div>
  )
}

export default Settings
