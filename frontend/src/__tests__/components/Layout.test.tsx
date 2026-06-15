import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import Layout from '@/components/Layout'
import { useAppStore } from '@/stores/appStore'

const renderWithRouter = (initialRoute = '/') =>
  render(
    <MemoryRouter initialEntries={[initialRoute]}>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<div>Dashboard</div>} />
          <Route path="/studies/new" element={<div>New Study</div>} />
          <Route path="/settings" element={<div>Settings</div>} />
          <Route path="/studies/:studyId/responses" element={<div>Responses</div>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  )

describe('Layout', () => {
  beforeEach(() => {
    useAppStore.setState({ ...useAppStore.getInitialState(), runningJobs: [] })
  })

  it('renders logo and menu items', () => {
    renderWithRouter('/')
    expect(screen.getByText('AI_CBC')).toBeInTheDocument()
    expect(screen.getAllByText('总览').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('创建研究')).toBeInTheDocument()
  })

  it('navigates when menu item clicked', () => {
    renderWithRouter('/')
    fireEvent.click(screen.getByText('创建研究'))
    expect(screen.getByText('New Study')).toBeInTheDocument()
  })

  it('shows analysis badge when jobs are running', () => {
    useAppStore.setState({
      ...useAppStore.getInitialState(),
      runningJobs: [{ analysis_id: 'a1', status: 'RUNNING' } as any],
    })
    renderWithRouter('/')
    expect(screen.getByText('分析任务运行中')).toBeInTheDocument()
  })

  it('shows nested page title for response simulator', () => {
    renderWithRouter('/studies/s1/responses')
    expect(screen.getAllByText('作答模拟').length).toBeGreaterThanOrEqual(1)
  })
})
