const TOKEN_KEY = 'aicbc_token'
const ROLE_KEY = 'aicbc_role'

export const setAuth = (response: { access_token: string; role: string }): void => {
  localStorage.setItem(TOKEN_KEY, response.access_token)
  localStorage.setItem(ROLE_KEY, response.role)
}

export const clearAuth = (): void => {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(ROLE_KEY)
}

export const getToken = (): string | null => {
  return localStorage.getItem(TOKEN_KEY)
}

export const getRole = (): 'researcher' | 'admin' | null => {
  const role = localStorage.getItem(ROLE_KEY)
  if (role === 'researcher' || role === 'admin') {
    return role
  }
  return null
}

export const isAuthenticated = (): boolean => {
  return !!getToken()
}

export const isAdmin = (): boolean => {
  return getRole() === 'admin'
}
