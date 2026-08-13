import { useCallback, useEffect, useState, type ChangeEvent, type FormEvent } from 'react'
import { api } from '../lib/api'
import { useAuth } from '../context/AuthContext'
import ChatBox from '../components/ChatBox'

interface Provider {
  id: number
  name: string
  kind: string
  base_url: string
  has_api_key: boolean
}

interface Model {
  id: number
  provider_id: number
  name: string
  display_name: string
  capability: string
}

interface FetchedModel {
  id: string
  capability: string
}

const KINDS = ['openai', 'deepseek', 'ollama', 'custom', 'self-hosted']
const CAPABILITIES = ['text-chat', 'embedding', 'tts', 'text-to-image', 'text-to-video', 'asr']

interface ProviderForm {
  id: number | null
  name: string
  kind: string
  base_url: string
  api_key: string
}

interface ModelForm {
  id: number | null
  provider_id: number
  name: string
  display_name: string
  capability: string
}

const emptyProviderForm: ProviderForm = { id: null, name: '', kind: 'deepseek', base_url: '', api_key: '' }
const emptyModelForm: ModelForm = { id: null, provider_id: 0, name: '', display_name: '', capability: 'text-chat' }

export default function Models() {
  const { user, logout } = useAuth()
  const [providers, setProviders] = useState<Provider[]>([])
  const [models, setModels] = useState<Model[]>([])
  const [error, setError] = useState<string | null>(null)
  const [pForm, setPForm] = useState<ProviderForm>(emptyProviderForm)
  const [mForm, setMForm] = useState<ModelForm>(emptyModelForm)
  const [fetchedModels, setFetchedModels] = useState<FetchedModel[]>([])
  const [selectedFetched, setSelectedFetched] = useState('')
  const [fetching, setFetching] = useState(false)

  const loadProviders = useCallback(async () => {
    setProviders(await api<Provider[]>('/api/v1/providers'))
  }, [])

  const loadModels = useCallback(async () => {
    setModels(await api<Model[]>('/api/v1/models'))
  }, [])

  useEffect(() => {
    loadProviders().catch((e) => setError(e instanceof Error ? e.message : String(e)))
    loadModels().catch((e) => setError(e instanceof Error ? e.message : String(e)))
  }, [loadProviders, loadModels])

  async function submitProvider(e: FormEvent) {
    e.preventDefault()
    setError(null)
    try {
      const body = {
        name: pForm.name,
        kind: pForm.kind,
        base_url: pForm.base_url,
        ...(pForm.api_key ? { api_key: pForm.api_key } : {}),
      }
      if (pForm.id) {
        await api(`/api/v1/providers/${pForm.id}`, { method: 'PUT', body: JSON.stringify(body) })
      } else {
        await api('/api/v1/providers', { method: 'POST', body: JSON.stringify(body) })
      }
      setPForm(emptyProviderForm)
      await loadProviders()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  async function removeProvider(id: number) {
    if (!confirm('删除该 Provider 会同时删除其下所有模型，确认？')) return
    await api(`/api/v1/providers/${id}`, { method: 'DELETE' })
    await Promise.all([loadProviders(), loadModels()])
  }

  function editProvider(p: Provider) {
    setPForm({ id: p.id, name: p.name, kind: p.kind, base_url: p.base_url, api_key: '' })
  }

  async function fetchModels() {
    if (!mForm.provider_id) return
    setError(null)
    setFetching(true)
    try {
      const list = await api<FetchedModel[]>(`/api/v1/providers/${mForm.provider_id}/models`)
      setFetchedModels(list)
      setSelectedFetched('')
    } catch (err) {
      setFetchedModels([])
      setSelectedFetched('')
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setFetching(false)
    }
  }

  function handleProviderChange(e: ChangeEvent<HTMLSelectElement>) {
    setMForm((prev) => ({ ...prev, provider_id: Number(e.target.value), name: '', display_name: '' }))
    setFetchedModels([])
    setSelectedFetched('')
  }

  function onPickFetched(e: ChangeEvent<HTMLSelectElement>) {
    const id = e.target.value
    setSelectedFetched(id)
    const item = fetchedModels.find((f) => f.id === id)
    if (item) {
      setMForm((prev) => ({ ...prev, name: item.id, display_name: item.id, capability: item.capability }))
    }
  }

  async function submitModel(e: FormEvent) {
    e.preventDefault()
    setError(null)
    try {
      const body = {
        provider_id: mForm.provider_id,
        name: mForm.name,
        display_name: mForm.display_name || mForm.name,
        capability: mForm.capability,
      }
      if (mForm.id) {
        await api(`/api/v1/models/${mForm.id}`, { method: 'PUT', body: JSON.stringify(body) })
      } else {
        await api('/api/v1/models', { method: 'POST', body: JSON.stringify(body) })
      }
      setMForm(emptyModelForm)
      setFetchedModels([])
      setSelectedFetched('')
      await loadModels()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  async function removeModel(id: number) {
    if (!confirm('确认删除该模型？')) return
    await api(`/api/v1/models/${id}`, { method: 'DELETE' })
    await loadModels()
  }

  function editModel(m: Model) {
    setMForm({ id: m.id, provider_id: m.provider_id, name: m.name, display_name: m.display_name, capability: m.capability })
    setFetchedModels([])
    setSelectedFetched('')
  }

  const providerName = (id: number) => providers.find((p) => p.id === id)?.name ?? `#${id}`

  return (
    <div className="min-h-screen bg-gradient-to-b from-ayaka-ice to-ayaka-blue">
      <header className="flex items-center justify-between px-6 py-4">
        <h1 className="text-2xl font-semibold text-white drop-shadow">神里绫华 · 模型网关</h1>
        <div className="flex items-center gap-3 text-sm text-white">
          <span>{user ? `你好，${user.username}` : ''}</span>
          <button onClick={logout} className="rounded-lg bg-white/20 px-3 py-1.5 hover:bg-white/30">
            退出
          </button>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-6 pb-12">
        {error && <div className="mb-4 rounded-lg bg-rose-100 px-4 py-2 text-sm text-rose-600">{error}</div>}

        <section className="mb-6 rounded-2xl bg-white/85 p-5 shadow backdrop-blur">
          <h2 className="mb-3 text-lg font-semibold text-ayaka-deep">Provider（模型服务商）</h2>
          <form onSubmit={submitProvider} className="mb-4 grid grid-cols-1 gap-2 sm:grid-cols-5">
            <input
              placeholder="名称，如 deepseek"
              value={pForm.name}
              onChange={(e) => setPForm({ ...pForm, name: e.target.value })}
              required
              className="input"
            />
            <select value={pForm.kind} onChange={(e) => setPForm({ ...pForm, kind: e.target.value })} className="input">
              {KINDS.map((k) => (
                <option key={k} value={k}>{k}</option>
              ))}
            </select>
            <input
              placeholder="Base URL，如 https://api.deepseek.com/v1"
              value={pForm.base_url}
              onChange={(e) => setPForm({ ...pForm, base_url: e.target.value })}
              required
              className="input sm:col-span-2"
            />
            <input
              type="password"
              placeholder="API Key（编辑时留空则不修改）"
              value={pForm.api_key}
              onChange={(e) => setPForm({ ...pForm, api_key: e.target.value })}
              className="input sm:col-span-2"
            />
            <div className="flex gap-2">
              <button type="submit" className="btn-primary flex-1">{pForm.id ? '保存' : '新增'}</button>
              {pForm.id && (
                <button type="button" onClick={() => setPForm(emptyProviderForm)} className="btn-secondary">
                  取消
                </button>
              )}
            </div>
          </form>

          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate-500">
                <th className="py-1">名称</th>
                <th>类型</th>
                <th>Base URL</th>
                <th>Key</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {providers.map((p) => (
                <tr key={p.id} className="border-t border-slate-200">
                  <td className="py-1.5 font-medium">{p.name}</td>
                  <td>{p.kind}</td>
                  <td className="max-w-xs truncate text-slate-500">{p.base_url}</td>
                  <td>{p.has_api_key ? '已配置' : '未配置'}</td>
                  <td className="text-right">
                    <button onClick={() => editProvider(p)} className="text-ayaka-deep hover:underline">编辑</button>
                    <button onClick={() => removeProvider(p.id)} className="ml-2 text-rose-500 hover:underline">删除</button>
                  </td>
                </tr>
              ))}
              {providers.length === 0 && (
                <tr><td colSpan={5} className="py-2 text-slate-400">暂无 Provider</td></tr>
              )}
            </tbody>
          </table>
        </section>

        <section className="mb-6 rounded-2xl bg-white/85 p-5 shadow backdrop-blur">
          <h2 className="mb-3 text-lg font-semibold text-ayaka-deep">模型</h2>
          <form onSubmit={submitModel} className="mb-4 space-y-2">
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-4">
              <select value={mForm.provider_id} onChange={handleProviderChange} required className="input">
                <option value={0} disabled>选择 Provider</option>
                {providers.map((p) => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </select>
              <button
                type="button"
                onClick={fetchModels}
                disabled={!mForm.provider_id || fetching}
                className="btn-secondary disabled:opacity-50"
              >
                {fetching ? '获取中…' : '获取模型'}
              </button>
              {fetchedModels.length > 0 && (
                <select value={selectedFetched} onChange={onPickFetched} className="input sm:col-span-2">
                  <option value="">从服务商选择模型标识</option>
                  {fetchedModels.map((f) => (
                    <option key={f.id} value={f.id}>{f.id}（{f.capability}）</option>
                  ))}
                </select>
              )}
            </div>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-5">
              <input
                placeholder="模型标识，如 deepseek-chat"
                value={mForm.name}
                onChange={(e) => setMForm({ ...mForm, name: e.target.value })}
                required
                className="input"
              />
              <input
                placeholder="显示名（可选）"
                value={mForm.display_name}
                onChange={(e) => setMForm({ ...mForm, display_name: e.target.value })}
                className="input"
              />
              <select value={mForm.capability} onChange={(e) => setMForm({ ...mForm, capability: e.target.value })} className="input">
                {CAPABILITIES.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
              <div className="flex gap-2 sm:col-span-2">
                <button type="submit" className="btn-primary flex-1">{mForm.id ? '保存' : '新增'}</button>
                {mForm.id && (
                  <button type="button" onClick={() => { setMForm(emptyModelForm); setFetchedModels([]); setSelectedFetched('') }} className="btn-secondary">
                    取消
                  </button>
                )}
              </div>
            </div>
          </form>

          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate-500">
                <th className="py-1">标识</th>
                <th>显示名</th>
                <th>Provider</th>
                <th>能力</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {models.map((m) => (
                <tr key={m.id} className="border-t border-slate-200">
                  <td className="py-1.5 font-medium">{m.name}</td>
                  <td>{m.display_name}</td>
                  <td>{providerName(m.provider_id)}</td>
                  <td>{m.capability}</td>
                  <td className="text-right">
                    <button onClick={() => editModel(m)} className="text-ayaka-deep hover:underline">编辑</button>
                    <button onClick={() => removeModel(m.id)} className="ml-2 text-rose-500 hover:underline">删除</button>
                  </td>
                </tr>
              ))}
              {models.length === 0 && (
                <tr><td colSpan={5} className="py-2 text-slate-400">暂无模型</td></tr>
              )}
            </tbody>
          </table>
        </section>

        <ChatBox models={models.filter((m) => m.capability === 'text-chat')} />
      </main>
    </div>
  )
}
