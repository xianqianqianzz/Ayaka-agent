import { useEffect, useState } from 'react'

type Health = { status: string }

export default function App() {
  const [health, setHealth] = useState<Health | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetch('/api/v1/health')
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        return res.json() as Promise<Health>
      })
      .then(setHealth)
      .catch((err) => setError(String(err)))
  }, [])

  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-4 bg-gradient-to-b from-ayaka-ice to-ayaka-blue text-slate-800">
      <h1 className="text-3xl font-semibold tracking-wide text-white drop-shadow">神里绫华 · AI 平台</h1>
      <p className="text-sm text-white/80">下游优先 · 模型网关为骨架</p>
      <div className="rounded-full bg-white/70 px-4 py-2 shadow-sm backdrop-blur">
        {error ? (
          <span className="text-rose-500">后端未连接：{error}</span>
        ) : health ? (
          <span className="text-emerald-600">后端正常：{health.status}</span>
        ) : (
          <span className="text-slate-400">连接中…</span>
        )}
      </div>
    </main>
  )
}
