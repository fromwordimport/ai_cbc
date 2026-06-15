import React, { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Card, Select, Button, Table, Tag, message, Spin, Alert, Input } from 'antd'
import { getStudies, getSegmentComparison } from '@/services/api'
import type { StudySummary, SegmentComparisonResponse } from '@/types/api'

const SegmentComparison: React.FC = () => {
  const [searchParams] = useSearchParams()
  const [studies, setStudies] = useState<StudySummary[]>([])
  const [selectedStudyId, setSelectedStudyId] = useState<string | null>(searchParams.get('study'))
  const [analysisId, setAnalysisId] = useState<string>('')
  const [segmentA, setSegmentA] = useState('')
  const [segmentB, setSegmentB] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<SegmentComparisonResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Derive segment options from the selected study's target_segments
  const selectedStudy = studies.find((s) => s.study_id === selectedStudyId)
  const segmentOptions = (selectedStudy?.target_segments || []).map((seg) => ({
    label: seg,
    value: seg,
  }))

  useEffect(() => {
    const fetch = async () => {
      try {
        const res = await getStudies()
        setStudies(res.studies)
        // Auto-select study from URL param
        const studyFromUrl = searchParams.get('study')
        if (studyFromUrl) {
          setSelectedStudyId(studyFromUrl)
        }
      } catch {
        message.error('加载研究列表失败')
      }
    }
    fetch()
  }, [searchParams])

  const handleCompare = async () => {
    if (!selectedStudyId || !analysisId || !segmentA || !segmentB) {
      message.warning('请填写所有字段')
      return
    }
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const data = await getSegmentComparison(selectedStudyId, analysisId, segmentA, segmentB)
      setResult(data)
    } catch (err) {
      const msg = err instanceof Error ? err.message : '对比失败'
      setError(msg)
      message.error(msg)
    } finally {
      setLoading(false)
    }
  }

  const columns = [
    { title: '属性', dataIndex: 'attribute', key: 'attribute' },
    { title: '方法', dataIndex: 'method', key: 'method' },
    {
      title: 't统计量',
      dataIndex: 't_statistic',
      key: 't_statistic',
      render: (v: number) => v?.toFixed(3),
    },
    {
      title: 'p值',
      dataIndex: 'p_value',
      key: 'p_value',
      render: (v: number) => v?.toFixed(4),
    },
    {
      title: '显著性',
      dataIndex: 'significant',
      key: 'significant',
      render: (v: boolean) => (v ? <Tag color="green">显著</Tag> : <Tag>不显著</Tag>),
    },
    {
      title: '效应量',
      dataIndex: 'cohens_d',
      key: 'cohens_d',
      render: (v: number) => v?.toFixed(3),
    },
    {
      title: `${segmentA || 'A'} 均值`,
      dataIndex: 'mean_a',
      key: 'mean_a',
      render: (v: number) => v?.toFixed(3),
    },
    {
      title: `${segmentB || 'B'} 均值`,
      dataIndex: 'mean_b',
      key: 'mean_b',
      render: (v: number) => v?.toFixed(3),
    },
  ]

  return (
    <Card title="细分群体偏好对比">
      <Spin spinning={loading}>
        {error && <Alert message="对比失败" description={error} type="error" showIcon style={{ marginBottom: 16 }} />}

        <Select
          placeholder="选择研究"
          value={selectedStudyId}
          onChange={setSelectedStudyId}
          style={{ width: '100%', marginBottom: 12 }}
          options={studies.map((s) => ({ label: s.study_id, value: s.study_id }))}
        />

        <Input
          placeholder="分析结果ID（输入或粘贴）"
          value={analysisId}
          onChange={(e) => setAnalysisId(e.target.value)}
          style={{ width: '100%', marginBottom: 12 }}
          allowClear
        />

        <Select
          placeholder={selectedStudy ? '群体 A（选择预设或输入自定义）' : '群体 A（请先选择研究）'}
          value={segmentA ? [segmentA] : undefined}
          onChange={(val) => setSegmentA(Array.isArray(val) ? val[0] || '' : '')}
          style={{ width: '100%', marginBottom: 12 }}
          options={segmentOptions}
          mode="tags"
          maxCount={1}
          showSearch
          disabled={!selectedStudyId}
          notFoundContent={selectedStudyId ? '该研究未定义目标群体，请手动输入' : '请先选择研究'}
        />

        <Select
          placeholder={selectedStudy ? '群体 B（选择预设或输入自定义）' : '群体 B（请先选择研究）'}
          value={segmentB ? [segmentB] : undefined}
          onChange={(val) => setSegmentB(Array.isArray(val) ? val[0] || '' : '')}
          style={{ width: '100%', marginBottom: 12 }}
          options={segmentOptions}
          mode="tags"
          maxCount={1}
          showSearch
          disabled={!selectedStudyId}
          notFoundContent={selectedStudyId ? '该研究未定义目标群体，请手动输入' : '请先选择研究'}
        />

        <Button type="primary" onClick={handleCompare} disabled={!selectedStudyId || !analysisId || !segmentA || !segmentB} block>
          运行对比分析
        </Button>

        {result && (
          <>
            <Card title="总体检验" size="small" style={{ marginTop: 16 }}>
              <p>方法: {result.overall_test.method}</p>
              <p>统计量: {result.overall_test.statistic.toFixed(3)}</p>
              <p>p值: {result.overall_test.p_value.toFixed(4)}</p>
              <p>
                显著性:{" "}
                {result.overall_test.significant ? (
                  <Tag color="green">显著</Tag>
                ) : (
                  <Tag>不显著</Tag>
                )}
              </p>
            </Card>

            <Table
              dataSource={result.per_attribute}
              columns={columns}
              rowKey="attribute"
              size="small"
              style={{ marginTop: 16 }}
              pagination={false}
            />
          </>
        )}
      </Spin>
    </Card>
  )
}

export default SegmentComparison
