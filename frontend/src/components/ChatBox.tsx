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

export default function ChatBox({ models }: { models: ChatModel[] }) {
  const [model, setModel] = useState('')
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)

  async function send(e: FormEvent) {
    e.preventDefault()
    const text = input.trim()
    const target = model || models[0]?.name
    if (!text || !target) return

    const history: Message[] = [...messages, { role: 'user', content: text }]
    setMessages([...history, { role: 'assistant', content: '' }])
    setInput('')
    setLoading(true)

    const assistantIdx = history.length
    let acc = ''
    try {
      const res = await fetch('/api/v1/chat/completions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${getToken()}` },
        body: JSON.stringify({
          model: target,
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
        setMessages((prev) => {
          const next = [...prev]
          next[assistantIdx] = { role: 'assistant', content: acc }
          return next
        })
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err)
      setMessages((prev) => {
        const next = [...prev]
        next[assistantIdx] = { role: 'assistant', content: `[请求失败] ${msg}` }
        return next
      })
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="rounded-2xl bg-white/85 p-5 shadow backdrop-blur">
      <h2 className="mb-3 text-lg font-semibold text-ayaka-deep">测试对话</h2>
      {models.length === 0 ? (
        <p className="text-sm text-slate-500">
          还没有 text-chat 能力的模型，请先在上方添加 Provider 与模型。
        </p>
      ) : (
        <>
          <div className="mb-3 flex items-center gap-2">
            <label className="text-sm text-slate-600">模型：</label>
            <select value={model || models[0]?.name} onChange={(e) => setModel(e.target.value)} className="input">
              {models.map((m) => (
                <option key={m.id} value={m.name}>{m.display_name || m.name}</option>
              ))}
            </select>
          </div>

          <div className="mb-3 max-h-80 space-y-2 overflow-y-auto rounded-lg bg-slate-50 p-3">
            {messages.map((m, i) => (
              <div key={i} className={m.role === 'user' ? 'text-right' : 'text-left'}>
                <span
                  className={`inline-block max-w-[80%] whitespace-pre-wrap rounded-xl px-3 py-2 text-sm ${
                    m.role === 'user' ? 'bg-ayaka-deep text-white' : 'bg-white text-slate-700 shadow-sm'
                  }`}
                >
                  {m.content || (loading && i === messages.length - 1 ? '…' : '')}
                </span>
              </div>
            ))}
            {messages.length === 0 && <p className="text-sm text-slate-400">发送一条消息开始测试。</p>}
          </div>

          <form onSubmit={send} className="flex gap-2">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="输入消息…"
              className="input flex-1"
              disabled={loading}
            />
            <button type="submit" disabled={loading || !input.trim()} className="btn-primary">
              发送
            </button>
          </form>
        </>
      )}
    </section>
  )
}
