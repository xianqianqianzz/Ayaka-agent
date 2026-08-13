import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

export default function Login() {
  const { login, register } = useAuth()
  const navigate = useNavigate()
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      if (mode === 'login') await login(username, password)
      else await register(username, password)
      navigate('/', { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-gradient-to-b from-ayaka-ice to-ayaka-blue">
      <form onSubmit={onSubmit} className="w-80 rounded-2xl bg-white/90 p-6 shadow-lg backdrop-blur">
        <h1 className="mb-1 text-center text-2xl font-semibold text-ayaka-deep">神里绫华 · AI 平台</h1>
        <p className="mb-4 text-center text-sm text-slate-500">{mode === 'login' ? '登录' : '注册'}</p>

        <label className="mb-1 block text-sm text-slate-600">用户名</label>
        <input
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          required
          minLength={3}
          className="mb-3 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-ayaka-blue focus:outline-none"
        />

        <label className="mb-1 block text-sm text-slate-600">密码</label>
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
          minLength={6}
          className="mb-3 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-ayaka-blue focus:outline-none"
        />

        {error && <p className="mb-2 text-sm text-rose-500">{error}</p>}

        <button
          disabled={loading}
          className="w-full rounded-lg bg-ayaka-deep py-2 text-white hover:bg-ayaka-blue disabled:opacity-50"
        >
          {loading ? '处理中…' : mode === 'login' ? '登录' : '注册'}
        </button>

        <button
          type="button"
          onClick={() => setMode(mode === 'login' ? 'register' : 'login')}
          className="mt-3 w-full text-center text-sm text-ayaka-deep hover:underline"
        >
          {mode === 'login' ? '没有账号？去注册' : '已有账号？去登录'}
        </button>
      </form>
    </main>
  )
}
