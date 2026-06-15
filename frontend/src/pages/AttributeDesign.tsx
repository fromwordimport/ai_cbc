import React, { useEffect, useState, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  Card, Button, Input, Tag, message, Spin, Alert, Space, Typography, Empty,
  Select, Row, Col, Table, Collapse,
} from 'antd'
import {
  PlusOutlined, DeleteOutlined, SaveOutlined, ArrowLeftOutlined,
  AppstoreOutlined, SyncOutlined,
} from '@ant-design/icons'
import { getStudyDesign, updateStudyDesign } from '@/services/api'
import type { AttributeDefinition, Level, ProhibitedPair, ProhibitedCondition } from '@/types/api'

const { Title, Text } = Typography

// Helper: try to make a slug from name (ASCII only; falls back to null for pure CJK)
export const slugify = (name: string): string | null => {
  const ascii = name
    .trim()
    .toLowerCase()
    .replace(/\s+/g, '_')
    .replace(/[^a-z0-9_-]/g, '')
  return ascii.length > 0 ? ascii : null
}

// ───────────────────────────────────────────────────────────
// 统一生成水平 value（所有 value 唯一入口）
// ───────────────────────────────────────────────────────────
export const generateLevelValue = (
  index: number,
  attrId: string,
  attrType: string,
): string => {
  if (!attrId) return `level_${index + 1}`
  if (attrType === 'categorical' || attrType === 'ordinal') {
    return `${attrId}_${index + 1}`
  }
  return `level_${index + 1}`
}

// 统一创建水平（所有 Level 唯一入口）
export const createLevel = (
  index: number,
  attrId: string,
  attrType: string,
  label: string = '',
): Level => ({
  value: generateLevelValue(index, attrId, attrType),
  label,
  description: null,
})

// 统一创建完整属性（用于默认值）
export const createAttribute = (
  id: string,
  name: string,
  type: AttributeDefinition['type'],
  levelLabels: string[],
): AttributeDefinition => ({
  id,
  name,
  type,
  description: null,
  levels: levelLabels.map((label, idx) => createLevel(idx, id, type, label)),
})

// 创建空属性（用于新增属性）
export const createEmptyAttribute = (index: number): AttributeDefinition => {
  const id = `attr_${index + 1}`
  const type = 'categorical'
  return {
    id,
    name: '',
    type,
    description: null,
    levels: [createLevel(0, id, type), createLevel(1, id, type)],
  }
}

// 默认属性（统一调用 createAttribute）
const DEFAULT_ATTRIBUTES: AttributeDefinition[] = [
  createAttribute('price', '价格', 'price', ['1999元', '3999元', '5999元', '8999元']),
  createAttribute('brand', '品牌', 'categorical', ['华菱', '美的', '方太', '西门子']),
  createAttribute('capacity', '容量', 'categorical', ['8套', '14套', '18套', '24套']),
  createAttribute('energy', '能效等级', 'categorical', ['一级', '二级', '三级']),
  createAttribute('spray_arm', '喷淋臂类型', 'categorical', ['上下双层', '三层', '多向旋喷']),
  createAttribute('installation', '安装方式', 'categorical', ['嵌入式', '独立式', '台式', '水槽式']),
  createAttribute('drying', '烘干方式', 'categorical', ['余热', '热交换', '热风', '晶蕾']),
]

export const validateAttributes = (
  attributes: AttributeDefinition[],
  prohibitedPairs: ProhibitedPair[],
): string | null => {
  if (attributes.length < 2) return '至少需要配置两个属性'
  const idSet = new Set<string>()
  for (let idx = 0; idx < attributes.length; idx++) {
    const attr = attributes[idx]
    if (!attr.id.trim()) return `属性 ${idx + 1} 的ID不能为空`
    if (!/^[a-zA-Z0-9_-]+$/.test(attr.id)) {
      return `属性「${attr.name || attr.id}」的ID只能包含字母、数字、下划线或连字符`
    }
    if (idSet.has(attr.id)) {
      return `属性ID「${attr.id}」重复，请确保每个属性的ID唯一`
    }
    idSet.add(attr.id)
    if (!attr.name.trim()) return `属性ID「${attr.id}」的名称不能为空`
    if (attr.levels.length < 2) {
      return `属性「${attr.name}」至少需要两个水平`
    }
    const levelValues = new Set<string>()
    for (let lIdx = 0; lIdx < attr.levels.length; lIdx++) {
      const lv = attr.levels[lIdx]
      if (!lv.value.trim()) {
        return `属性「${attr.name}」的水平 ${lIdx + 1} 的标识（value）不能为空`
      }
      if (levelValues.has(lv.value)) {
        return `属性「${attr.name}」的水平值「${lv.value}」重复`
      }
      levelValues.add(lv.value)
    }
  }
  if (prohibitedPairs.length > 0) {
    for (let pIdx = 0; pIdx < prohibitedPairs.length; pIdx++) {
      const pair = prohibitedPairs[pIdx]
      if (pair.conditions.length < 2) {
        return `禁止组合 ${pIdx + 1} 至少需要两个条件`
      }
      for (const cond of pair.conditions) {
        const attr = attributes.find((a) => a.id === cond.attribute_id)
        if (!attr) {
          return `禁止组合 ${pIdx + 1} 引用了不存在的属性「${cond.attribute_id}」`
        }
        if (!attr.levels.some((lv) => lv.value === cond.level_value)) {
          return `禁止组合 ${pIdx + 1} 引用了属性「${attr.name}」中不存在的水平「${cond.level_value}」`
        }
      }
    }
  }
  return null
}


export const formatProhibitedPairDisplay = (
  pair: ProhibitedPair,
  attributes: AttributeDefinition[],
): string => {
  return pair.conditions
    .map((cond) => {
      const attr = attributes.find((a) => a.id === cond.attribute_id)
      const level = attr?.levels.find((l) => l.value === cond.level_value)
      return `${attr?.name || cond.attribute_id} = ${level?.label || cond.level_value}`
    })
    .join(' 且 ')
}

const AttributeDesign: React.FC = () => {
  const { studyId } = useParams<{ studyId: string }>()
  const navigate = useNavigate()
  const [attributes, setAttributes] = useState<AttributeDefinition[]>([])
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [prohibitedPairs, setProhibitedPairs] = useState<ProhibitedPair[]>([])
  const [cond1, setCond1] = useState<ProhibitedCondition>({ attribute_id: '', level_value: '' })
  const [cond2, setCond2] = useState<ProhibitedCondition>({ attribute_id: '', level_value: '' })

  useEffect(() => {
    if (!studyId) return
    const fetch = async () => {
      setLoading(true)
      setError(null)
      try {
        const res = await getStudyDesign(studyId)
        if (res.attributes && res.attributes.length > 0) {
          setAttributes(res.attributes)
        } else {
          setAttributes([...DEFAULT_ATTRIBUTES])
        }
        setProhibitedPairs(res.prohibited_pairs || [])
      } catch (err) {
        setAttributes([...DEFAULT_ATTRIBUTES])
        setProhibitedPairs([])
        setError('后端接口暂未就绪，使用默认属性配置。保存后将尝试提交。')
      } finally {
        setLoading(false)
      }
    }
    fetch()
  }, [studyId])

  const handleUpdateAttributeName = (index: number, name: string) => {
    setAttributes((prev) =>
      prev.map((attr, i) => {
        if (i !== index) return attr
        // Auto-generate id only when id is currently empty
        const newId = attr.id === '' ? (slugify(name) || '') : attr.id
        // If id changed and type is categorical/ordinal, auto-rename levels
        if (newId && newId !== attr.id && (attr.type === 'categorical' || attr.type === 'ordinal')) {
          const newLevels = attr.levels.map((lv, idx) => {
            const isAutoGenerated =
              lv.value === `level_${idx + 1}` ||
              lv.value === `${attr.id}_${idx + 1}` ||
              lv.value === ''
            if (isAutoGenerated) {
              return { ...lv, value: `${newId}_${idx + 1}` }
            }
            return lv
          })
          return { ...attr, name, id: newId, levels: newLevels }
        }
        return { ...attr, name, id: newId }
      }),
    )
  }

  const handleUpdateAttributeId = (index: number, id: string) => {
    setAttributes((prev) =>
      prev.map((attr, i) => {
        if (i !== index) return attr
        // If id changed and type is categorical/ordinal, auto-rename levels
        if (id && id !== attr.id && (attr.type === 'categorical' || attr.type === 'ordinal')) {
          const newLevels = attr.levels.map((lv, idx) => {
            const isAutoGenerated =
              lv.value === `level_${idx + 1}` ||
              lv.value === `${attr.id}_${idx + 1}` ||
              lv.value === ''
            if (isAutoGenerated) {
              return { ...lv, value: `${id}_${idx + 1}` }
            }
            return lv
          })
          return { ...attr, id, levels: newLevels }
        }
        return { ...attr, id }
      }),
    )
  }

  const handleUpdateAttributeType = (index: number, type: string) => {
    setAttributes((prev) =>
      prev.map((attr, i) => {
        if (i !== index) return attr
        const newType = type as AttributeDefinition['type']
        // If switching to categorical/ordinal from other types and id exists, auto-rename levels
        if ((newType === 'categorical' || newType === 'ordinal') &&
            attr.id &&
            attr.type !== 'categorical' && attr.type !== 'ordinal') {
          const newLevels = attr.levels.map((lv, idx) => {
            const isAutoGenerated =
              lv.value === `level_${idx + 1}` ||
              lv.value === ''
            if (isAutoGenerated) {
              return { ...lv, value: `${attr.id}_${idx + 1}` }
            }
            return lv
          })
          return { ...attr, type: newType, levels: newLevels }
        }
        return { ...attr, type: newType }
      }),
    )
  }

  const handleUpdateAttributeDescription = (index: number, description: string) => {
    setAttributes((prev) =>
      prev.map((attr, i) =>
        i === index ? { ...attr, description: description || null } : attr,
      ),
    )
  }

  const handleAutoGenerateId = (index: number) => {
    setAttributes((prev) =>
      prev.map((attr, i) => {
        if (i !== index) return attr
        let newId = slugify(attr.name)
        if (!newId) {
          newId = `attribute_${index + 1}`
        }
        // Ensure uniqueness
        let suffix = ''
        let counter = 1
        while (prev.some((a, j) => j !== i && a.id === `${newId}${suffix}`)) {
          suffix = `_${counter}`
          counter++
        }
        const finalId = `${newId}${suffix}`
        // If type is categorical/ordinal, auto-rename levels
        if (attr.type === 'categorical' || attr.type === 'ordinal') {
          const newLevels = attr.levels.map((lv, idx) => {
            const isAutoGenerated =
              lv.value === `level_${idx + 1}` ||
              lv.value === `${attr.id}_${idx + 1}` ||
              lv.value === ''
            if (isAutoGenerated) {
              return { ...lv, value: `${finalId}_${idx + 1}` }
            }
            return lv
          })
          return { ...attr, id: finalId, levels: newLevels }
        }
        return { ...attr, id: finalId }
      }),
    )
  }

  const handleAddAttribute = () => {
    setAttributes((prev) => [...prev, createEmptyAttribute(prev.length)])
  }

  const handleRemoveAttribute = (index: number) => {
    setAttributes((prev) => prev.filter((_, i) => i !== index))
  }

  const handleAddLevel = (attrIndex: number) => {
    setAttributes((prev) =>
      prev.map((attr, i) => {
        if (i !== attrIndex) return attr
        const newLevel = createLevel(
          attr.levels.length,
          attr.id,
          attr.type,
        )
        return { ...attr, levels: [...attr.levels, newLevel] }
      }),
    )
  }

  const handleRemoveLevel = (attrIndex: number, levelIndex: number) => {
    setAttributes((prev) =>
      prev.map((attr, i) =>
        i === attrIndex
          ? { ...attr, levels: attr.levels.filter((_, j) => j !== levelIndex) }
          : attr,
      ),
    )
  }

  const handleUpdateLevel = (
    attrIndex: number,
    levelIndex: number,
    field: keyof Level,
    value: string,
  ) => {
    setAttributes((prev) =>
      prev.map((attr, i) =>
        i === attrIndex
          ? {
              ...attr,
              levels: attr.levels.map((lv, j) =>
                j === levelIndex
                  ? { ...lv, [field]: field === 'description' ? (value || null) : value }
                  : lv,
              ),
            }
          : attr,
      ),
    )
  }

  const handleSave = async () => {
    const validationError = validateAttributes(attributes, prohibitedPairs)
    if (validationError) {
      message.warning(validationError)
      return
    }
    if (!studyId) return

    setSaving(true)
    try {
      await updateStudyDesign(studyId, attributes, prohibitedPairs)
      message.success('属性配置已保存')
      setError(null)
    } catch (err) {
      const msg = err instanceof Error ? err.message : '保存失败'
      message.error(msg)
      setError(msg)
    } finally {
      setSaving(false)
    }
  }

  const handleAddProhibitedPair = useCallback(() => {
    if (!cond1.attribute_id || !cond1.level_value || !cond2.attribute_id || !cond2.level_value) return
    if (cond1.attribute_id === cond2.attribute_id) {
      message.warning('禁止组合的两个条件必须来自不同属性')
      return
    }
    const newPair: ProhibitedPair = {
      conditions: [cond1, cond2].sort((a, b) => a.attribute_id.localeCompare(b.attribute_id)),
    }
    const exists = prohibitedPairs.some((pair) => {
      if (pair.conditions.length !== newPair.conditions.length) return false
      return pair.conditions.every((c, i) => 
        c.attribute_id === newPair.conditions[i].attribute_id && 
        c.level_value === newPair.conditions[i].level_value
      )
    })
    if (exists) {
      message.warning('该禁止组合已存在')
      return
    }
    setProhibitedPairs((prev) => [...prev, newPair])
    setCond1({ attribute_id: '', level_value: '' })
    setCond2({ attribute_id: '', level_value: '' })
    message.success('已添加禁止组合')
  }, [cond1, cond2, prohibitedPairs])

  const handleRemoveProhibitedPair = useCallback((index: number) => {
    setProhibitedPairs((prev) => prev.filter((_, i) => i !== index))
  }, [])

  const overviewColumns = [
    { title: '属性ID', dataIndex: 'id', key: 'id', render: (v: string) => <Tag color="blue">{v}</Tag> },
    { title: '属性名称', dataIndex: 'name', key: 'name' },
    { title: '类型', dataIndex: 'type', key: 'type', render: (v: string) => {
      const typeMap: Record<string, string> = {
        categorical: '分类变量',
        ordinal: '有序变量',
        continuous: '连续变量',
        price: '价格',
      }
      return <Tag>{typeMap[v] ?? v}</Tag>
    } },
    { title: '水平数', key: 'levelCount', render: (_: unknown, record: AttributeDefinition) => record.levels.length },
    {
      title: '水平',
      key: 'levels',
      render: (_: unknown, record: AttributeDefinition) => (
        <Space size="small" wrap>
          {record.levels.map((lv, idx) => (
            <Tag key={lv.value || lv.label || `lv-${idx}`} color="cyan">{lv.label || lv.value}</Tag>
          ))}
        </Space>
      ),
    },
  ]

  return (
    <Spin spinning={loading}>
      <Card
        title={
          <Space>
            <AppstoreOutlined />
            <Title level={4} style={{ margin: 0 }}>属性与水平配置</Title>
          </Space>
        }
        extra={
          <Space>
            <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/questionnaires')}>
              返回问卷配置
            </Button>
            <Button type="primary" icon={<SaveOutlined />} onClick={handleSave} loading={saving}>
              保存配置
            </Button>
          </Space>
        }
      >
        {error && (
          <Alert message="注意" description={error} type="warning" showIcon style={{ marginBottom: 16 }} />
        )}

        <Text type="secondary" style={{ display: 'block', marginBottom: 16 }}>
          研究ID: <code>{studyId}</code> · 共 {attributes.length} 个属性
        </Text>

        {attributes.length === 0 && (
          <Empty description="暂无属性配置，请添加属性" style={{ marginBottom: 16 }} />
        )}

        {attributes.map((attr, attrIdx) => (
          <Card
            key={attrIdx}
            size="small"
            style={{ marginBottom: 12 }}
            title={
              <Space wrap>
                <Tag color="blue">属性 {attrIdx + 1}</Tag>
                <Input
                  placeholder="属性ID（如 brand）"
                  value={attr.id}
                  onChange={(e) => handleUpdateAttributeId(attrIdx, e.target.value)}
                  style={{ width: 160 }}
                  status={!attr.id.trim() ? 'warning' : undefined}
                />
                <Input
                  placeholder="属性名称（如：品牌）"
                  value={attr.name}
                  onChange={(e) => handleUpdateAttributeName(attrIdx, e.target.value)}
                  style={{ width: 160 }}
                />
                <Select
                  value={attr.type}
                  style={{ width: 140 }}
                  onChange={(val) => handleUpdateAttributeType(attrIdx, val)}
                  options={[
                    { value: 'categorical', label: '分类变量' },
                    { value: 'ordinal', label: '有序变量' },
                    { value: 'continuous', label: '连续变量' },
                    { value: 'price', label: '价格' },
                  ]}
                  title="分类变量：无序类别（如品牌、颜色）\n有序变量：有内在顺序（如大小、等级）\n连续变量：可取任意数值（如重量、尺寸）\n价格：特殊连续变量，用于WTP计算"
                />
                <Button
                  size="small"
                  icon={<SyncOutlined />}
                  onClick={() => handleAutoGenerateId(attrIdx)}
                  title="根据名称自动生成ID"
                >
                  自动生成ID
                </Button>
              </Space>
            }
            extra={
              <Button
                type="link"
                danger
                size="small"
                icon={<DeleteOutlined />}
                onClick={() => handleRemoveAttribute(attrIdx)}
              >
                删除属性
              </Button>
            }
          >
            <Collapse
              ghost
              size="small"
              style={{ marginBottom: 8 }}
              items={[
                {
                  key: 'desc',
                  label: '描述（可选）',
                  children: (
                    <Input.TextArea
                      placeholder="属性描述"
                      value={attr.description || ''}
                      onChange={(e) => handleUpdateAttributeDescription(attrIdx, e.target.value)}
                      rows={2}
                    />
                  ),
                },
              ]}
            />

            <Row gutter={[16, 8]}>
              {attr.levels.map((lv, lvIdx) => (
                <Col key={lvIdx} xs={24} sm={12} md={8} lg={8}>
                  <Card size="small" style={{ background: '#fafafa' }}>
                    <Space direction="vertical" style={{ width: '100%' }}>
                      <Space>
                        <Tag color="cyan">水平 {lvIdx + 1}</Tag>
                        {attr.levels.length > 2 && (
                          <Button
                            type="link"
                            danger
                            size="small"
                            icon={<DeleteOutlined />}
                            onClick={() => handleRemoveLevel(attrIdx, lvIdx)}
                          />
                        )}
                      </Space>
                      <Space.Compact style={{ width: '100%' }}>
                        <Input
                          placeholder="机器标识（如 brand_a）—— 用于问卷生成和数据分析"
                          value={lv.value}
                          onChange={(e) => handleUpdateLevel(attrIdx, lvIdx, 'value', e.target.value)}
                          status={!lv.value?.trim() ? 'warning' : undefined}
                          style={{ width: 'calc(100% - 50px)' }}
                        />
                        <Tag style={{ display: 'flex', alignItems: 'center', height: '100%', margin: 0 }}>value</Tag>
                      </Space.Compact>
                      <Space.Compact style={{ width: '100%' }}>
                        <Input
                          placeholder="显示标签（如 品牌A）—— 用户看到的名称"
                          value={lv.label || ''}
                          onChange={(e) => handleUpdateLevel(attrIdx, lvIdx, 'label', e.target.value)}
                          style={{ width: 'calc(100% - 50px)' }}
                        />
                        <Tag style={{ display: 'flex', alignItems: 'center', height: '100%', margin: 0 }}>label</Tag>
                      </Space.Compact>
                      <Space.Compact style={{ width: '100%' }}>
                        <Input
                          placeholder="描述（可选）—— 该水平的补充说明"
                          value={lv.description || ''}
                          onChange={(e) => handleUpdateLevel(attrIdx, lvIdx, 'description', e.target.value)}
                          style={{ width: 'calc(100% - 50px)' }}
                        />
                        <Tag style={{ display: 'flex', alignItems: 'center', height: '100%', margin: 0 }}>描述</Tag>
                      </Space.Compact>
                    </Space>
                  </Card>
                </Col>
              ))}
              <Col xs={24} sm={12} md={8} lg={8}>
                <Button
                  type="dashed"
                  block
                  icon={<PlusOutlined />}
                  onClick={() => handleAddLevel(attrIdx)}
                  style={{ height: '100%', minHeight: 120 }}
                >
                  添加水平
                </Button>
              </Col>
            </Row>
          </Card>
        ))}

        <Button type="dashed" block icon={<PlusOutlined />} onClick={handleAddAttribute} style={{ marginTop: 8, marginBottom: 24 }}>
          添加属性
        </Button>

        <Card
          title="禁止组合配置"
          size="small"
          style={{ marginBottom: 24 }}
        >
          <Space direction="vertical" style={{ width: '100%' }}>
            <Row gutter={[16, 16]}>
              <Col xs={24} md={12}>
                <Space>
                  <Text>条件1:</Text>
                  <Select
                    placeholder="选择属性"
                    style={{ width: 160 }}
                    value={cond1.attribute_id || undefined}
                    onChange={(val) => setCond1({ attribute_id: val, level_value: '' })}
                    options={attributes.map((attr) => ({ value: attr.id, label: attr.name }))}
                    allowClear
                  />
                  <Select
                    placeholder="选择水平"
                    style={{ width: 160 }}
                    value={cond1.level_value || undefined}
                    onChange={(val) => setCond1((prev) => ({ ...prev, level_value: val }))}
                    options={cond1.attribute_id
                      ? attributes.find((a) => a.id === cond1.attribute_id)?.levels.map((lv) => ({ value: lv.value, label: lv.label })) || []
                      : []
                    }
                    disabled={!cond1.attribute_id}
                    allowClear
                  />
                </Space>
              </Col>
              <Col xs={24} md={12}>
                <Space>
                  <Text>条件2:</Text>
                  <Select
                    placeholder="选择属性"
                    style={{ width: 160 }}
                    value={cond2.attribute_id || undefined}
                    onChange={(val) => setCond2({ attribute_id: val, level_value: '' })}
                    options={attributes.map((attr) => ({ value: attr.id, label: attr.name }))}
                    allowClear
                  />
                  <Select
                    placeholder="选择水平"
                    style={{ width: 160 }}
                    value={cond2.level_value || undefined}
                    onChange={(val) => setCond2((prev) => ({ ...prev, level_value: val }))}
                    options={cond2.attribute_id
                      ? attributes.find((a) => a.id === cond2.attribute_id)?.levels.map((lv) => ({ value: lv.value, label: lv.label })) || []
                      : []
                    }
                    disabled={!cond2.attribute_id}
                    allowClear
                  />
                </Space>
              </Col>
            </Row>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={handleAddProhibitedPair}
              disabled={!cond1.attribute_id || !cond1.level_value || !cond2.attribute_id || !cond2.level_value || cond1.attribute_id === cond2.attribute_id}
            >
              添加禁止组合
            </Button>

            {prohibitedPairs.length > 0 && (
              <div>
                <Text strong>已禁止的组合:</Text>
                <div style={{ marginTop: 8 }}>
                  <Space size="small" wrap>
                    {prohibitedPairs.map((pair, idx) => {
                      const display = formatProhibitedPairDisplay(pair, attributes)
                      return (
                        <Tag
                          key={idx}
                          color="red"
                          closable
                          onClose={() => handleRemoveProhibitedPair(idx)}
                        >
                          {display}
                        </Tag>
                      )
                    })}
                  </Space>
                </div>
              </div>
            )}
          </Space>
        </Card>

        {attributes.length > 0 && (
          <Card size="small" title="属性与水平总览">
            <Table
              dataSource={attributes}
              columns={overviewColumns}
              pagination={false}
              size="small"
              rowKey="id"
            />
          </Card>
        )}
      </Card>
    </Spin>
  )
}

export default AttributeDesign
