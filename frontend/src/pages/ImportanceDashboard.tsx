import React, { useEffect, useMemo, useState, useCallback } from 'react'
import {
  Card,
  Row,
  Col,
  Select,
  Button,
  Spin,
  Alert,
  Statistic,
  Tag,
  Space,
  Tabs,
  Table,
  Empty,
  Typography,
} from 'antd'
import {
  BarChartOutlined,
  ReloadOutlined,
  PlayCircleOutlined,
  CheckCircleOutlined,
  ExclamationCircleOutlined,
} from '@ant-design/icons'
import ReactECharts from 'echarts-for-react'
import { useSearchParams } from 'react-router-dom'
import {
  getStudies,
  getImportance,
  getConvergence,
  getWTP,
  analyzeStudy,
  getAnalysisStatus,
} from '@/services/api'
import { useAppStore } from '@/stores/appStore'
import type { ImportanceResponse, StudySummary, WTPResponse, WTPAttribute, WTPComparison } from '@/types/api'

const { Option } = Select
const { TabPane } = Tabs
const { Title } = Typography

// ---------------------------------------------------------------------------
// Helper: build bar chart option for attribute importance
// ---------------------------------------------------------------------------

export function buildImportanceChartOption(importance: ImportanceResponse | null) {
  if (!importance || !importance.overall) return {}

  const entries = Object.entries(importance.overall).sort((a, b) => b[1].mean - a[1].mean)
  const names = entries.map(([k]) => k)
  const means = entries.map(([, v]) => +(v.mean * 100).toFixed(2))
  const lower = entries.map(([, v]) => +((v.ci_95_lower ?? v.mean) * 100).toFixed(2))
  const upper = entries.map(([, v]) => +((v.ci_95_upper ?? v.mean) * 100).toFixed(2))

  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: (params: unknown[]) => {
        const p = params[0] as { name: string; value: number }
        const idx = names.indexOf(p.name)
        const l = lower[idx]
        const u = upper[idx]
        return `${p.name}<br/>重要性: ${p.value}%<br/>95% CI: [${l}%, ${u}%]`
      },
    },
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
    xAxis: {
      type: 'category',
      data: names,
      axisLabel: { rotate: 30, interval: 0 },
    },
    yAxis: {
      type: 'value',
      name: '重要性 (%)',
      max: 100,
    },
    series: [
      {
        name: '重要性',
        type: 'bar',
        data: means,
        itemStyle: {
          color: (params: { dataIndex: number }) => {
            const colors = ['#5470c6', '#91cc75', '#fac858', '#ee6666', '#73c0de', '#3ba272']
            return colors[params.dataIndex % colors.length]
          },
          borderRadius: [4, 4, 0, 0],
        },
        barMaxWidth: 60,
      },
    ],
  }
}

// ---------------------------------------------------------------------------
// Helper: build pie chart option for attribute importance
// ---------------------------------------------------------------------------

export function buildImportancePieOption(importance: ImportanceResponse | null) {
  if (!importance || !importance.overall) return {}

  const data = Object.entries(importance.overall)
    .sort((a, b) => b[1].mean - a[1].mean)
    .map(([name, stats]) => ({
      name,
      value: +(stats.mean * 100).toFixed(2),
    }))

  return {
    tooltip: {
      trigger: 'item',
      formatter: '{b}: {c}% ({d}%)',
    },
    legend: {
      orient: 'vertical',
      right: 10,
      top: 'center',
    },
    series: [
      {
        name: '属性重要性',
        type: 'pie',
        radius: ['40%', '70%'],
        avoidLabelOverlap: false,
        itemStyle: {
          borderRadius: 8,
          borderColor: '#fff',
          borderWidth: 2,
        },
        label: {
          show: true,
          formatter: '{b}\n{c}%',
        },
        emphasis: {
          label: { show: true, fontSize: 16, fontWeight: 'bold' },
        },
        data,
      },
    ],
  }
}

export function getRhatStatusColor(rhatMax: number): string {
  return rhatMax > 1.1 ? '#cf1322' : '#3f8600'
}

export function getPriceCoefficientColor(mean: number): string {
  return mean < 0 ? '#3f8600' : '#cf1322'
}

export function buildImportanceTableData(importance: ImportanceResponse | null) {
  if (!importance?.overall) return []
  return Object.entries(importance.overall)
    .sort((a, b) => b[1].mean - a[1].mean)
    .map(([attr, stats], idx) => ({
      key: attr,
      rank: idx + 1,
      attribute: attr,
      mean: stats.mean,
      std: stats.std,
      ciLower: stats.ci_95_lower,
      ciUpper: stats.ci_95_upper,
    }))
}

export function buildWTPTableData(wtp: WTPResponse | null) {
  if (!wtp?.wtp_values) return []
  const rows: Array<{
    key: string
    attribute: string
    fromLevel: string
    toLevel: string
    wtpMean: number
    wtpMedian: number
    wtpStd: number
    ciLower: number
    ciUpper: number
  }> = []
  Object.entries(wtp.wtp_values).forEach(([attr, attrData]: [string, WTPAttribute]) => {
    attrData.comparisons.forEach((c: WTPComparison) => {
      rows.push({
        key: `${attr}-${c.from_level}-${c.to_level}`,
        attribute: attr,
        fromLevel: c.from_level,
        toLevel: c.to_level,
        wtpMean: c.wtp_mean,
        wtpMedian: c.wtp_median,
        wtpStd: c.wtp_std,
        ciLower: c.ci_95_lower,
        ciUpper: c.ci_95_upper,
      })
    })
  })
  return rows
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const ImportanceDashboard: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams()
  const {
    selectedStudyId,
    selectedAnalysisId,
    setSelectedStudy,
    setSelectedAnalysis,
    addJob,
    updateJob,
    runningJobs,
    studies,
    setStudies,
  } = useAppStore()

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [importance, setImportance] = useState<ImportanceResponse | null>(null)
  const [convergence, setConvergence] = useState<import('@/types/api').ConvergenceDiagnostics | null>(null)
  const [wtp, setWTP] = useState<import('@/types/api').WTPResponse | null>(null)
  const [pollingId, setPollingId] = useState<ReturnType<typeof setInterval> | null>(null)

  // Initialize from URL params
  useEffect(() => {
    const studyId = searchParams.get('study')
    const analysisId = searchParams.get('analysis')
    if (studyId) setSelectedStudy(studyId)
    if (analysisId) setSelectedAnalysis(analysisId)
  }, [searchParams, setSelectedStudy, setSelectedAnalysis])

  // Load studies on mount
  useEffect(() => {
    getStudies().then((res) => setStudies(res.studies)).catch(() => {})
  }, [setStudies])

  // ---------------------------------------------------------------------------
  // Fetch importance / convergence / WTP when study+analysis selected
  // ---------------------------------------------------------------------------

  const fetchResults = useCallback(async () => {
    if (!selectedStudyId || !selectedAnalysisId) return
    setLoading(true)
    setError(null)
    try {
      const [impRes, convRes, wtpRes] = await Promise.all([
        getImportance(selectedStudyId, selectedAnalysisId),
        getConvergence(selectedStudyId, selectedAnalysisId),
        getWTP(selectedStudyId, selectedAnalysisId),
      ])
      setImportance(impRes)
      setConvergence(convRes)
      setWTP(wtpRes)
    } catch (err) {
      setError(err instanceof Error ? err.message : '获取分析结果失败')
    } finally {
      setLoading(false)
    }
  }, [selectedStudyId, selectedAnalysisId])

  useEffect(() => {
    fetchResults()
  }, [fetchResults])

  // ---------------------------------------------------------------------------
  // Poll running jobs
  // ---------------------------------------------------------------------------

  useEffect(() => {
    if (runningJobs.length === 0) {
      if (pollingId) {
        clearInterval(pollingId)
        setPollingId(null)
      }
      return
    }

    const id = setInterval(async () => {
      for (const job of runningJobs) {
        try {
          const status = await getAnalysisStatus(job.study_id, job.analysis_id)
          updateJob(status)
          if (status.status === 'COMPLETED' || status.status === 'FAILED') {
            // Keep job in store for cross-page visibility (AnalysisStatus page)
            updateJob(status)
            if (
              status.status === 'COMPLETED' &&
              job.study_id === selectedStudyId &&
              job.analysis_id === selectedAnalysisId
            ) {
              fetchResults()
            }
          }
        } catch {
          // ignore polling errors
        }
      }
    }, 3000)

    setPollingId(id)
    return () => clearInterval(id)
  }, [runningJobs, selectedStudyId, selectedAnalysisId, updateJob, fetchResults])

  // ---------------------------------------------------------------------------
  // Run analysis
  // ---------------------------------------------------------------------------

  const handleRunAnalysis = async () => {
    if (!selectedStudyId) return
    setLoading(true)
    setError(null)
    try {
      const job = await analyzeStudy(selectedStudyId, 'hb')
      addJob(job)
      setSelectedAnalysis(job.analysis_id)
      setSearchParams({ study: selectedStudyId, analysis: job.analysis_id })
    } catch (err) {
      setError(err instanceof Error ? err.message : '启动分析失败')
    } finally {
      setLoading(false)
    }
  }

  // ---------------------------------------------------------------------------
  // Table data
  // ---------------------------------------------------------------------------

  const importanceTableData = useMemo(() => buildImportanceTableData(importance), [importance])

  const wtpTableData = useMemo(() => buildWTPTableData(wtp), [wtp])

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  const hasResults = importance !== null && convergence !== null

  return (
    <div>
      <Title level={4} style={{ marginBottom: 16 }}>
        <BarChartOutlined /> 属性重要性可视化看板
      </Title>

      {/* Control bar */}
      <Card style={{ marginBottom: 16 }}>
        <Space wrap>
          <Select
            placeholder="选择研究项目"
            style={{ width: 240 }}
            value={selectedStudyId || undefined}
            onChange={(val) => {
              setSelectedStudy(val)
              setSelectedAnalysis(null)
              setImportance(null)
              setConvergence(null)
              setWTP(null)
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

          {selectedStudyId && (
            <Button
              type="primary"
              icon={<PlayCircleOutlined />}
              onClick={handleRunAnalysis}
              loading={loading}
            >
              运行 HB 分析
            </Button>
          )}

          {selectedAnalysisId && (
            <Tag icon={<CheckCircleOutlined />} color="success">
              分析ID: {selectedAnalysisId}
            </Tag>
          )}

          {runningJobs.length > 0 && (
            <Tag icon={<ReloadOutlined spin />} color="processing">
              {runningJobs.length} 个任务运行中
            </Tag>
          )}
        </Space>
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

      {/* Convergence diagnostics */}
      {convergence && (
        <Card style={{ marginBottom: 16 }} title="收敛诊断">
          <Row gutter={16}>
            <Col span={6}>
              <Statistic
                title="R-hat Max"
                value={convergence.rhat_max}
                precision={3}
                valueStyle={{
                  color: getRhatStatusColor(convergence.rhat_max),
                }}
                prefix={
                  convergence.rhat_max > 1.1 ? (
                    <ExclamationCircleOutlined />
                  ) : (
                    <CheckCircleOutlined />
                  )
                }
              />
            </Col>
            <Col span={6}>
              <Statistic
                title="ESS Bulk Min"
                value={convergence.ess_bulk_min}
                precision={0}
              />
            </Col>
            <Col span={6}>
              <Statistic
                title="ESS Tail Min"
                value={convergence.ess_tail_min}
                precision={0}
              />
            </Col>
            <Col span={6}>
              <Statistic
                title="收敛状态"
                value={convergence.converged ? '已收敛' : '未收敛'}
                valueStyle={{
                  color: convergence.converged ? '#3f8600' : '#cf1322',
                }}
              />
            </Col>
          </Row>
          {convergence.rhat_max > 1.1 && (
            <Alert
              message="警告: R-hat > 1.1，模型未收敛，结果不可靠"
              type="warning"
              showIcon
              style={{ marginTop: 12 }}
            />
          )}
        </Card>
      )}

      {/* Main content */}
      <Spin spinning={loading && !hasResults}>
        {!hasResults && !error ? (
          <Empty
            description={
              selectedStudyId
                ? '请选择研究项目并运行分析'
                : '请先选择一个研究项目'
            }
            style={{ marginTop: 64 }}
          />
        ) : (
          <Tabs defaultActiveKey="bar">
            <TabPane tab="柱状图" key="bar">
              <Row gutter={[16, 16]}>
                <Col xs={24} lg={16}>
                  <Card title="属性重要性排名">
                    <ReactECharts
                      option={buildImportanceChartOption(importance)}
                      style={{ height: 400 }}
                      opts={{ renderer: 'canvas' }}
                    />
                  </Card>
                </Col>
                <Col xs={24} lg={8}>
                  <Card title="重要性占比">
                    <ReactECharts
                      option={buildImportancePieOption(importance)}
                      style={{ height: 400 }}
                      opts={{ renderer: 'canvas' }}
                    />
                  </Card>
                </Col>
              </Row>
            </TabPane>

            <TabPane tab="数据表格" key="table">
              <Card title="属性重要性统计">
                <Table
                  dataSource={importanceTableData}
                  size="small"
                  pagination={false}
                  columns={[
                    { title: '排名', dataIndex: 'rank', width: 60 },
                    { title: '属性', dataIndex: 'attribute' },
                    {
                      title: '重要性均值',
                      dataIndex: 'mean',
                      render: (v: number) => `${(v * 100).toFixed(2)}%`,
                      sorter: (a, b) => a.mean - b.mean,
                    },
                    {
                      title: '标准差',
                      dataIndex: 'std',
                      render: (v: number) => `${(v * 100).toFixed(2)}%`,
                    },
                    {
                      title: '95% CI 下限',
                      dataIndex: 'ciLower',
                      render: (v: number) => `${(v * 100).toFixed(2)}%`,
                    },
                    {
                      title: '95% CI 上限',
                      dataIndex: 'ciUpper',
                      render: (v: number) => `${(v * 100).toFixed(2)}%`,
                    },
                  ]}
                />
              </Card>
            </TabPane>

            <TabPane tab="WTP (支付意愿)" key="wtp">
              <Card title="支付意愿分析">
                {wtp && (
                  <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
                    <Col span={6}>
                      <Statistic
                        title="价格系数均值"
                        value={wtp.price_coefficient_summary.mean}
                        precision={4}
                        valueStyle={{
                          color: getPriceCoefficientColor(wtp.price_coefficient_summary.mean),
                        }}
                        prefix={
                          wtp.price_coefficient_summary.mean < 0 ? (
                            <CheckCircleOutlined />
                          ) : (
                            <ExclamationCircleOutlined />
                          )
                        }
                      />
                    </Col>
                    <Col span={6}>
                      <Statistic
                        title="负系数比例"
                        value={wtp.price_coefficient_summary.negative_rate * 100}
                        suffix="%"
                        precision={1}
                      />
                    </Col>
                    <Col span={6}>
                      <Statistic
                        title="正异常值数"
                        value={wtp.price_coefficient_summary.n_positive_outliers}
                      />
                    </Col>
                    <Col span={6}>
                      <Statistic
                        title="价格系数标准差"
                        value={wtp.price_coefficient_summary.std}
                        precision={4}
                      />
                    </Col>
                  </Row>
                )}
                <Table
                  dataSource={wtpTableData}
                  size="small"
                  scroll={{ x: 'max-content' }}
                  columns={[
                    { title: '属性', dataIndex: 'attribute', fixed: 'left' },
                    { title: '从等级', dataIndex: 'fromLevel' },
                    { title: '到等级', dataIndex: 'toLevel' },
                    {
                      title: 'WTP 均值',
                      dataIndex: 'wtpMean',
                      render: (v: number) => `¥${v.toFixed(2)}`,
                    },
                    {
                      title: 'WTP 中位数',
                      dataIndex: 'wtpMedian',
                      render: (v: number) => `¥${v.toFixed(2)}`,
                    },
                    {
                      title: '标准差',
                      dataIndex: 'wtpStd',
                      render: (v: number) => `¥${v.toFixed(2)}`,
                    },
                    {
                      title: '95% CI 下限',
                      dataIndex: 'ciLower',
                      render: (v: number) => `¥${v.toFixed(2)}`,
                    },
                    {
                      title: '95% CI 上限',
                      dataIndex: 'ciUpper',
                      render: (v: number) => `¥${v.toFixed(2)}`,
                    },
                  ]}
                />
              </Card>
            </TabPane>
          </Tabs>
        )}
      </Spin>
    </div>
  )
}

export default ImportanceDashboard
