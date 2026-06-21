import { describe, it, expect, beforeEach } from 'vitest'
import {
  setAuth,
  clearAuth,
  getToken,
  getRole,
  isAuthenticated,
  isAdmin,
} from '@/services/token'

describe('token storage', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('stores and reads token/role', () => {
    setAuth({ access_token: 'token-1', role: 'researcher' })
    expect(getToken()).toBe('token-1')
    expect(getRole()).toBe('researcher')
    expect(isAuthenticated()).toBe(true)
    expect(isAdmin()).toBe(false)
  })

  it('clears storage', () => {
    setAuth({ access_token: 'token-1', role: 'admin' })
    clearAuth()
    expect(getToken()).toBeNull()
    expect(getRole()).toBeNull()
  })
})
