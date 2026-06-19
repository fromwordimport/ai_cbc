import api from './api'
import { clearAuth, setAuth } from './token'
import type { LoginRequest, LoginResponse } from '@/types/api'

export const login = async (request: LoginRequest): Promise<LoginResponse> => {
  const { data } = await api.post('/auth/login', request)
  setAuth(data)
  return data
}

export const logout = (): void => {
  clearAuth()
  window.location.href = '/login'
}
