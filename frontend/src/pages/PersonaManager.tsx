import React, { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Card, Table, Button, Tag, Space, Modal, Form, Input, message, Spin, Pagination, Popconfirm, Alert, AutoComplete } from 'antd'
import { DeleteOutlined } from '@ant-design/icons'
import { getPersonas, generatePersonas, deletePersona, getStudies } from '@/services/api'
import type { PersonaSummary, StudySummary } from '@/types/api'

const PersonaManager: React.FC = () => {
  const navigate = useNavigate()
  const [personas, setPersonas] = useState<PersonaSummary[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [loading, setLoading] = useState(false)
  const [genModalOpen, setGenModalOpen] = useState(false)
  const [genLoading, setGenLoading] = useState(false)
  const [genForm] = Form.useForm()

  const [studies, setStudies] = useState<StudySummary[]>([])
  const [studiesLoading, setStudiesLoading] = useState(false)
  const [filterStudyId, setFilterStudyId] = useState<string | undefined>(undefined)

  const loadStudies = async () => {
    setStudiesLoading(true)
    try {
      const res = await getStudies(1, 100)
      setStudies(res.studies)
    } catch {
      message.error('加载研究列表失败')
    } finally {
      setStudiesLoading(false)
    }
  }

  useEffect(() => {
    loadStudies()
  }, [])

  useEffect(() => {
    fetchPersonas()
  }, [page, pageSize, filterStudyId])

  const fetchPersonas = async (p = page, ps = pageSize, studyId = filterStudyId) => {
    setLoading(true)
    try {
      const res = await getPersonas(p, ps, studyId)
      setPersonas(res.personas)
      setTotal(res.total)
    } catch (err) {
      message.error(err instanceof Error ? err.message : '加载画像失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (!genModalOpen) return
    loadStudies()
  }, [genModalOpen])

  const handleDelete = async (personaId: string) => {
    try {
      await deletePersona(personaId)
      message.success(`已删除画像 ${personaId}`)
      fetchPersonas(page, pageSize)
    } catch (err) {
      message.error(err instanceof Error ? err.message : '删除失败')
    }
  }

  const handleGenerate = async (values: { study_id: string; count: number }) => {
    setGenLoading(true)
    try {
      const res = await generatePersonas({
        study_id: values.study_id,
        count: values.count,
      })
      message.success(`成功生成 ${res.generated || values.count} 个虚拟消费者`)
      setGenModalOpen(false)
      genForm.resetFields()
      fetchPersonas(1)
    } catch (err) {
      message.error(err instanceof Error ? err.message : '生成失败')
    } finally {
      setGenLoading(false)
    }
  }

  const columns = [
    {
      title: '画像ID',
      dataIndex: 'persona_id',
      key: 'persona_id',
      render: (text: string) => <code>{text}</code>,
    },
    {
      title: '细分群体',
      dataIndex: 'segment',
      key: 'segment',
    },
    {
      title: '人生阶段',
      dataIndex: 'life_stage',
      key: 'life_stage',
    },
    {
      title: '城市层级',
      dataIndex: 'city_tier',
      key: 'city_tier',
    },
    {
      title: '收入档位',
      dataIndex: 'income_bracket',
      key: 'income_bracket',
    },
    {
      title: '真实性评分',
      dataIndex: 'authenticity_score',
      key: 'authenticity_score',
      render: (score: number | null) =>
        score === null ? <Tag>未评分</Tag> : <Tag color={score >= 9 ? 'green' : score >= 6 ? 'orange' : 'red'}>{score.toFixed(1)}</Tag>,
    },
    {
      title: '偏见审计',
      dataIndex: 'bias_audit_status',
      key: 'bias_audit_status',
      render: (status: string) => {
        const colorMap: Record<string, string> = {
          PASS: 'green',
          WARNING: 'orange',
          FAIL: 'red',
          PENDING: 'default',
        }
        return <Tag color={colorMap[status] || 'default'}>{status}</Tag>
      },
    },
    {
      title: '操作',
      key: 'action',
      render: (_: unknown, record: PersonaSummary) => (
        <Space>
          <Button type="link" size="small" onClick={() => navigate(`/personas/${record.persona_id}`)}>
            详情
          </Button>
          <Popconfirm
            title="确认删除"
            description={`确定要删除画像 ${record.persona_id} 吗？此操作不可撤销。`}
            onConfirm={() => handleDelete(record.persona_id)}
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
    <>
      <Card
        title="虚拟消费者画像管理"
        extra={
          <Space>
            <AutoComplete
              data-testid="study-filter-input"
              options={studies.map((s) => ({
                value: s.study_id,
                label: `${s.study_id} (${s.product_category || '未分类'})`,
              }))}
              placeholder="按研究ID筛选"
              allowClear
              showSearch
              value={filterStudyId}
              filterOption={(input, option) => {
                const value = String(option?.value || '').toLowerCase()
                const label = String(option?.label || '').toLowerCase()
                const query = input.toLowerCase()
                return value.includes(query) || label.includes(query)
              }}
              notFoundContent={studiesLoading ? <Spin size="small" /> : '无匹配研究'}
              onSelect={(value: string) => {
                setFilterStudyId(value)
                setPage(1)
              }}
              onClear={() => {
                setFilterStudyId(undefined)
                setPage(1)
              }}
              onChange={(value: string) => {
                setFilterStudyId(value || undefined)
                setPage(1)
              }}
              style={{ width: 260 }}
            />
            <Button type="primary" onClick={() => setGenModalOpen(true)}>
              批量生成
            </Button>
          </Space>
        }
      >
        <Spin spinning={loading}>
          <Table
            dataSource={personas}
            columns={columns}
            rowKey="persona_id"
            pagination={false}
            size="small"
          />
          <Pagination
            current={page}
            pageSize={pageSize}
            total={total}
            onChange={(p, ps) => {
              setPage(p)
              setPageSize(ps || 20)
            }}
            style={{ marginTop: 16, textAlign: 'right' }}
          />
        </Spin>
      </Card>

      <Modal
        title="批量生成虚拟消费者"
        open={genModalOpen}
        onCancel={() => setGenModalOpen(false)}
        footer={null}
      >
        <Form form={genForm} layout="vertical" onFinish={handleGenerate}>
          <Form.Item
            label="研究ID"
            name="study_id"
            rules={[{ required: true, message: '请输入或选择研究ID' }]}
          >
            <AutoComplete
              data-testid="study-id-input"
              options={studies.map((s) => ({
                value: s.study_id,
                label: `${s.study_id} (${s.product_category || '未分类'})`,
              }))}
              placeholder="输入或选择研究ID"
              allowClear
              showSearch
              filterOption={(input, option) => {
                const value = String(option?.value || '').toLowerCase()
                const label = String(option?.label || '').toLowerCase()
                const query = input.toLowerCase()
                return value.includes(query) || label.includes(query)
              }}
              notFoundContent={studiesLoading ? <Spin size="small" /> : '无匹配研究'}
            />
          </Form.Item>
          <Form.Item
            label="生成数量"
            name="count"
            rules={[{ required: true, message: '请输入数量' }]}
            initialValue={2}
            extra="单次建议 1-3 个，最多 5 个。大量生成请分多次操作，每个画像需要多次 LLM 调用，耗时约 30-90 秒。"
          >
            <Input type="number" min={1} max={5} />
          </Form.Item>
          <Form.Item>
            <Alert
              message="生成耗时提示"
              description="当前为同步生成：前端会保持连接等待后端完成。若网络不稳定或生成数量较多，仍可能超时，建议少量多次。"
              type="info"
              showIcon
              style={{ marginBottom: 16 }}
            />
            <Button type="primary" htmlType="submit" loading={genLoading} block>
              开始生成
            </Button>
          </Form.Item>
        </Form>
      </Modal>
    </>
  )
}

export default PersonaManager
