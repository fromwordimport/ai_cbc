import React from 'react'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { Layout as AntLayout, Menu, Typography, Badge, theme } from 'antd'
import {
  DashboardOutlined,
  BarChartOutlined,
  PieChartOutlined,
  ExperimentOutlined,
  UserOutlined,
  PlusCircleOutlined,
  CommentOutlined,
  SwapOutlined,
  FileTextOutlined,
  SettingOutlined,
  ClockCircleOutlined,
  PlayCircleOutlined,
} from '@ant-design/icons'
import { useAppStore } from '@/stores/appStore'

const { Header, Sider, Content } = AntLayout
const { Title } = Typography

const menuItems = [
  {
    key: '/',
    icon: <DashboardOutlined />,
    label: '总览',
  },
  {
    key: '/studies/new',
    icon: <PlusCircleOutlined />,
    label: '创建研究',
  },
  {
    key: '/personas',
    icon: <UserOutlined />,
    label: '画像管理',
  },
  {
    key: '/questionnaires',
    icon: <FileTextOutlined />,
    label: '问卷配置',
  },
  {
    key: '/interview',
    icon: <CommentOutlined />,
    label: '对话实验室',
  },
  {
    key: '/importance',
    icon: <BarChartOutlined />,
    label: '属性重要性看板',
  },
  {
    key: '/segment-comparison',
    icon: <SwapOutlined />,
    label: '细分群体比较',
  },
  {
    key: '/market-simulator',
    icon: <PieChartOutlined />,
    label: '市场份额模拟器',
  },
  {
    key: '/analysis-status',
    icon: <ClockCircleOutlined />,
    label: '分析任务状态',
  },
  {
    key: '/responses',
    icon: <PlayCircleOutlined />,
    label: '作答模拟',
  },
  {
    key: '/settings',
    icon: <SettingOutlined />,
    label: '系统设置',
  },
]

const Layout: React.FC = () => {
  const location = useLocation()
  const navigate = useNavigate()
  const { runningJobs } = useAppStore()
  const {
    token: { colorBgContainer, borderRadiusLG },
  } = theme.useToken()

  // Match exact or nested paths for menu highlighting
  const selectedKeys = React.useMemo(() => {
    const exact = menuItems.find((item) => item.key === location.pathname)
    if (exact) return [location.pathname]
    // For nested study routes, don't highlight any menu item
    return []
  }, [location.pathname])

  // Determine page title for nested routes too
  const pageTitle = React.useMemo(() => {
    const exact = menuItems.find((item) => item.key === location.pathname)
    if (exact) return exact.label
    // Check if it's a study response simulator page
    if (location.pathname.match(/\/studies\/[^/]+\/responses/)) {
      return '作答模拟'
    }
    return 'AI_CBC'
  }, [location.pathname])

  return (
    <AntLayout style={{ minHeight: '100vh' }}>
      <Sider trigger={null} collapsible theme="light" width={220}>
        <div style={{ padding: '16px', borderBottom: '1px solid #f0f0f0' }}>
          <Title level={5} style={{ margin: 0, display: 'flex', alignItems: 'center', gap: 8 }}>
            <ExperimentOutlined style={{ color: '#1677ff' }} />
            AI_CBC
          </Title>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            虚拟消费者联合分析
          </Typography.Text>
        </div>
        <Menu
          mode="inline"
          selectedKeys={selectedKeys}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
          style={{ borderRight: 0 }}
        />
      </Sider>
      <AntLayout>
        <Header
          style={{
            padding: '0 24px',
            background: colorBgContainer,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            borderBottom: '1px solid #f0f0f0',
          }}
        >
          <Typography.Text strong style={{ fontSize: 16 }}>
            {pageTitle}
          </Typography.Text>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            {runningJobs.length > 0 && (
              <Badge count={runningJobs.length} style={{ backgroundColor: '#1677ff' }}>
                <Typography.Text type="secondary">分析任务运行中</Typography.Text>
              </Badge>
            )}
          </div>
        </Header>
        <Content
          style={{
            margin: 24,
            padding: 24,
            background: colorBgContainer,
            borderRadius: borderRadiusLG,
            minHeight: 280,
            overflow: 'auto',
          }}
        >
          <Outlet />
        </Content>
      </AntLayout>
    </AntLayout>
  )
}

export default Layout
