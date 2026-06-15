import React, { useEffect, useState } from 'react'
import { Card, Row, Col, Statistic, Table, Button, Tag, Spin, Alert, Space, Popconfirm, message } from 'antd'
import {
  ExperimentOutlined,
  UserOutlined,
  FileTextOutlined,
  BarChartOutlined,
  DeleteOutlined,
  PlayCircleOutlined,
  EyeOutlined,
  FormOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { getStudies, getDashboardSummary, deleteStudy, generateQuestionnaire } from '@/services/api'
import { useAppStore } from '@/stores/appStore'
import type { StudySummary, DashboardSummaryResponse } from '@/types/api'

const Dashboard: React.FC = () => {
  const navigate = useNavigate()
  const { studies, setStudies, runningJobs } = useAppStore()
  const [summary, setSummary] = useState<DashboardSummaryResponse['summary'] | null>(null)
  const [error, setError] = useState<string | null>(null)

  const [generatingStudyId, setGeneratingStudyId] = useState<string | null>(null)

  const fetchData = async () => {
    setError(null)
    try {
      const [summaryRes, studiesRes] = await Promise.all([
        getDashboardSummary(),
        getStudies(),
      ])
      setSummary(summaryRes.summary)
      setStudies(studiesRes.studies)
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载数据失败')
    }
  }

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 60000)
    const onFocus = () => fetchData()
    window.addEventListener('focus', onFocus)
    return () => {
      clearInterval(interval)
      window.removeEventListener('focus', onFocus)
    }
  }, [setStudies])

  const handleGenerateQuestionnaire = async (studyId: string) => {
    setGeneratingStudyId(studyId)
    try {
      const res = await generateQuestionnaire(studyId)
      message.success(`问卷生成成功: D-efficiency=${res.d_efficiency?.toFixed(3) ?? 'N/A'}`)
      await fetchData()
    } catch (err) {
      message.error(err instanceof Error ? err.message : '生成问卷失败')
    } finally {
      setGeneratingStudyId(null)
    }
  }

  const handleDeleteStudy = async (studyId: string) => {
    try {
      await deleteStudy(studyId)
      message.success(`已删除研究 ${studyId} 及其关联的问卷、作答数据`)
      await fetchData()
    } catch (err) {
      message.error(err instanceof Error ? err.message : '删除失败')
    }
  }

  const columns = [
    {
      title: '研究ID',
      dataIndex: 'study_id',
      key: 'study_id',
      render: (text: string) => <code>{text}</code>,
    },
    {
      title: '产品类别',
      dataIndex: 'product_category',
      key: 'product_category',
    },
    {
      title: '研究目标',
      dataIndex: 'research_goal',
      key: 'research_goal',
      ellipsis: true,
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      render: (text: string) => text ? new Date(text).toLocaleString('zh-CN') : '-',
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => {
        const colorMap: Record<string, string> = {
          INIT: 'default',
          DESIGNING: 'processing',
          READY: 'success',
          COMPLETED: 'success',
        }
        const labelMap: Record<string, string> = {
          INIT: '初始化',
          DESIGNING: '设计中',
          READY: '就绪',
          COMPLETED: '已完成',
        }
        return <Tag color={colorMap[status] || 'default'}>{labelMap[status] || status}</Tag>
      },
    },
    {
      title: '操作',
      key: 'action',
      render: (_: unknown, record: StudySummary) => (
        <Space>
          {record.status !== 'READY' && record.status !== 'COMPLETED' && (
            <Button
              type="link"
              size="small"
              icon={<FormOutlined />}
              loading={generatingStudyId === record.study_id}
              onClick={() => handleGenerateQuestionnaire(record.study_id)}
            >
              生成问卷
            </Button>
          )}
          {(record.status === 'READY' || record.status === 'COMPLETED') && (
            <Button
              type="link"
              size="small"
              icon={<EyeOutlined />}
              onClick={() => navigate(`/studies/${record.study_id}/questionnaire`)}
            >
              查看问卷
            </Button>
          )}
          <Button
            type="link"
            size="small"
            icon={<PlayCircleOutlined />}
            onClick={() => navigate(`/studies/${record.study_id}/responses`)}
          >
            模拟作答
          </Button>
          <Button
            type="link"
            size="small"
            onClick={() => navigate(`/importance?study=${record.study_id}`)}
          >
            查看分析
          </Button>
          <Popconfirm
            title="确认删除研究"
            description={`确定要删除研究「${record.study_id}」吗？将同时删除关联的问卷和作答数据，此操作不可撤销。`}
            onConfirm={() => handleDeleteStudy(record.study_id)}
            okText="确认删除"
            cancelText="取消"
            okButtonProps={{ danger: true }}
          >
            <Button type="link" size="small" danger icon={<DeleteOutlined />}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <Spin spinning={false}>
      {error && (
        <Alert
          message="数据加载失败"
          description={error}
          type="error"
          showIcon
          style={{ marginBottom: 16 }}
        />
      )}

      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title="研究项目"
              value={summary?.total_studies ?? 0}
              prefix={<ExperimentOutlined />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title="虚拟消费者"
              value={summary?.total_personas ?? 0}
              prefix={<UserOutlined />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title="问卷设计"
              value={summary?.studies_by_status?.READY ?? 0}
              prefix={<FileTextOutlined />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title="分析任务"
              value={runningJobs.length}
              prefix={<BarChartOutlined />}
              valueStyle={{ color: runningJobs.length > 0 ? '#1677ff' : undefined }}
            />
          </Card>
        </Col>
      </Row>

      <Card title="研究项目列表" extra={<Button type="primary" onClick={() => navigate('/importance')}>属性重要性看板</Button>}>
        <Table
          dataSource={[...studies].sort((a, b) => new Date(b.created_at || 0).getTime() - new Date(a.created_at || 0).getTime())}
          columns={columns}
          rowKey="study_id"
          pagination={{ pageSize: 10 }}
          size="small"
        />
      </Card>
    </Spin>
  )
}

export default Dashboard
