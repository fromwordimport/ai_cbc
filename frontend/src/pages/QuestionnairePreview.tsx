import React, { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Card, Table, Tag, Spin, Alert, Descriptions } from 'antd'
import { getQuestionnaire } from '@/services/api'
import type { QuestionnaireDetail, ChoiceSet } from '@/types/api'

const QuestionnairePreview: React.FC = () => {
  const { studyId } = useParams<{ studyId: string }>()
  const [questionnaire, setQuestionnaire] = useState<QuestionnaireDetail | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!studyId) return
    const fetch = async () => {
      setLoading(true)
      setError(null)
      try {
        const q = await getQuestionnaire(studyId)
        setQuestionnaire(q)
      } catch (err) {
        setError(err instanceof Error ? err.message : '加载问卷失败')
      } finally {
        setLoading(false)
      }
    }
    fetch()
  }, [studyId])

  if (error) {
    return <Alert message="加载失败" description={error} type="error" showIcon />
  }

  return (
    <Spin spinning={loading}>
      {questionnaire && (
        <>
          <Card title="实验设计参数" style={{ marginBottom: 16 }}>
            <Descriptions size="small" bordered>
              <Descriptions.Item label="算法">{questionnaire.design_params.algorithm}</Descriptions.Item>
              <Descriptions.Item label="D-efficiency">{questionnaire.design_params.d_efficiency?.toFixed(3) || 'N/A'}</Descriptions.Item>
              <Descriptions.Item label="选择集数量">{questionnaire.design_params.n_choice_sets}</Descriptions.Item>
              <Descriptions.Item label="每集选项数">{questionnaire.design_params.n_alternatives}</Descriptions.Item>
              <Descriptions.Item label="含None选项">{questionnaire.design_params.include_none ? '是' : '否'}</Descriptions.Item>
            </Descriptions>
          </Card>

          <Card title="选择集预览">
            {questionnaire.choice_sets.map((cs: ChoiceSet) => (
              <Card
                key={cs.choice_set_id}
                type="inner"
                title={`选择集 #${cs.choice_set_id}`}
                style={{ marginBottom: 12 }}
                size="small"
              >
                <Table
                  dataSource={cs.alternatives}
                  columns={[
                    { title: '选项', dataIndex: 'alt_index', key: 'alt_index', render: (v: number) => <Tag>选项 {String.fromCharCode(65 + v)}</Tag> },
                    ...Object.keys(cs.alternatives[0]?.attributes || {}).map((attr) => ({
                      title: attr,
                      dataIndex: ['attributes', attr],
                      key: attr,
                    })),
                  ]}
                  pagination={false}
                  size="small"
                  rowKey="alt_index"
                />
              </Card>
            ))}
          </Card>
        </>
      )}
    </Spin>
  )
}

export default QuestionnairePreview
