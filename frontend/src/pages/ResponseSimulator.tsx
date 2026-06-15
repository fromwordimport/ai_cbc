import React, { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Card, Button, Select, InputNumber, Checkbox, message, Spin, Alert, Space, Typography } from 'antd'
import { getPersonas, simulateResponses, exportDataset } from '@/services/api'
import type { PersonaSummary, SimulateResponsesRequest } from '@/types/api'

const { Text } = Typography

const ResponseSimulator: React.FC = () => {
  const { studyId } = useParams<{ studyId: string }>()
  const [personas, setPersonas] = useState<PersonaSummary[]>([])
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [mode, setMode] = useState<'rule' | 'llm'>('rule')
  const [deterministic, setDeterministic] = useState(false)
  const [seed, setSeed] = useState<number | undefined>(undefined)
  const [loading, setLoading] = useState(false)
  const [simulating, setSimulating] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<{ simulated: number; failed: number } | null>(null)

  useEffect(() => {
    const fetch = async () => {
      setLoading(true)
      try {
        const res = await getPersonas(1, 100)
        setPersonas(res.personas)
      } catch (err) {
        message.error('加载画像失败')
      } finally {
        setLoading(false)
      }
    }
    fetch()
  }, [])

  const handleSimulate = async () => {
    if (!studyId || selectedIds.length === 0) {
      message.warning('请选择至少一个虚拟消费者')
      return
    }
    setSimulating(true)
    setError(null)
    setResult(null)
    try {
      const payload: SimulateResponsesRequest = {
        persona_ids: selectedIds,
        mode,
        deterministic,
      }
      if (seed !== undefined) payload.seed = seed
      const res = await simulateResponses(studyId, payload)
      setResult({ simulated: res.simulated || selectedIds.length, failed: res.failed || 0 })
      message.success(`模拟完成：${res.simulated || selectedIds.length} 个消费者已作答`)
    } catch (err) {
      const msg = err instanceof Error ? err.message : '模拟失败'
      setError(msg)
      message.error(msg)
    } finally {
      setSimulating(false)
    }
  }

  const handleExport = async () => {
    if (!studyId) return
    setExporting(true)
    try {
      const res = await exportDataset(studyId)
      message.success(`数据集导出成功：${res.n_total_records} 条记录`)
    } catch (err) {
      message.error('导出失败')
    } finally {
      setExporting(false)
    }
  }

  return (
    <Spin spinning={loading}>
      {error && <Alert message="模拟失败" description={error} type="error" showIcon style={{ marginBottom: 16 }} />}

      <Card
        title="模拟作答"
        extra={
          <Space>
            <Button onClick={handleExport} loading={exporting}>
              导出数据集
            </Button>
          </Space>
        }
      >
        <Select
          mode="multiple"
          placeholder="选择要模拟的虚拟消费者"
          value={selectedIds}
          onChange={setSelectedIds}
          style={{ width: '100%', marginBottom: 16 }}
          options={personas.map((p) => ({ label: `${p.persona_id} (${p.segment})`, value: p.persona_id }))}
        />

        <Select
          placeholder="选择模拟模式"
          value={mode}
          onChange={setMode}
          style={{ width: '100%', marginBottom: 16 }}
          options={[
            { label: '规则模式 (rule)', value: 'rule' },
            { label: 'LLM 模式 (llm)', value: 'llm' },
          ]}
        />

        <Space style={{ width: '100%', marginBottom: 16 }}>
          <Checkbox
            checked={deterministic}
            onChange={(e) => setDeterministic(e.target.checked)}
            disabled={mode !== 'rule'}
          >
            确定性选择（仅 rule 模式）
          </Checkbox>
          <InputNumber
            placeholder="随机种子 (可选)"
            value={seed}
            onChange={(v) => setSeed(v ?? undefined)}
            style={{ width: 200 }}
          />
        </Space>

        <Button type="primary" onClick={handleSimulate} loading={simulating} disabled={selectedIds.length === 0} block>
          开始模拟作答
        </Button>

        {simulating && (
          <div style={{ marginTop: 16, textAlign: 'center' }}>
            <Spin size="small" />
            <Text type="secondary" style={{ marginLeft: 8 }}>正在模拟作答，请稍候...</Text>
          </div>
        )}

        {result && (
          <Alert
            message="模拟完成"
            description={`成功模拟 ${result.simulated} 个消费者作答`}
            type="success"
            showIcon
            style={{ marginTop: 16 }}
          />
        )}
      </Card>
    </Spin>
  )
}

export default ResponseSimulator
