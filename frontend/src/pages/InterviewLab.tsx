import React, { useEffect, useState } from 'react'
import { Card, Select, Input, Button, List, Tag, Space, message, Radio, Typography } from 'antd'
import { getPersonas, converse, runInterview } from '@/services/api'
import type { PersonaSummary, ConverseResponse } from '@/types/api'

const { TextArea } = Input
const { Text } = Typography

type ChatTurn = {
  turn: number
  question: string
  response: string
  emotion: string
  inconsistency: boolean
}

const InterviewLab: React.FC = () => {
  const [personas, setPersonas] = useState<PersonaSummary[]>([])
  const [selectedPersonaId, setSelectedPersonaId] = useState<string | null>(null)
  const [mode, setMode] = useState<'single' | 'multi'>('single')

  // Single-turn state
  const [singleQuestion, setSingleQuestion] = useState('')

  // Multi-round state
  const [questions, setQuestions] = useState<string[]>([''])

  // Shared history and loading
  const [history, setHistory] = useState<ChatTurn[]>([])
  const [loading, setLoading] = useState(false)
  const [personaLoading, setPersonaLoading] = useState(false)

  const loadPersonas = async () => {
    setPersonaLoading(true)
    try {
      const res = await getPersonas(1, 100)
      setPersonas(res.personas)
    } catch {
      message.error('加载画像失败')
    } finally {
      setPersonaLoading(false)
    }
  }

  useEffect(() => {
    loadPersonas()
  }, [])

  const appendTurns = (turns: ConverseResponse[]) => {
    setHistory((prev) => {
      const nextTurn = prev.length + 1
      const newTurns = turns.map((t, idx) => ({
        turn: nextTurn + idx,
        question: t.researcher_question,
        response: t.consumer_response,
        emotion: t.emotion_tag,
        inconsistency: t.inconsistency_flag,
      }))
      return [...prev, ...newTurns]
    })
  }

  const handleSingleSend = async () => {
    if (!selectedPersonaId || !singleQuestion.trim()) {
      message.warning('请选择画像并输入问题')
      return
    }
    setLoading(true)
    try {
      const data = await converse(selectedPersonaId, { question: singleQuestion.trim(), context: {} })
      appendTurns([data])
      setSingleQuestion('')
    } catch (err) {
      message.error(err instanceof Error ? err.message : '对话失败')
    } finally {
      setLoading(false)
    }
  }

  const handleRunInterview = async () => {
    if (!selectedPersonaId) {
      message.warning('请选择画像')
      return
    }
    const validQuestions = questions.map((q) => q.trim()).filter(Boolean)
    if (validQuestions.length === 0) {
      message.warning('请至少输入一个访谈问题')
      return
    }
    setLoading(true)
    try {
      const data = await runInterview(selectedPersonaId, { questions: validQuestions, context: {} })
      appendTurns(data.turns)
    } catch (err) {
      message.error(err instanceof Error ? err.message : '访谈失败')
    } finally {
      setLoading(false)
    }
  }

  const updateQuestion = (idx: number, value: string) => {
    setQuestions((prev) => prev.map((q, i) => (i === idx ? value : q)))
  }

  const addQuestion = () => {
    setQuestions((prev) => [...prev, ''])
  }

  const removeQuestion = (idx: number) => {
    setQuestions((prev) => prev.filter((_, i) => i !== idx))
  }

  return (
    <Card title="消费者对话实验室">
      <Space direction="vertical" style={{ width: '100%' }}>
        <Select
          placeholder="选择虚拟消费者"
          loading={personaLoading}
          value={selectedPersonaId}
          onChange={setSelectedPersonaId}
          style={{ width: '100%' }}
          options={personas.map((p) => ({ label: `${p.persona_id} (${p.segment})`, value: p.persona_id }))}
        />

        <Radio.Group
          value={mode}
          onChange={(e) => setMode(e.target.value)}
          style={{ marginBottom: 8 }}
        >
          <Radio.Button value="single">单轮对话</Radio.Button>
          <Radio.Button value="multi">多轮访谈</Radio.Button>
        </Radio.Group>

        {mode === 'single' ? (
          <>
            <TextArea
              rows={3}
              placeholder="输入研究员的问题..."
              value={singleQuestion}
              onChange={(e) => setSingleQuestion(e.target.value)}
              maxLength={2000}
              showCount
            />
            <Button type="primary" onClick={handleSingleSend} loading={loading} disabled={!selectedPersonaId}>
              发送问题
            </Button>
          </>
        ) : (
          <>
            {questions.map((q, idx) => (
              <Space key={idx} style={{ width: '100%' }}>
                <Text style={{ minWidth: 60 }}>问题 {idx + 1}</Text>
                <TextArea
                  rows={2}
                  placeholder={`访谈问题 ${idx + 1}`}
                  value={q}
                  onChange={(e) => updateQuestion(idx, e.target.value)}
                  maxLength={2000}
                  showCount
                  style={{ flex: 1 }}
                />
                {questions.length > 1 && (
                  <Button danger onClick={() => removeQuestion(idx)}>
                    删除
                  </Button>
                )}
              </Space>
            ))}
            <Button type="dashed" onClick={addQuestion} block>
              添加问题
            </Button>
            <Button
              type="primary"
              onClick={handleRunInterview}
              loading={loading}
              disabled={!selectedPersonaId}
              block
            >
              运行多轮访谈
            </Button>
          </>
        )}

        {history.length > 0 && (
          <List
            header={<div>对话历史</div>}
            bordered
            dataSource={history}
            renderItem={(item) => (
              <List.Item>
                <Space direction="vertical" style={{ width: '100%' }}>
                  <div>
                    <Tag color="blue">研究员 #{item.turn}</Tag>
                    {item.question}
                  </div>
                  <div>
                    <Tag color="green">消费者</Tag>
                    <Tag>{item.emotion}</Tag>
                    {item.inconsistency && <Tag color="red">矛盾警告</Tag>}
                    <div style={{ marginTop: 4, padding: 8, background: '#f6ffed', borderRadius: 4 }}>
                      {item.response}
                    </div>
                  </div>
                </Space>
              </List.Item>
            )}
          />
        )}
      </Space>
    </Card>
  )
}

export default InterviewLab
