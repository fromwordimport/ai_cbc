import React, { useEffect, useState, useCallback } from 'react'
import {
  Card,
  Row,
  Col,
  Select,
  Button,
  InputNumber,
  Input,
  Spin,
  Alert,
  Space,
  Table,
  Tag,
  Empty,
  Typography,
  Divider,
  Popconfirm,
  Tooltip,
} from 'antd'
import {
  PieChartOutlined,
  PlusOutlined,
  DeleteOutlined,
  PlayCircleOutlined,
  InfoCircleOutlined,
  ExclamationCircleOutlined,
} from '@ant-design/icons'
import ReactECharts from 'echarts-for-react'
import { useSearchParams } from 'react-router-dom'
import {
  getStudies,
  getStudyDesign,
  getAnalysisResult,
  simulateMarket,
} from '@/services/api'
import { useAppStore } from '@/stores/appStore'
import type {
  StudySummary,
  ProductScenario,
  ScenarioShare,
  AnalysisResultResponse,
  AttributeDefinition,
} from '@/types/api'

const { Option } = Select
const { Title, Text } = Typography

// ---------------------------------------------------------------------------
// Fallback dishwasher levels (used only when study has no attributes)
// ---------------------------------------------------------------------------

const FALLBACK_ATTRIBUTES: AttributeDefinition[] = [
  { id: 'price', name: '价格', type: 'price', levels: [] },
  { id: 'capacity', name: '容量', type: 'categorical', levels: [{ value: '6套', label: '6套' }, { value: '8套', label: '8套' }, { value: '10套', label: '10套' }, { value: '13套', label: '13套' }, { value: '15套', label: '15套' }] },
  { id: 'installation', name: '安装方式', type: 'categorical', levels: [{ value: '台式', label: '台式' }, { value: '嵌入式', label: '嵌入式' }, { value: '独立式', label: '独立式' }, { value: '水槽式', label: '水槽式' }] },
  { id: 'features', name: '功能配置', type: 'categorical', levels: [{ value: '基础款', label: '基础款' }, { value: '智能款', label: '智能款' }, { value: '旗舰款', label: '旗舰款' }] },
  { id: 'brand', name: '品牌', type: 'categorical', levels: [{ value: '美的', label: '美的' }, { value: '西门子', label: '西门子' }, { value: '海尔', label: '海尔' }, { value: '方太', label: '方太' }, { value: '老板', label: '老板' }] },
  { id: 'energy', name: '能效', type: 'categorical', levels: [{ value: '一级', label: '一级' }, { value: '二级', label: '二级' }, { value: '三级', label: '三级' }] },
]

export function buildDefaultScenario(attributes: AttributeDefinition[]): ProductScenario {
  const attrs: Record<string, string | number> = {}
  attributes.forEach((attr) => {
    if (attr.type === 'price' || attr.type === 'continuous') {
      attrs[attr.id] = attr.id === 'price' ? 3999 : 0
    } else if (attr.levels.length > 0) {
      attrs[attr.id] = attr.levels[0].value
    } else {
      attrs[attr.id] = ''
    }
  })
  return { name: '产品 A', attributes: attrs }
}

// ---------------------------------------------------------------------------
// Chart builders
// ---------------------------------------------------------------------------

export function buildSharePieOption(shares: ScenarioShare[]) {
  return {
    tooltip: {
      trigger: 'item',
      formatter: '{b}: {c}% ({d}%)',
    },
    legend: { bottom: 0 },
    series: [
      {
        name: '市场份额',
        type: 'pie',
        radius: ['35%', '65%'],
        center: ['50%', '45%'],
        itemStyle: { borderRadius: 6, borderColor: '#fff', borderWidth: 2 },
        label: { show: true, formatter: '{b}\n{c}%' },
        data: shares.map((s) => ({
          name: s.name,
          value: +(s.predicted_share * 100).toFixed(2),
        })),
      },
    ],
  }
}

export function buildShareBarOption(shares: ScenarioShare[]) {
  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: (params: unknown[]) => {
        const p = params[0] as { name: string; value: number }
        const share = shares.find((s) => s.name === p.name)
        if (!share) return p.name
        return `${p.name}<br/>份额: ${p.value}%<br/>95% CI: [${(share.share_ci_95_lower * 100).toFixed(1)}%, ${(share.share_ci_95_upper * 100).toFixed(1)}%]`
      },
    },
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
    xAxis: {
      type: 'category',
      data: shares.map((s) => s.name),
      axisLabel: { interval: 0, rotate: shares.length > 5 ? 30 : 0 },
    },
    yAxis: { type: 'value', name: '市场份额 (%)', max: 100 },
    series: [
      {
        name: '份额',
        type: 'bar',
        data: shares.map((s) => +(s.predicted_share * 100).toFixed(2)),
        itemStyle: {
          color: (params: { dataIndex: number }) => {
            const colors = ['#5470c6', '#91cc75', '#fac858', '#ee6666', '#73c0de', '#3ba272', '#fc8452']
            return colors[params.dataIndex % colors.length]
          },
          borderRadius: [4, 4, 0, 0],
        },
        barMaxWidth: 80,
      },
    ],
  }
}

export function buildScenarioName(index: number): string {
  const names = 'ABCDEFGHIJ'
  return `产品 ${names[index]}`
}

export function validateScenarios(scenarios: ProductScenario[]): string | null {
  if (scenarios.length < 2) return '至少需要配置 2 个产品场景'
  return null
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const MarketSimulator: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams()
  const {
    selectedStudyId,
    selectedAnalysisId,
    setSelectedStudy,
    setSelectedAnalysis,
    studies,
    setStudies,
  } = useAppStore()

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [analysisResult, setAnalysisResult] = useState<AnalysisResultResponse | null>(null)
  const [attributes, setAttributes] = useState<AttributeDefinition[]>(FALLBACK_ATTRIBUTES)
  const [scenarios, setScenarios] = useState<ProductScenario[]>([])
  const [simulationRule, setSimulationRule] = useState<'logit' | 'first_choice'>('logit')
  const [includeNone, setIncludeNone] = useState(true)
  const [shares, setShares] = useState<ScenarioShare[] | null>(null)

  // Init from URL
  useEffect(() => {
    const studyId = searchParams.get('study')
    const analysisId = searchParams.get('analysis')
    if (studyId) setSelectedStudy(studyId)
    if (analysisId) setSelectedAnalysis(analysisId)
  }, [searchParams, setSelectedStudy, setSelectedAnalysis])

  // Load studies
  useEffect(() => {
    getStudies().then((res) => setStudies(res.studies)).catch(() => {})
  }, [setStudies])

  // Load study design to build dynamic scenario controls
  useEffect(() => {
    if (!selectedStudyId) {
      setAttributes(FALLBACK_ATTRIBUTES)
      setScenarios([buildDefaultScenario(FALLBACK_ATTRIBUTES)])
      return
    }
    getStudyDesign(selectedStudyId)
      .then((res) => {
        const attrs = res.attributes?.length ? res.attributes : FALLBACK_ATTRIBUTES
        setAttributes(attrs)
        setScenarios((prev) => {
          if (prev.length > 0) return prev
          return [buildDefaultScenario(attrs), { ...buildDefaultScenario(attrs), name: '产品 B' }]
        })
      })
      .catch(() => {
        setAttributes(FALLBACK_ATTRIBUTES)
        setScenarios((prev) => (prev.length > 0 ? prev : [buildDefaultScenario(FALLBACK_ATTRIBUTES)]))
      })
  }, [selectedStudyId])

  // Fetch analysis result for validation
  const fetchAnalysisResult = useCallback(async () => {
    if (!selectedStudyId || !selectedAnalysisId) return
    try {
      const res = await getAnalysisResult(selectedStudyId, selectedAnalysisId)
      setAnalysisResult(res)
    } catch {
      setAnalysisResult(null)
    }
  }, [selectedStudyId, selectedAnalysisId])

  useEffect(() => {
    fetchAnalysisResult()
  }, [fetchAnalysisResult])

  // ---------------------------------------------------------------------------
  // Scenario management
  // ---------------------------------------------------------------------------

  const addScenario = () => {
    const nextIdx = scenarios.length
    if (nextIdx >= 10) return
    setScenarios((prev) => [
      ...prev,
      {
        ...buildDefaultScenario(attributes),
        name: buildScenarioName(nextIdx),
      },
    ])
  }

  const removeScenario = (idx: number) => {
    setScenarios((prev) => prev.filter((_, i) => i !== idx))
  }

  const updateScenario = (idx: number, field: string, value: string | number) => {
    setScenarios((prev) =>
      prev.map((s, i) => {
        if (i !== idx) return s
        if (field === 'name') {
          return { ...s, name: value as string }
        }
        return { ...s, attributes: { ...s.attributes, [field]: value } }
      }),
    )
  }

  // ---------------------------------------------------------------------------
  // Run simulation
  // ---------------------------------------------------------------------------

  const handleSimulate = async () => {
    if (!selectedStudyId || !selectedAnalysisId) {
      setError('请先选择研究项目和分析结果')
      return
    }
    const validationError = validateScenarios(scenarios)
    if (validationError) {
      setError(validationError)
      return
    }
    setLoading(true)
    setError(null)
    try {
      const res = await simulateMarket(selectedStudyId, selectedAnalysisId, {
        scenarios,
        rule: simulationRule,
        include_none: includeNone,
      })
      setShares(res.scenarios)
    } catch (err) {
      setError(err instanceof Error ? err.message : '模拟失败')
    } finally {
      setLoading(false)
    }
  }

  // ---------------------------------------------------------------------------
  // Table columns for shares
  // ---------------------------------------------------------------------------

  const shareColumns = [
    { title: '产品场景', dataIndex: 'name' },
    {
      title: '预测份额',
      dataIndex: 'predicted_share',
      render: (v: number) => `${(v * 100).toFixed(2)}%`,
      sorter: (a: ScenarioShare, b: ScenarioShare) => a.predicted_share - b.predicted_share,
    },
    {
      title: '95% CI 下限',
      dataIndex: 'share_ci_95_lower',
      render: (v: number) => `${(v * 100).toFixed(2)}%`,
    },
    {
      title: '95% CI 上限',
      dataIndex: 'share_ci_95_upper',
      render: (v: number) => `${(v * 100).toFixed(2)}%`,
    },
    {
      title: '区间宽度',
      render: (_: unknown, record: ScenarioShare) =>
        `${((record.share_ci_95_upper - record.share_ci_95_lower) * 100).toFixed(2)}%`,
    },
  ]

  // ---------------------------------------------------------------------------
  // Render helpers
  // ---------------------------------------------------------------------------

  const renderScenarioControl = (scenario: ProductScenario, idx: number, attr: AttributeDefinition) => {
    const value = scenario.attributes[attr.id]
    if (attr.type === 'price' || attr.type === 'continuous') {
      return (
        <InputNumber
          key={attr.id}
          style={{ width: '100%' }}
          value={typeof value === 'number' ? value : 0}
          onChange={(v) => updateScenario(idx, attr.id, v ?? 0)}
          min={0}
          step={attr.type === 'price' ? 100 : 1}
          prefix={attr.type === 'price' ? '¥' : undefined}
          placeholder={attr.name}
        />
      )
    }
    return (
      <Select
        key={attr.id}
        style={{ width: '100%' }}
        value={value as string}
        onChange={(v) => updateScenario(idx, attr.id, v)}
        placeholder={attr.name}
      >
        {attr.levels.map((level) => (
          <Option key={level.value} value={level.value}>
            {level.label}
          </Option>
        ))}
      </Select>
    )
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  const canSimulate = selectedStudyId && selectedAnalysisId && scenarios.length >= 2

  return (
    <div>
      <Title level={4} style={{ marginBottom: 16 }}>
        <PieChartOutlined /> 市场份额模拟器
      </Title>

      {/* Study / Analysis selector */}
      <Card style={{ marginBottom: 16 }} title="分析配置">
        <Space wrap>
          <Select
            placeholder="选择研究项目"
            style={{ width: 240 }}
            value={selectedStudyId || undefined}
            onChange={(val) => {
              setSelectedStudy(val)
              setSelectedAnalysis(null)
              setShares(null)
              setSearchParams(val ? { study: val } : {})
            }}
            allowClear
          >
            {studies.map((s: StudySummary) => (
              <Option key={s.study_id} value={s.study_id}>
                {s.study_id} ({s.product_category})
              </Option>
            ))}
          </Select>

          <Select
            placeholder="选择分析结果"
            style={{ width: 240 }}
            value={selectedAnalysisId || undefined}
            onChange={(val) => {
              setSelectedAnalysis(val)
              setShares(null)
              setSearchParams((prev) => {
                const next = new URLSearchParams(prev)
                if (val) next.set('analysis', val)
                else next.delete('analysis')
                return next
              })
            }}
            allowClear
            disabled={!selectedStudyId}
          >
            {/* Analysis selection can be populated by listing analyses for the selected study */}
          </Select>

          <Select
            value={simulationRule}
            onChange={(v) => setSimulationRule(v)}
            style={{ width: 140 }}
          >
            <Option value="logit">Logit 模型</Option>
            <Option value="first_choice">First Choice</Option>
          </Select>

          <Select
            value={includeNone ? 'include' : 'exclude'}
            onChange={(v) => setIncludeNone(v === 'include')}
            style={{ width: 160 }}
          >
            <Option value="include">包含"无"选项</Option>
            <Option value="exclude">不包含"无"选项</Option>
          </Select>
        </Space>

        {analysisResult && (
          <div style={{ marginTop: 12 }}>
            <Space>
              <Tag color={analysisResult.convergence.converged ? 'success' : 'error'}>
                收敛: {analysisResult.convergence.converged ? '已收敛' : '未收敛'}
              </Tag>
              <Tag>R-hat: {analysisResult.convergence.rhat_max.toFixed(3)}</Tag>
              <Tag>模型: {analysisResult.model_type.toUpperCase()}</Tag>
            </Space>
          </div>
        )}
      </Card>

      {/* Scenario builder */}
      <Card
        style={{ marginBottom: 16 }}
        title={
          <Space>
            <span>产品场景配置</span>
            <Tooltip title="配置 2-10 个产品场景进行市场份额预测">
              <InfoCircleOutlined style={{ color: '#999' }} />
            </Tooltip>
          </Space>
        }
        extra={
          <Button
            type="dashed"
            icon={<PlusOutlined />}
            onClick={addScenario}
            disabled={scenarios.length >= 10}
          >
            添加场景
          </Button>
        }
      >
        {scenarios.map((scenario, idx) => (
          <div key={idx} style={{ marginBottom: 16 }}>
            <Row gutter={[12, 12]} align="middle">
              <Col span={3}>
                <Input
                  value={scenario.name}
                  onChange={(e) => updateScenario(idx, 'name', e.target.value)}
                  placeholder="场景名称"
                />
              </Col>
              {attributes.map((attr) => (
                <Col span={3} key={attr.id}>
                  {renderScenarioControl(scenario, idx, attr)}
                </Col>
              ))}
              <Col span={2}>
                <Popconfirm
                  title="删除此场景?"
                  onConfirm={() => removeScenario(idx)}
                  disabled={scenarios.length <= 2}
                >
                  <Button
                    danger
                    icon={<DeleteOutlined />}
                    size="small"
                    disabled={scenarios.length <= 2}
                  />
                </Popconfirm>
              </Col>
            </Row>
            {idx < scenarios.length - 1 && <Divider style={{ margin: '12px 0' }} />}
          </div>
        ))}

        <div style={{ marginTop: 8 }}>
          <Button
            type="primary"
            icon={<PlayCircleOutlined />}
            onClick={handleSimulate}
            loading={loading}
            disabled={!canSimulate}
            size="large"
          >
            运行市场份额模拟
          </Button>
          {!canSimulate && (
            <Text type="secondary" style={{ marginLeft: 12 }}>
              <ExclamationCircleOutlined /> 请选择研究项目、分析结果，并确保至少 2 个场景
            </Text>
          )}
        </div>
      </Card>

      {error && (
        <Alert
          message="错误"
          description={error}
          type="error"
          showIcon
          style={{ marginBottom: 16 }}
          closable
          onClose={() => setError(null)}
        />
      )}

      {/* Results */}
      {shares && (
        <Spin spinning={loading}>
          <Row gutter={[16, 16]}>
            <Col xs={24} lg={12}>
              <Card title="市场份额分布">
                <ReactECharts
                  option={buildSharePieOption(shares)}
                  style={{ height: 400 }}
                  opts={{ renderer: 'canvas' }}
                />
              </Card>
            </Col>
            <Col xs={24} lg={12}>
              <Card title="份额对比">
                <ReactECharts
                  option={buildShareBarOption(shares)}
                  style={{ height: 400 }}
                  opts={{ renderer: 'canvas' }}
                />
              </Card>
            </Col>
            <Col xs={24}>
              <Card title="详细数据">
                <Table
                  dataSource={shares}
                  columns={shareColumns}
                  rowKey="name"
                  pagination={false}
                  size="small"
                />
              </Card>
            </Col>
          </Row>
        </Spin>
      )}

      {!shares && !loading && !error && (
        <Empty
          description="配置产品场景并点击运行模拟"
          style={{ marginTop: 64 }}
        />
      )}
    </div>
  )
}

export default MarketSimulator
