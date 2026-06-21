import { describe, it, expect, vi, beforeEach } from 'vitest'
import { login, logout } from '@/services/auth'
import { getToken, getRole } from '@/services/token'

const mockPost = vi.fn()
vi.mock('@/services/api', () => ({
  default: { post: (...args: any[]) => mockPost(...args) },
}))

describe('auth service', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.clearAllMocks()
  })

  it('stores token and role on login', async () => {
    mockPost.mockResolvedValueOnce({
      data: {
        access_token: 'token-1',
        token_type: 'bearer',
        role: 'researcher',
        expires_in_minutes: 60,
      },
    })
    await login({ username: 'researcher', password: 'pass' })
    expect(getToken()).toBe('token-1')
    expect(getRole()).toBe('researcher')
  })

  it('clears auth on logout', () => {
    localStorage.setItem('aicbc_token', 'token-1')
    localStorage.setItem('aicbc_role', 'admin')
    logout()
    expect(getToken()).toBeNull()
    expect(getRole()).toBeNull()
  })
})
