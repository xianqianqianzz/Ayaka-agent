import { useState, type FormEvent } from 'react'
import { getToken } from '../lib/auth'

interface ChatModel {
  id: number
  name: string
  display_name: string
}

interface Message {
  role: 'user' | 'assistant'
  content: string
}

interface ChatState {
  messages: Message[]
  input: string
  loading: boolean
}

const emptyChat: ChatState = { messages: [], input: '', loading: false }

export default function ChatBox({ models }: { models: ChatModel[] }) {
  const [activeName, setActiveName] = useState('')
  const [chats, setChats] = useState<Record<string, ChatState>>({})

  const active = models.some((m) => m.name === activeName) ? activeName : (models[0]?.name ?? '')
  const state = chats[active] ?? emptyChat

  function patch(partial: Partial<ChatState>) {
    setChats((prev) => ({ ...prev, [active]: { ...(prev[active] ?? emptyChat), ...partial } }))
  }

  async function send(e: FormEvent) {
    e.preventDefault()
    const text = state.input.trim()
    if (!text || !active) return
    const history: Message[] = [...state.messages, { role: 'user', content: text }]
    patch({ messages: [...history, { role: 'assistant', content: '' }], input: '', loading: true })

    const assistantIdx = history.length
    let acc = ''
    try {
      const res = await fetch('/api/v1/chat/completions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${getToken()}` },
        body: JSON.stringify({
          model: active,
          messages: history.map((m) => ({ role: m.role, content: m.content })),
          stream: true,
        }),
      })
      if (!res.ok || !res.body) {
        throw new Error(await res.text() || `HTTP ${res.status}`)
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''
        for (const line of lines) {
          const trimmed = line.trim()
          if (!trimmed.startsWith('data:')) continue
          const data = trimmed.slice(5).trim()
          if (!data || data === '[DONE]') continue
          try {
            const json = JSON.parse(data)
            if (json.error) {
              acc += `\n[错误] ${json.error.message ?? JSON.stringify(json.error)}`
            } else {
              const delta = json.choices?.[0]?.delta?.content ?? ''
              if (delta) acc += delta
            }
          } catch {
            // 忽略无法解析的行
          }
        }
        setChats((prev) => {
          const cur = prev[active] ?? emptyChat
          const nextMessages = [...cur.messages]
          nextMessages[assistantIdx] = { role: 'assistant', content: acc }
          return { ...prev, [active]: { ...cur, messages: nextMessages } }
        })
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err)
      setChats((prev) => {
        const cur = prev[active] ?? emptyChat
        const nextMessages = [...cur.messages]
        nextMessages[assistantIdx] = { role: 'assistant', content: `[请求失败] ${msg}` }
        return { ...prev, [active]: { ...cur, messages: nextMessages } }
      })
    } finally {
      setChats((prev) => {
        const cur = prev[active] ?? emptyChat
        return { ...prev, [active]: { ...cur, loading: false } }
      })
    }
  }

  if (models.length === 0) {
    return (
      <section className="rounded-2xl bg-white/85 p-5 shadow backdrop-blur">
        <h2 className="mb-3 text-lg font-semibold text-ayaka-deep">测试对话</h2>
        <p className="text-sm text-slate-500">还没有 text-chat 能力的模型，请先在上方添加 Provider 与模型。</p>
      </section>
    )
  }

  return (
    <section className="rounded-2xl bg-white/85 p-5 shadow backdrop-blur">
      <h2 className="mb-3 text-lg font-semibold text-ayaka-deep">测试对话（每个模型独立窗口）</h2>

      <div className="mb-3 flex flex-wrap gap-2">
        {models.map((m) => (
          <button
            key={m.id}
            onClick={() => setActiveName(m.name)}
            className={`rounded-lg px-3 py-1.5 text-sm ${
              active === m.name ? 'bg-ayaka-deep text-white' : 'bg-slate-200 text-slate-600 hover:bg-slate-300'
            }`}
          >
            {m.display_name || m.name}
          </button>
        ))}
      </div>

      <div className="mb-3 max-h-80 space-y-2 overflow-y-auto rounded-lg bg-slate-50 p-3">
        {state.messages.map((m, i) => (
          <div key={i} className={m.role === 'user' ? 'text-right' : 'text-left'}>
            <span
              className={`inline-block max-w-[80%] whitespace-pre-wrap rounded-xl px-3 py-2 text-sm ${
                m.role === 'user' ? 'bg-ayaka-deep text-white' : 'bg-white text-slate-700 shadow-sm'
              }`}
            >
              {m.content || (state.loading && i === state.messages.length - 1 ? '…' : '')}
            </span>
          </div>
        ))}
        {state.messages.length === 0 && <p className="text-sm text-slate-400">发送一条消息开始测试。</p>}
      </div>

      <form onSubmit={send} className="flex gap-2">
        <input
          value={state.input}
          onChange={(e) => patch({ input: e.target.value })}
          placeholder={`给 ${active} 发消息…`}
          className="input flex-1"
          disabled={state.loading}
        />
        <button type="submit" disabled={state.loading || !state.input.trim()} className="btn-primary">
          发送
        </button>
      </form>
    </section>
  )
}
