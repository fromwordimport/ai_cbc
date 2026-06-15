import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Card, Form, Input, Button, Select, message, Alert, Space, Collapse,
  InputNumber, Radio, Row, Col,
} from 'antd'
import { PlusOutlined, MinusCircleOutlined } from '@ant-design/icons'
import { createStudy, generateQuestionnaire } from '@/services/api'
import type { AttributeDefinition, Level } from '@/types/api'

const { TextArea } = Input
const { Option } = Select
const { Panel } = Collapse

const DEFAULT_ATTRIBUTE: AttributeDefinition = {
  id: '',
  name: '',
  type: 'categorical',
  levels: [{ value: '', label: '' }],
}

const StudyCreate: React.FC = () => {
  const navigate = useNavigate()
  const [form] = Form.useForm()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [useCustomAttributes, setUseCustomAttributes] = useState(false)

  const handleSubmit = async (values: {
    study_id: string
    product_category: string
    research_goal: string
    target_segments: string[]
    attributes?: AttributeDefinition[]
    design_parameters?: {
      n_choice_sets?: number
      n_alternatives?: number
      include_none?: boolean
    }
  }) => {
    setLoading(true)
    setError(null)

    const payload: Parameters<typeof createStudy>[0] = {
      study_id: values.study_id,
      product_category: values.product_category,
      research_goal: values.research_goal,
      target_segments: values.target_segments || [],
    }

    if (useCustomAttributes && values.attributes && values.attributes.length > 0) {
      payload.attributes = values.attributes
        .map((attr) => ({
          ...attr,
          levels: attr.levels.filter((l) => l.value.trim() !== ''),
        }))
        .filter((attr) => attr.id.trim() !== '' && attr.name.trim() !== '')
    }

    if (values.design_parameters) {
      const dp: Record<string, unknown> = {}
      if (values.design_parameters.n_choice_sets !== undefined) {
        dp.n_choice_sets = values.design_parameters.n_choice_sets
      }
      if (values.design_parameters.n_alternatives !== undefined) {
        dp.n_alternatives = values.design_parameters.n_alternatives
      }
      if (values.design_parameters.include_none !== undefined) {
        dp.include_none = values.design_parameters.include_none
      }
      if (Object.keys(dp).length > 0) {
        payload.design_parameters = dp
      }
    }

    try {
      const study = await createStudy(payload)
      message.success(`研究 "${study.study_id}" 创建成功`)

      message.loading({ content: '正在生成 CBC 问卷...', key: 'gen_q' })
      try {
        const q = await generateQuestionnaire(study.study_id)
        message.success({ content: `问卷生成完成，D-efficiency=${q.d_efficiency?.toFixed(3) || 'N/A'}`, key: 'gen_q' })
        navigate(`/studies/${study.study_id}/design`)
      } catch (genErr) {
        message.error({ content: '问卷生成失败，研究已创建但无问卷。请在研究列表中删除或手动重新生成。', key: 'gen_q' })
        setError(`研究已创建(ID: ${study.study_id})，但问卷生成失败: ${genErr instanceof Error ? genErr.message : '未知错误'}`)
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : '创建失败'
      setError(msg)
      message.error(msg)
    } finally {
      setLoading(false)
    }
  }

  const renderLevelInput = (
    fields: { key: number; name: number; fieldKey?: number }[],
    { add, remove }: { add: (defaultValue?: Level) => void; remove: (index: number) => void },
  ) => (
    <div>
      {fields.map((field) => (
        <Space key={field.key} align="baseline" style={{ width: '100%', marginBottom: 8 }}>
          <Form.Item
            noStyle
            name={[field.name, 'value']}
            rules={[{ required: true, message: '请输入水平值' }]}
          >
            <Input placeholder="水平值（如 brand_0）" />
          </Form.Item>
          <Form.Item
            noStyle
            name={[field.name, 'label']}
            rules={[{ required: true, message: '请输入显示标签' }]}
          >
            <Input placeholder="显示标签（如 美的）" />
          </Form.Item>
          <Form.Item
            noStyle
            name={[field.name, 'description']}
          >
            <Input placeholder="描述（可选）" />
          </Form.Item>
          {fields.length > 1 && (
            <MinusCircleOutlined onClick={() => remove(field.name)} />
          )}
        </Space>
      ))}
      <Button type="dashed" onClick={() => add({ value: '', label: '', description: '' })} block icon={<PlusOutlined />}>
        添加水平
      </Button>
    </div>
  )

  return (
    <Card title="创建新研究" style={{ maxWidth: 900, margin: '0 auto' }}>
      {error && (
        <Alert message="创建失败" description={error} type="error" showIcon style={{ marginBottom: 16 }} />
      )}
      <Form
        form={form}
        layout="vertical"
        onFinish={handleSubmit}
        initialValues={{
          product_category: '洗碗机',
          target_segments: [],
          attributes: [DEFAULT_ATTRIBUTE],
          design_parameters: {
            n_choice_sets: 12,
            n_alternatives: 3,
            include_none: true,
          },
        }}
      >
        <Form.Item
          label="研究ID"
          name="study_id"
          rules={[{ required: true, message: '请输入研究ID' }, { pattern: /^[a-zA-Z0-9_-]+$/, message: '仅允许字母、数字、下划线和连字符' }]}
        >
          <Input placeholder="例如：dishwasher-2024q3" />
        </Form.Item>

        <Form.Item
          label="产品类别"
          name="product_category"
          rules={[{ required: true, message: '请输入产品类别' }]}
        >
          <Input placeholder="例如：洗碗机、扫地机器人" />
        </Form.Item>

        <Form.Item
          label="研究目标"
          name="research_goal"
          rules={[{ required: true, message: '请输入研究目标' }]}
        >
          <TextArea rows={3} placeholder="例如：评估消费者对洗碗机各属性水平的偏好，指导新品定价与功能配置" />
        </Form.Item>

        <Form.Item label="目标人群" name="target_segments">
          <Select mode="tags" placeholder="选择或输入目标人群标签，按回车自定义">
            <Option value="一线城市年轻家庭">一线城市年轻家庭</Option>
            <Option value="新一线品质追求者">新一线品质追求者</Option>
            <Option value="二线务实家庭">二线务实家庭</Option>
            <Option value="独居青年">独居青年</Option>
            <Option value="年轻白领">年轻白领</Option>
            <Option value="宠物家庭">宠物家庭</Option>
            <Option value="银发族">银发族</Option>
          </Select>
        </Form.Item>

        <Form.Item>
          <Radio.Group
            value={useCustomAttributes ? 'custom' : 'default'}
            onChange={(e) => setUseCustomAttributes(e.target.value === 'custom')}
          >
            <Radio.Button value="default">使用默认属性</Radio.Button>
            <Radio.Button value="custom">自定义属性</Radio.Button>
          </Radio.Group>
        </Form.Item>

        {useCustomAttributes && (
          <Card title="自定义属性" size="small" style={{ marginBottom: 16 }}>
            <Form.List name="attributes">
              {(fields, { add, remove }) => (
                <>
                  {fields.map((field) => (
                    <Card
                      key={field.key}
                      size="small"
                      style={{ marginBottom: 12 }}
                      extra={
                        fields.length > 1 ? (
                          <Button type="link" danger onClick={() => remove(field.name)}>删除</Button>
                        ) : null
                      }
                    >
                      <Row gutter={16}>
                        <Col span={8}>
                          <Form.Item
                            label="属性ID"
                            name={[field.name, 'id']}
                            rules={[{ required: true, message: '请输入属性ID' }]}
                          >
                            <Input placeholder="例如 price" />
                          </Form.Item>
                        </Col>
                        <Col span={8}>
                          <Form.Item
                            label="属性名称"
                            name={[field.name, 'name']}
                            rules={[{ required: true, message: '请输入属性名称' }]}
                          >
                            <Input placeholder="例如 价格" />
                          </Form.Item>
                        </Col>
                        <Col span={8}>
                          <Form.Item
                            label="类型"
                            name={[field.name, 'type']}
                            rules={[{ required: true, message: '请选择类型' }]}
                          >
                            <Select>
                              <Option value="categorical">类别型</Option>
                              <Option value="ordinal">有序型</Option>
                              <Option value="continuous">连续型</Option>
                              <Option value="price">价格型</Option>
                            </Select>
                          </Form.Item>
                        </Col>
                      </Row>

                      <Form.Item label="属性水平">
                        <Form.List name={[field.name, 'levels']}>
                          {(levelFields, levelOps) => renderLevelInput(levelFields, levelOps)}
                        </Form.List>
                      </Form.Item>
                    </Card>
                  ))}
                  <Button
                    type="dashed"
                    onClick={() => add({ ...DEFAULT_ATTRIBUTE })}
                    block
                    icon={<PlusOutlined />}
                  >
                    添加属性
                  </Button>
                </>
              )}
            </Form.List>
          </Card>
        )}

        <Collapse ghost style={{ marginBottom: 16 }}>
          <Panel header="高级实验设计参数" key="design">
            <Row gutter={16}>
              <Col span={8}>
                <Form.Item label="选择集数量" name={['design_parameters', 'n_choice_sets']}>
                  <InputNumber min={1} max={100} style={{ width: '100%' }} />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item label="每集选项数" name={['design_parameters', 'n_alternatives']}>
                  <InputNumber min={2} max={10} style={{ width: '100%' }} />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item label="包含 None 选项" name={['design_parameters', 'include_none']} valuePropName="checked">
                  <Radio.Group>
                    <Radio value={true}>是</Radio>
                    <Radio value={false}>否</Radio>
                  </Radio.Group>
                </Form.Item>
              </Col>
            </Row>
          </Panel>
        </Collapse>

        <Form.Item>
          <Button type="primary" htmlType="submit" loading={loading} block>
            创建研究并生成问卷
          </Button>
        </Form.Item>
      </Form>
    </Card>
  )
}

export default StudyCreate
