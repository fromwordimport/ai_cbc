import React, { useEffect, useState } from 'react'
import {
  Card, Table, Tag, Progress, Spin, Alert, Empty, Space,
  Button, Typography, Statistic, Row, Col, Select, message, Modal,
} from 'antd'
import {
  PlayCircleOutlined, ReloadOutlined, CheckCircleOutlined,
  CloseCircleOutlined, SyncOutlined, ClockCircleOutlined,
  ExperimentOutlined, FileTextOutlined, BarChartOutlined,
  ClusterOutlined,
} from '@ant-design/icons'
import { useAppStore } from '@/stores/appStore'
import {
  getStudies, analyzeStudy, getAnalysisStatus, getConvergence,
  getAnalysisVisualization, runLatentClassAnalysis, listAnalyses,
} from '@/services/api'
import type { StudySummary, AnalysisJobStatus, ConvergenceDiagnostics } from '@/types/api'

const { Title } = Typography

interface JobRow {
  job: AnalysisJobStatus
  convergence: ConvergenceDiagnostics | null
  convLoading: boolean
}

const AnalysisStatus: React.FC = () => {
  const {
    runningJobs, addJob, updateJob,
    completedJobs,
    studies, setStudies,
    setJobs,
  } = useAppStore()
  const [jobs, setJobRows] = useState<JobRow[]>([])
  const [error, setError] = useState<string | null>(null)
  const [selectedStudyId, setSelectedStudyId] = useState<string | undefined>()
  const [selectedModelType, setSelectedModelType] = useState<'hb' | 'mnl' | 'latent_class'>('hb')
  const [startingJob, setStartingJob] = useState(false)
  const [vizOpen, setVizOpen] = useState(false)
  const [vizData, setVizData] = useState<unknown>(null)
  const [vizLoading, setVizLoading] = useState(false)

  useEffect(() => {
    getStudies().then((res) => setStudies(res.studies)).catch(() => {})
  }, [setStudies])

  useEffect(() => {
    const allJobs = [...runningJobs, ...completedJobs]
    setJobRows((prev) =>
      allJobs.map((job) => {
        const existing = prev.find((j) => j.job.analysis_id === job.analysis_id)
        return {
          job,
          convergence: existing?.convergence ?? null,
          convLoading: existing?.convLoading ?? false,
        }
      }),
    )
  }, [runningJobs, completedJobs])

  useEffect(() => {
    if (runningJobs.length === 0) return
    const interval = setInterval(async () => {
      for (const job of runningJobs) {
        try {
          const status = await getAnalysisStatus(job.study_id, job.analysis_id)
          updateJob(status)
          if (status.status === 'COMPLETED') {
            fetchConvergence(job.study_id, job.analysis_id)
          }
        } catch { /* polling error */ }
      }
    }, 3000)
    return () => clearInterval(interval)
  }, [runningJobs, updateJob])

  const fetchConvergence = async (studyId: string, analysisId: string) => {
    setJobRows((prev) =>
      prev.map((j) =>
        j.job.analysis_id === analysisId ? { ...j, convLoading: true } : j,
      ),
    )
    try {
      const conv = await getConvergence(studyId, analysisId)
      setJobRows((prev) =>
        prev.map((j) =>
          j.job.analysis_id === analysisId ? { ...j, convergence: conv, convLoading: false } : j,
        ),
      )
    } catch {
      setJobRows((prev) =>
        prev.map((j) =>
          j.job.analysis_id === analysisId ? { ...j, convLoading: false } : j,
        ),
      )
    }
  }

  const handleStartAnalysis = async () => {
    if (!selectedStudyId) {
      message.warning('请选择研究项目')
      return
    }
    setStartingJob(true)
    setError(null)
    try {
      const job = await analyzeStudy(selectedStudyId, selectedModelType)
      addJob(job)
      message.success(`分析任务已启动: ${job.analysis_id}`)
    } catch (err) {
      const detail = (err as { detail?: string })?.detail
      setError(detail || (err instanceof Error ? err.message : '启动分析失败'))
    } finally {
      setStartingJob(false)
    }
  }

  const loadJobs = async () => {
    if (studies.length === 0) return
    try {
      const all: AnalysisJobStatus[] = []
      await Promise.all(
        studies.map(async (study) => {
          try {
            const jobsForStudy = await listAnalyses(study.study_id)
            all.push(...jobsForStudy)
          } catch {
            // ignore per-study errors
          }
        }),
      )
      setJobs(all)
    } catch {
      message.error('加载任务列表失败')
    }
  }

  useEffect(() => {
    loadJobs()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [studies])

  const statusConfig: Record<string, { color: string; icon: React.ReactNode; label: string }> = {
    PENDING: { color: 'default', icon: <ClockCircleOutlined />, label: '等待中' },
    QUEUED: { color: 'default', icon: <ClockCircleOutlined />, label: '排队中' },
    RUNNING: { color: 'processing', icon: <SyncOutlined spin />, label: '运行中' },
    COMPLETED: { color: 'success', icon: <CheckCircleOutlined />, label: '已完成' },
    FAILED: { color: 'error', icon: <CloseCircleOutlined />, label: '失败' },
    CANCELLED: { color: 'warning', icon: <CloseCircleOutlined />, label: '已取消' },
    TIMED_OUT: { color: 'warning', icon: <ClockCircleOutlined />, label: '超时' },
  }

  const columns = [
    {
      title: '分析ID',
      dataIndex: ['job', 'analysis_id'],
      key: 'analysis_id',
      width: 180,
      render: (text: string) => <code>{text}</code>,
    },
    {
      title: '研究ID',
      dataIndex: ['job', 'study_id'],
      key: 'study_id',
      width: 160,
    },
    {
      title: '模型',
      dataIndex: ['job', 'model_type'],
      key: 'model_type',
      width: 60,
      render: (v: string) => <Tag>{v.toUpperCase()}</Tag>,
    },
    {
      title: '状态',
      dataIndex: ['job', 'status'],
      key: 'status',
      width: 100,
      render: (s: string) => {
        const cfg = statusConfig[s] || statusConfig.PENDING
        return <Tag color={cfg.color} icon={cfg.icon}>{cfg.label}</Tag>
      },
    },
    {
      title: '进度',
      dataIndex: ['job', 'progress_percent'],
      key: 'progress',
      width: 160,
      render: (pct: number, record: JobRow) => (
        <Progress percent={pct} size="small"
          status={record.job.status === 'FAILED' ? 'exception' : record.job.status === 'COMPLETED' ? 'success' : 'active'} />
      ),
    },
    {
      title: '收敛',
      key: 'convergence',
      width: 180,
      render: (_: unknown, record: JobRow) => {
        if (record.job.status === 'RUNNING' || record.job.status === 'PENDING') return <Spin size="small" />
        if (record.convLoading) return <Spin size="small" />
        if (!record.convergence) return '-'
        return (
          <Space>
            <Tag color={record.convergence.converged ? 'success' : 'error'}>
              {record.convergence.converged ? '已收敛' : '未收敛'}
            </Tag>
            <Tag>R-hat: {record.convergence.rhat_max.toFixed(3)}</Tag>
          </Space>
        )
      },
    },
    {
      title: '操作',
      key: 'action',
      width: 220,
      render: (_: unknown, record: JobRow) => {
        const { study_id, analysis_id, status, model_type } = record.job
        const isCompleted = status === 'COMPLETED'
        return (
          <Space size="small">
            <Button
              size="small"
              icon={<FileTextOutlined />}
              disabled={!isCompleted}
              onClick={() =>
                window.open(
                  `/api/v1/studies/${study_id}/analysis/${analysis_id}/report?format=markdown`,
                  '_blank',
                )
              }
            >
              报告
            </Button>
            <Button
              size="small"
              icon={<BarChartOutlined />}
              disabled={!isCompleted}
              loading={vizLoading}
              onClick={async () => {
                setVizLoading(true)
                try {
                  const data = await getAnalysisVisualization(study_id, analysis_id, 'dashboard')
                  setVizData(data)
                  setVizOpen(true)
                } catch (err) {
                  message.error(err instanceof Error ? err.message : '加载可视化失败')
                } finally {
                  setVizLoading(false)
                }
              }}
            >
              可视化
            </Button>
            {model_type !== 'latent_class' && (
              <Button
                size="small"
                icon={<ClusterOutlined />}
                disabled={!isCompleted}
                onClick={async () => {
                  try {
                    const job = await runLatentClassAnalysis(study_id, { n_classes: 3 })
                    addJob(job)
                    message.success(`潜在类别分析已启动: ${job.analysis_id}`)
                  } catch (err) {
                    message.error(err instanceof Error ? err.message : '启动潜在类别分析失败')
                  }
                }}
              >
                LCM
              </Button>
            )}
          </Space>
        )
      },
    },
  ]

  const expandedRowRender = (record: JobRow) => {
    if (!record.convergence) {
      return <Empty description="收敛数据不可用" image={Empty.PRESENTED_IMAGE_SIMPLE} />
    }
    const c = record.convergence
    return (
      <div style={{ padding: '0 24px' }}>
        <Row gutter={16}>
          <Col span={6}>
            <Statistic title="R-hat Max" value={c.rhat_max} precision={3}
              valueStyle={{ color: c.rhat_max > 1.1 ? '#cf1322' : '#3f8600' }} />
          </Col>
          <Col span={6}>
            <Statistic title="ESS Bulk Min" value={c.ess_bulk_min} precision={0} />
          </Col>
          <Col span={6}>
            <Statistic title="ESS Tail Min" value={c.ess_tail_min} precision={0} />
          </Col>
          <Col span={6}>
            <Statistic title="发散次数" value={c.divergences} precision={0} />
          </Col>
        </Row>
        {c.rhat_max > 1.1 && (
          <Alert message="警告: R-hat > 1.1，模型未收敛" type="warning" showIcon style={{ marginTop: 12 }} />
        )}
      </div>
    )
  }

  return (
    <div>
      <Title level={4} style={{ marginBottom: 16 }}>
        <ExperimentOutlined /> 分析任务状态
      </Title>

      <Card style={{ marginBottom: 16 }}>
        <Space wrap>
          <Select
            placeholder="选择研究项目运行分析"
            style={{ width: 280 }}
            value={selectedStudyId}
            onChange={setSelectedStudyId}
            allowClear
            options={studies.map((s: StudySummary) => ({
              label: `${s.study_id} (${s.product_category})`,
              value: s.study_id,
            }))}
          />
          <Select
            placeholder="选择模型类型"
            style={{ width: 160 }}
            value={selectedModelType}
            onChange={setSelectedModelType}
            options={[
              { label: 'HB (Hierarchical Bayes)', value: 'hb' },
              { label: 'MNL (Multinomial Logit)', value: 'mnl' },
              { label: 'Latent Class', value: 'latent_class' },
            ]}
          />
          <Button type="primary" icon={<PlayCircleOutlined />}
            onClick={handleStartAnalysis} loading={startingJob} disabled={!selectedStudyId}>
            启动分析
          </Button>
          <Button icon={<ReloadOutlined />} onClick={async () => { await getStudies().then((res) => setStudies(res.studies)); await loadJobs(); message.success('任务列表已刷新') }}>
            刷新
          </Button>
        </Space>
      </Card>

      {error && (
        <Alert message="错误" description={error} type="error" showIcon closable
          style={{ marginBottom: 16 }} onClose={() => setError(null)} />
      )}

      <Card title={`任务队列 (${jobs.length} 个任务)`}>
        {jobs.length === 0 ? (
          <Empty description="暂无分析任务，请选择一个研究项目启动分析" style={{ padding: 40 }} />
        ) : (
          <Table
            dataSource={jobs}
            columns={columns}
            rowKey={(r) => r.job.analysis_id}
            pagination={{ pageSize: 10, showTotal: (t) => `共 ${t} 个任务` }}
            size="small"
            expandable={{
              expandedRowRender,
              rowExpandable: (record) => record.job.status === 'COMPLETED',
            }}
          />
        )}
      </Card>

      <Modal
        title="可视化配置 (ECharts Option)"
        open={vizOpen}
        onCancel={() => setVizOpen(false)}
        footer={null}
        width={720}
      >
        <pre style={{ maxHeight: 480, overflow: 'auto' }}>{JSON.stringify(vizData, null, 2)}</pre>
      </Modal>
    </div>
  )
}

export default AnalysisStatus
