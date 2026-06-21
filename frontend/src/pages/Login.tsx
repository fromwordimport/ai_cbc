import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Card, Form, Input, Button, Alert, Typography } from 'antd'
import { LoginOutlined } from '@ant-design/icons'
import { login } from '@/services/auth'

const { Title } = Typography

const Login: React.FC = () => {
  const navigate = useNavigate()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (values: { username: string; password: string }) => {
    setLoading(true)
    setError(null)
    try {
      await login(values)
      navigate('/', { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : '登录失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: '#f0f2f5',
    }}>
      <Card style={{ width: 360, boxShadow: '0 4px 12px rgba(0,0,0,0.1)' }}>
        <div style={{ textAlign: 'center', marginBottom: 24 }}>
          <Title level={3} style={{ margin: 0 }}>AI_CBC</Title>
          <Typography.Text type="secondary">虚拟消费者联合分析平台</Typography.Text>
        </div>
        {error && (
          <Alert message="登录失败" description={error} type="error" showIcon style={{ marginBottom: 16 }} />
        )}
        <Form layout="vertical" onFinish={handleSubmit}>
          <Form.Item
            label="用户名"
            name="username"
            rules={[{ required: true, message: '请输入用户名' }]}
          >
            <Input placeholder="researcher 或 admin" />
          </Form.Item>
          <Form.Item
            label="密码"
            name="password"
            rules={[{ required: true, message: '请输入密码' }]}
          >
            <Input.Password placeholder="密码" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={loading} block icon={<LoginOutlined />}>
              登录
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  )
}

export default Login
