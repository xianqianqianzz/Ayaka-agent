import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { api } from '../lib/api'
import { clearToken, getToken, setToken } from '../lib/auth'

interface User {
  id: number
  username: string
}

interface AuthContextValue {
  user: User | null
  token: string | null
  login: (username: string, password: string) => Promise<void>
  register: (username: string, password: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setTokenState] = useState<string | null>(getToken())
  const [user, setUser] = useState<User | null>(null)

  useEffect(() => {
    if (!token || user) return
    api<User>('/api/v1/auth/me')
      .then(setUser)
      .catch(() => {
        clearToken()
        setTokenState(null)
      })
  }, [token, user])

  async function login(username: string, password: string) {
    const res = await api<{ access_token: string }>('/api/v1/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    })
    setToken(res.access_token)
    setTokenState(res.access_token)
    setUser(await api<User>('/api/v1/auth/me'))
  }

  async function register(username: string, password: string) {
    const res = await api<{ access_token: string }>('/api/v1/auth/register', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    })
    setToken(res.access_token)
    setTokenState(res.access_token)
    setUser(await api<User>('/api/v1/auth/me'))
  }

  function logout() {
    clearToken()
    setTokenState(null)
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, token, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth 必须在 AuthProvider 内使用')
  return ctx
}
