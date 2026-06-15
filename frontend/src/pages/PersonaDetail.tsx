import React, { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Card, Descriptions, Tag, Button, Spin, Collapse, Typography, Space, message, Popconfirm } from 'antd'
import { ArrowLeftOutlined, DeleteOutlined } from '@ant-design/icons'
import { getPersona, deletePersona } from '@/services/api'
import type { PersonaDetail as PersonaDetailType } from '@/types/api'

const { Text, Paragraph } = Typography

const PersonaDetail: React.FC = () => {
  const { personaId } = useParams<{ personaId: string }>()
  const navigate = useNavigate()
  const [persona, setPersona] = useState<PersonaDetailType | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!personaId) return
    setLoading(true)
    getPersona(personaId)
      .then((data) => setPersona(data))
      .catch((err) => {
        message.error(err instanceof Error ? err.message : '加载画像详情失败')
      })
      .finally(() => setLoading(false))
  }, [personaId])

  if (loading) {
    return <Spin size="large" style={{ display: 'flex', justifyContent: 'center', marginTop: 80 }} />
  }

  const handleDelete = async () => {
    if (!personaId) return
    try {
      await deletePersona(personaId)
      message.success(`已删除画像 ${personaId}`)
      navigate('/personas')
    } catch (err) {
      message.error(err instanceof Error ? err.message : '删除失败')
    }
  }

  if (!persona) {
    return (
      <Card>
        <Text type="secondary">画像不存在</Text>
        <br />
        <Button type="link" onClick={() => navigate('/personas')}>返回列表</Button>
      </Card>
    )
  }

  const scoreColor = (score: number | null) =>
    score === null ? 'default' : score >= 12 ? 'green' : score >= 9 ? 'blue' : score >= 7 ? 'orange' : 'red'

  const biasColorMap: Record<string, string> = {
    PASSED: 'green',
    FAILED: 'red',
    PENDING: 'default',
  }

  const l1 = (persona.layer1_demographics || {}) as Record<string, unknown>
  const l2 = (persona.layer2_behavior || {}) as Record<string, unknown>
  const l3 = (persona.layer3_psychology || {}) as Record<string, unknown>
  const l4 = (persona.layer4_scenarios || {}) as Record<string, unknown>
  const dc = (persona.dishwasher_context || {}) as Record<string, unknown>
  const meta = (persona.generation_metadata || {}) as Record<string, unknown>

  return (
    <>
      <Space style={{ marginBottom: 16, width: '100%', justifyContent: 'space-between' }}>
        <Button
          type="link"
          icon={<ArrowLeftOutlined />}
          onClick={() => navigate('/personas')}
          style={{ padding: 0 }}
        >
          返回画像列表
        </Button>
        <Popconfirm
          title="确认删除"
          description={`确定要删除画像 ${persona.persona_id} 吗？此操作不可撤销。`}
          onConfirm={handleDelete}
          okText="确认删除"
          cancelText="取消"
          okButtonProps={{ danger: true }}
        >
          <Button danger icon={<DeleteOutlined />}>删除画像</Button>
        </Popconfirm>
      </Space>

      <Card title={`画像详情 — ${persona.persona_id}`}>
        <Descriptions column={2} bordered size="small" style={{ marginBottom: 24 }}>
          <Descriptions.Item label="画像ID">
            <code>{persona.persona_id}</code>
          </Descriptions.Item>
          <Descriptions.Item label="细分群体">{persona.segment}</Descriptions.Item>
          <Descriptions.Item label="真实性评分">
            <Tag color={scoreColor(persona.authenticity_score)}>
              {persona.authenticity_score?.toFixed(1) ?? '未评分'}
            </Tag>
          </Descriptions.Item>
          <Descriptions.Item label="偏见审计">
            <Tag color={biasColorMap[persona.bias_audit_status] || 'default'}>
              {persona.bias_audit_status}
            </Tag>
          </Descriptions.Item>
          <Descriptions.Item label="创建时间">{persona.created_at}</Descriptions.Item>
          <Descriptions.Item label="生成模型">
            {String(meta.model ?? '-')} / 成本 ¥{Number(meta.cost_cny ?? 0).toFixed(2)}
          </Descriptions.Item>
        </Descriptions>

        <Collapse
          defaultActiveKey={['layer1']}
          items={[
            {
              key: 'layer1',
              label: 'Layer 1 — 基础骨架（人口统计）',
              children: (
                <Descriptions column={2} size="small" bordered>
                  <Descriptions.Item label="年龄">{String(l1.age ?? '-')}</Descriptions.Item>
                  <Descriptions.Item label="性别">{String(l1.gender ?? '-')}</Descriptions.Item>
                  <Descriptions.Item label="城市">{String(l1.city ?? '-')}</Descriptions.Item>
                  <Descriptions.Item label="收入">{String(l1.income ?? '-')}</Descriptions.Item>
                  <Descriptions.Item label="职业">{String(l1.occupation ?? '-')}</Descriptions.Item>
                  <Descriptions.Item label="学历">{String(l1.education ?? '-')}</Descriptions.Item>
                  <Descriptions.Item label="婚姻">{String(l1.marital_status ?? '-')}</Descriptions.Item>
                  <Descriptions.Item label="居住">{String(l1.living_type ?? '-')}</Descriptions.Item>
                </Descriptions>
              ),
            },
            {
              key: 'layer2',
              label: 'Layer 2 — 行为签名（消费模式）',
              children: (
                <Descriptions column={1} size="small" bordered>
                  <Descriptions.Item label="价格敏感度">{String(l2.price_sensitivity ?? '-')}</Descriptions.Item>
                  <Descriptions.Item label="购买渠道">
                    {Array.isArray(l2.purchase_channels)
                      ? l2.purchase_channels.join('、')
                      : String(l2.purchase_channels ?? '-')}
                  </Descriptions.Item>
                  <Descriptions.Item label="决策风格">{String(l2.decision_style ?? '-')}</Descriptions.Item>
                  <Descriptions.Item label="品牌忠诚度">{String(l2.brand_loyalty ?? '-')}</Descriptions.Item>
                  <Descriptions.Item label="信息来源">
                    {Array.isArray(l2.information_source)
                      ? l2.information_source.join('、')
                      : String(l2.information_source ?? '-')}
                  </Descriptions.Item>
                </Descriptions>
              ),
            },
            {
              key: 'layer3',
              label: 'Layer 3 — 心理引擎（深层驱动）',
              children: (
                <Descriptions column={1} size="small" bordered>
                  <Descriptions.Item label="核心价值观">
                    {Array.isArray(l3.core_values) ? l3.core_values.join('、') : String(l3.core_values ?? '-')}
                  </Descriptions.Item>
                  <Descriptions.Item label="核心焦虑">
                    {Array.isArray(l3.core_anxieties) ? l3.core_anxieties.join('、') : String(l3.core_anxieties ?? '-')}
                  </Descriptions.Item>
                  <Descriptions.Item label="矛盾张力">
                    {(() => {
                      const tc = l3.tension_combination as Record<string, unknown> | undefined
                      if (!tc) return '-'
                      const labels = Array.isArray(tc.labels) ? tc.labels.join(' vs ') : String(tc.labels ?? '')
                      return (
                        <Space direction="vertical">
                          <Text strong>{labels}</Text>
                          <Paragraph type="secondary" style={{ marginBottom: 0 }}>
                            {String(tc.narrative_explanation ?? '')}
                          </Paragraph>
                        </Space>
                      )
                    })()}
                  </Descriptions.Item>
                  <Descriptions.Item label="秘密动机">{String(l3.secret_motivation ?? '-')}</Descriptions.Item>
                  <Descriptions.Item label="防御机制">{String(l3.defense_mechanism ?? '-')}</Descriptions.Item>
                </Descriptions>
              ),
            },
            {
              key: 'layer4',
              label: 'Layer 4 — 场景反应库（情境驱动）',
              children: (
                <Descriptions column={1} size="small" bordered>
                  <Descriptions.Item label="日常轨迹">{String(l4.daily_routine ?? '-')}</Descriptions.Item>
                  <Descriptions.Item label="购买触发">{String(l4.purchase_trigger ?? '-')}</Descriptions.Item>
                  <Descriptions.Item label="压力反应">{String(l4.stress_response ?? '-')}</Descriptions.Item>
                  <Descriptions.Item label="社交行为">{String(l4.social_behavior ?? '-')}</Descriptions.Item>
                </Descriptions>
              ),
            },
            {
              key: 'language',
              label: '语言样本',
              children: (
                <ul style={{ margin: 0, paddingLeft: 20 }}>
                  {Array.isArray(persona.language_samples) && persona.language_samples.length > 0 ? (
                    persona.language_samples.map((s, i) => <li key={i}>{s}</li>)
                  ) : (
                    <Text type="secondary">无</Text>
                  )}
                </ul>
              ),
            },
            {
              key: 'dishwasher',
              label: '洗碗机购买情境',
              children: (
                <Descriptions column={1} size="small" bordered>
                  <Descriptions.Item label="购买约束">
                    {Array.isArray(dc.purchase_constraints)
                      ? dc.purchase_constraints.join('、')
                      : String(dc.purchase_constraints ?? '-')}
                  </Descriptions.Item>
                  <Descriptions.Item label="决策因素">
                    {Array.isArray(dc.decision_factors)
                      ? dc.decision_factors.join('、')
                      : String(dc.decision_factors ?? '-')}
                  </Descriptions.Item>
                  <Descriptions.Item label="忽略因素">
                    {Array.isArray(dc.ignored_factors)
                      ? dc.ignored_factors.join('、')
                      : String(dc.ignored_factors ?? '-')}
                  </Descriptions.Item>
                </Descriptions>
              ),
            },
          ]}
        />
      </Card>
    </>
  )
}

export default PersonaDetail
