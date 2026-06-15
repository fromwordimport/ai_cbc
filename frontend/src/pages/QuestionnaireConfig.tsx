import React, { useEffect, useState, useCallback } from 'react'
import {
  Card, Table, Button, Tag, Spin, Alert, Descriptions,
  Typography, Empty, Collapse, Popconfirm, message, Space,
} from 'antd'
import {
  FileTextOutlined, ReloadOutlined, CheckCircleOutlined,
  CloseCircleOutlined, ClockCircleOutlined, DeleteOutlined,
  FormOutlined, AppstoreOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { getStudies, getQuestionnaire, deleteStudy, generateQuestionnaire } from '@/services/api'
import type { StudySummary, QuestionnaireDetail } from '@/types/api'

const { Title, Text } = Typography
const { Panel } = Collapse

interface StudyRow {
  study: StudySummary
  questionnaire: QuestionnaireDetail | null
  hasQuestionnaire: boolean
  loadingQuestionnaire: boolean
}

const QuestionnaireConfig: React.FC = () => {
  const navigate = useNavigate()
  const [data, setData] = useState<StudyRow[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [generatingStudyId, setGeneratingStudyId] = useState<string | null>(null)

  const loadStudies = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await getStudies(1, 100)
      const items: StudyRow[] = res.studies.map((study) => ({
        study,
        questionnaire: null,
        hasQuestionnaire: study.status === 'READY' || study.status === 'COMPLETED',
        loadingQuestionnaire: false,
      }))
      setData(items)

      items.forEach((item) => {
        if (item.hasQuestionnaire) {
          loadQuestionnaire(item.study.study_id)
        }
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [])

  const loadQuestionnaire = async (studyId: string) => {
    setData((prev) =>
      prev.map((item) =>
        item.study.study_id === studyId
          ? { ...item, loadingQuestionnaire: true }
          : item,
      ),
    )
    try {
      const q = await getQuestionnaire(studyId)
      setData((prev) =>
        prev.map((item) =>
          item.study.study_id === studyId
            ? { ...item, questionnaire: q, hasQuestionnaire: true, loadingQuestionnaire: false }
            : item,
        ),
      )
    } catch {
      setData((prev) =>
        prev.map((item) =>
          item.study.study_id === studyId
            ? { ...item, hasQuestionnaire: false, loadingQuestionnaire: false }
            : item,
        ),
      )
    }
  }

  useEffect(() => {
    loadStudies()
  }, [loadStudies])

  const handleGenerateQuestionnaire = async (studyId: string) => {
    setGeneratingStudyId(studyId)
    try {
      const res = await generateQuestionnaire(studyId)
      message.success(`问卷生成成功: D-efficiency=${res.d_efficiency?.toFixed(3) ?? 'N/A'}`)
      // Refresh questionnaire data for this study
      loadQuestionnaire(studyId)
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
      loadStudies()
    } catch (err) {
      message.error(err instanceof Error ? err.message : '删除失败')
    }
  }

  const statusTag = (status: string) => {
    const map: Record<string, { color: string; icon: React.ReactNode }> = {
      DRAFT: { color: 'default', icon: <ClockCircleOutlined /> },
      READY: { color: 'processing', icon: <CheckCircleOutlined /> },
      RUNNING: { color: 'warning', icon: <ClockCircleOutlined /> },
      COMPLETED: { color: 'success', icon: <CheckCircleOutlined /> },
      FAILED: { color: 'error', icon: <CloseCircleOutlined /> },
    }
    const cfg = map[status] || map.DRAFT
    return <Tag color={cfg.color} icon={cfg.icon}>{status}</Tag>
  }

  const columns = [
    {
      title: '研究ID',
      dataIndex: ['study', 'study_id'],
      key: 'study_id',
      width: 180,
      render: (text: string) => <code>{text}</code>,
    },
    {
      title: '产品类别',
      dataIndex: ['study', 'product_category'],
      key: 'product_category',
      width: 100,
    },
    {
      title: '研究目标',
      dataIndex: ['study', 'research_goal'],
      key: 'research_goal',
      ellipsis: true,
    },
    {
      title: '状态',
      dataIndex: ['study', 'status'],
      key: 'status',
      width: 100,
      render: (s: string) => statusTag(s),
    },
    {
      title: '问卷',
      key: 'questionnaire_status',
      width: 100,
      render: (_: unknown, record: StudyRow) => {
        if (record.loadingQuestionnaire) return <Spin size="small" />
        if (record.questionnaire) {
          return <Tag color="success" icon={<CheckCircleOutlined />}>已生成</Tag>
        }
        return <Tag icon={<ClockCircleOutlined />}>未生成</Tag>
      },
    },
    {
      title: '选择集数',
      key: 'n_choice_sets',
      width: 80,
      render: (_: unknown, record: StudyRow) =>
        record.questionnaire?.design_params?.n_choice_sets ?? '-',
    },
    {
      title: 'D-efficiency',
      key: 'd_efficiency',
      width: 110,
      render: (_: unknown, record: StudyRow) => {
        const val = record.questionnaire?.design_params?.d_efficiency
        if (val === null || val === undefined) return '-'
        return (
          <Tag color={val >= 0.85 ? 'green' : val >= 0.7 ? 'orange' : 'red'}>
            {val.toFixed(3)}
          </Tag>
        )
      },
    },
    {
      title: '操作',
      key: 'action',
      width: 120,
      render: (_: unknown, record: StudyRow) => (
        <Space>
          <Button
            type="link"
            size="small"
            icon={<AppstoreOutlined />}
            onClick={() => navigate(`/studies/${record.study.study_id}/design`)}
          >
            配置属性
          </Button>
          {!record.hasQuestionnaire && (
            <Button
              type="link"
              size="small"
              icon={<FormOutlined />}
              loading={generatingStudyId === record.study.study_id}
              onClick={() => handleGenerateQuestionnaire(record.study.study_id)}
            >
              生成问卷
            </Button>
          )}
          <Popconfirm
            title="确认删除研究"
            description={`确定要删除研究「${record.study.study_id}」吗？将同时删除关联的问卷和作答数据，此操作不可撤销。`}
            onConfirm={() => handleDeleteStudy(record.study.study_id)}
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

  const expandedRowRender = (record: StudyRow) => {
    if (!record.questionnaire) {
      return <Empty description="尚未生成问卷" image={Empty.PRESENTED_IMAGE_SIMPLE} />
    }
    const q = record.questionnaire
    return (
      <div style={{ padding: '0 24px' }}>
        <Descriptions size="small" bordered column={4} style={{ marginBottom: 16 }}>
          <Descriptions.Item label="算法">{q.design_params.algorithm}</Descriptions.Item>
          <Descriptions.Item label="属性数">{q.design_params.n_attributes}</Descriptions.Item>
          <Descriptions.Item label="选择集数">{q.design_params.n_choice_sets}</Descriptions.Item>
          <Descriptions.Item label="选项数/集">{q.design_params.n_alternatives}</Descriptions.Item>
          <Descriptions.Item label="含None选项">{q.design_params.include_none ? '是' : '否'}</Descriptions.Item>
          <Descriptions.Item label="D-efficiency">{q.design_params.d_efficiency?.toFixed(4) ?? 'N/A'}</Descriptions.Item>
        </Descriptions>

        <Text strong style={{ display: 'block', marginBottom: 8 }}>选择集设计矩阵</Text>
        <Collapse size="small" ghost>
          {q.choice_sets.map((cs) => (
            <Panel key={cs.choice_set_id} header={`选择集 #${cs.choice_set_id}`}>
              <Table
                dataSource={cs.alternatives}
                columns={[
                  {
                    title: '选项',
                    dataIndex: 'alt_index',
                    width: 80,
                    render: (v: number) => (
                      <Tag>{v === 99 ? 'None' : `选项 ${String.fromCharCode(65 + v)}`}</Tag>
                    ),
                  },
                  ...Object.keys(cs.alternatives[0]?.attributes || {}).map(
                    (attr) => ({
                      title: attr,
                      dataIndex: ['attributes', attr] as [string, string],
                      key: attr,
                    }),
                  ),
                ]}
                pagination={false}
                size="small"
                rowKey="alt_id"
              />
            </Panel>
          ))}
        </Collapse>
      </div>
    )
  }

  return (
    <div>
      <Title level={4} style={{ marginBottom: 16 }}>
        <FileTextOutlined /> 问卷配置管理
      </Title>

      {error && (
        <Alert message="加载失败" description={error} type="error" showIcon closable
          style={{ marginBottom: 16 }} onClose={() => setError(null)} />
      )}

      <Spin spinning={loading}>
        <Card
          title={`CBC实验设计总览 (${data.length} 个研究)`}
          extra={<Button icon={<ReloadOutlined />} onClick={loadStudies}>刷新</Button>}
        >
          <Table
            dataSource={data}
            columns={columns}
            rowKey={(r) => r.study.study_id}
            pagination={{ pageSize: 10, showTotal: (t) => `共 ${t} 项` }}
            size="small"
            expandable={{
              expandedRowRender,
              rowExpandable: (record) => record.hasQuestionnaire,
            }}
          />
        </Card>
      </Spin>
    </div>
  )
}

export default QuestionnaireConfig
