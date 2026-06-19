import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Login from '@/pages/Login'

const mockLogin = vi.fn()
vi.mock('@/services/auth', () => ({
  login: (...args: any[]) => mockLogin(...args),
}))

const mockNavigate = vi.fn()
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return { ...actual, useNavigate: () => mockNavigate }
})

describe('Login page', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  const renderPage = () =>
    render(
      <MemoryRouter>
        <Login />
      </MemoryRouter>,
    )

  it('submits credentials and navigates on success', async () => {
    mockLogin.mockResolvedValueOnce({})
    renderPage()

    fireEvent.change(screen.getByPlaceholderText('researcher 或 admin'), {
      target: { value: 'researcher' },
    })
    fireEvent.change(screen.getByPlaceholderText('密码'), {
      target: { value: 'pass' },
    })
    fireEvent.click(screen.getByText('登录'))

    await waitFor(() => expect(mockLogin).toHaveBeenCalledWith({ username: 'researcher', password: 'pass' }))
    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith('/', { replace: true }))
  })

  it('shows error on failure', async () => {
    mockLogin.mockRejectedValueOnce(new Error('invalid'))
    renderPage()

    fireEvent.change(screen.getByPlaceholderText('researcher 或 admin'), {
      target: { value: 'researcher' },
    })
    fireEvent.change(screen.getByPlaceholderText('密码'), {
      target: { value: 'wrong' },
    })
    fireEvent.click(screen.getByText('登录'))

    await waitFor(() => expect(screen.getByText('invalid')).toBeInTheDocument())
  })
})
