import { useState, useEffect, useRef } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkBreaks from 'remark-breaks'

function MoonIcon({ size = 22 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="#e6ca8a" aria-hidden="true">
      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
    </svg>
  )
}

const ICONS = {
  bazi: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
      <circle cx="12" cy="12" r="9" />
      <path d="M12 3a4.5 4.5 0 0 1 0 9a4.5 4.5 0 0 0 0 9" />
      <circle cx="12" cy="7.5" r="1.5" fill="currentColor" stroke="none" />
      <circle cx="12" cy="16.5" r="1.5" fill="currentColor" stroke="none" />
    </svg>
  ),
  ziwei: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M12 4l1.8 3.6 4 .6-2.9 2.8.7 4-3.6-1.9-3.6 1.9.7-4L6.2 8.2l4-.6z" strokeLinejoin="round" />
      <circle cx="19" cy="6" r="1.2" fill="currentColor" stroke="none" />
      <circle cx="5" cy="7" r="1" fill="currentColor" stroke="none" />
      <circle cx="18.5" cy="17" r="1" fill="currentColor" stroke="none" />
    </svg>
  ),
  xingzuo: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
      <circle cx="5" cy="8" r="1.3" fill="currentColor" stroke="none" />
      <circle cx="11" cy="5" r="1.3" fill="currentColor" stroke="none" />
      <circle cx="17" cy="9" r="1.3" fill="currentColor" stroke="none" />
      <circle cx="13" cy="16" r="1.3" fill="currentColor" stroke="none" />
      <circle cx="7" cy="18" r="1.3" fill="currentColor" stroke="none" />
      <path d="M5 8l6-3 6 4-4 7-6 2z" />
    </svg>
  ),
  fengshui: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
      <circle cx="12" cy="12" r="9" />
      <path d="M12 3v18M3 12h18" />
      <path d="M12 8l3 4-3 4-3-4z" strokeLinejoin="round" />
    </svg>
  ),
  mbti: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
      <rect x="4" y="4" width="7" height="7" rx="1.5" />
      <rect x="13" y="4" width="7" height="7" rx="1.5" />
      <rect x="4" y="13" width="7" height="7" rx="1.5" />
      <rect x="13" y="13" width="7" height="7" rx="1.5" />
    </svg>
  ),
  jiemeng: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M14 4a8 8 0 1 0 6 10 6 6 0 0 1-6-10z" strokeLinejoin="round" />
      <path d="M18 4.5l.5 1.5 1.5.5-1.5.5-.5 1.5-.5-1.5-1.5-.5 1.5-.5z" fill="currentColor" stroke="none" />
    </svg>
  ),
  taluo: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
      <rect x="5" y="3" width="14" height="18" rx="2" />
      <path d="M12 8l1.5 3 3 .4-2.2 2 .6 3.1L12 15l-2.9 1.5.6-3.1-2.2-2 3-.4z" strokeLinejoin="round" />
    </svg>
  ),
  zhouyi: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
      <path d="M6 6h12" />
      <path d="M6 12h5M13 12h5" />
      <path d="M6 18h12" />
    </svg>
  ),
}

const MODULES = [
  {
    id: 'taluo', name: '塔罗', sub: '塔罗牌阵 · 抽牌', desc: '抽一张牌，看看当下的指引', badge: '招牌',
    welcome: '你好呀，我是星语 ✨\n想占塔罗的话，告诉我你想问的事，我帮你抽牌解读。',
  },
  {
    id: 'bazi', name: '八字', sub: '排盘 · 五行 · 大运', desc: '输入出生年月日时，看命盘格局',
    welcome: '你好呀，我是星语 ✨\n想算八字的话，把出生年月日时和性别告诉我，我帮你排盘看看。',
  },
  {
    id: 'ziwei', name: '紫薇斗数', sub: '十二宫 · 星曜 · 流年', desc: '紫微星盘，解读你的人生剧本',
    welcome: '你好呀，我是星语 ✨\n想排紫微斗数的话，把你的出生年月日时告诉我，我帮你起盘。',
  },
  {
    id: 'xingzuo', name: '星座', sub: '星盘 · 每日运势', desc: '西方占星，看你的星座与运势',
    welcome: '你好呀，我是星语 ✨\n告诉我你的星座或出生日期，我陪你聊聊运势和星象。',
  },
  {
    id: 'fengshui', name: '风水', sub: '家居 · 办公 · 布局', desc: '风水常识与布局建议',
    welcome: '你好呀，我是星语 ✨\n家里、办公室的风水布局，或者想了解风水常识，都可以问我。',
  },
  {
    id: 'mbti', name: 'MBTI', sub: '16型人格 · 性格', desc: '了解你的性格特质',
    welcome: '你好呀，我是星语 ✨\n想了解自己的 MBTI 类型，我们从几个小问题开始，我陪你一起探索。',
  },
  {
    id: 'jiemeng', name: '解梦', sub: '梦境 · 潜意识', desc: '说说你的梦，一起看含义',
    welcome: '你好呀，我是星语 ✨\n做了什么梦都可以告诉我，我陪你一起看看它可能想说什么。',
  },
  {
    id: 'zhouyi', name: '周易', sub: '六爻起卦 · 卦象 · 变卦', desc: '摇一卦，看吉凶与指引',
    welcome: '你好呀，我是星语 ✨\n想算周易卦的话，把你想问的事告诉我，我帮你摇一卦、解一解。',
  },
]

function newSessionId() {
  return Math.random().toString(36).slice(2, 10) + Date.now().toString(36)
}

function formatTime(ts) {
  if (!ts) return ''
  const d = new Date(ts * 1000)
  const now = new Date()
  const pad = (n) => String(n).padStart(2, '0')
  const hm = `${pad(d.getHours())}:${pad(d.getMinutes())}`
  if (d.toDateString() === now.toDateString()) return `今天 ${hm}`
  const md = `${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
  return d.getFullYear() === now.getFullYear() ? `${md} ${hm}` : `${d.getFullYear()}-${md}`
}

export default function App() {
  const [view, setView] = useState('home')
  const [module, setModule] = useState(null)
  const [messages, setMessages] = useState([])
  const [sessions, setSessions] = useState([])
  const [activeSessionId, setActiveSessionId] = useState(null)
  const [status, setStatus] = useState('')
  const [busy, setBusy] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [loadingHistory, setLoadingHistory] = useState(false)
  const [input, setInput] = useState('')

  const sessionIdRef = useRef(newSessionId())
  const endRef = useRef(null)
  const nextIdRef = useRef(1)

  useEffect(() => { loadSessions() }, [])

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, status])

  async function loadSessions() {
    try {
      const r = await fetch('/sessions')
      const d = await r.json()
      setSessions(d.sessions || [])
    } catch (e) {
      /* 忽略 */
    }
  }

  function openModule(m) {
    sessionIdRef.current = newSessionId()
    setModule(m)
    setActiveSessionId(null)
    setStatus('')
    setMessages([{ id: nextIdRef.current++, role: 'assistant', content: m.welcome }])
    setView('chat')
    setSidebarOpen(false)
  }

  function newChat() {
    sessionIdRef.current = newSessionId()
    setModule(null)
    setActiveSessionId(null)
    setMessages([])
    setStatus('')
    setView('home')
    setSidebarOpen(false)
  }

  async function openHistory(s) {
    sessionIdRef.current = s.session_id
    setActiveSessionId(s.session_id)
    const mod = MODULES.find((m) => m.id === s.module) || MODULES[0]
    setModule(mod)
    setStatus('')
    setSidebarOpen(false)
    setView('chat')
    setLoadingHistory(true)
    try {
      const r = await fetch(`/sessions/${s.session_id}/messages`)
      const d = await r.json()
      const msgs = (d.messages || []).map((m) => ({ id: nextIdRef.current++, role: m.role, content: m.content }))
      setMessages(msgs)
    } catch (e) {
      setMessages([])
    } finally {
      setLoadingHistory(false)
    }
  }

  async function sendMessage() {
    const text = input.trim()
    if (!text || busy || !module) return
    setInput('')
    setStatus('')
    setBusy(true)
    setMessages((prev) => [...prev, { id: nextIdRef.current++, role: 'user', content: text }])
    const botId = nextIdRef.current++
    setMessages((prev) => [...prev, { id: botId, role: 'assistant', content: '', streaming: true }])

    const sid = sessionIdRef.current
    try {
      const res = await fetch('/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: text, session_id: sid, module: module.id }),
      })
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buf = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true })
        const lines = buf.split('\n')
        buf = lines.pop()
        for (const line of lines) {
          const s = line.trim()
          if (!s.startsWith('data:')) continue
          let ev
          try { ev = JSON.parse(s.slice(5).trim()) } catch { continue }
          if (ev.type === 'token') {
            setStatus('')
            setMessages((prev) => prev.map((m) => (m.id === botId ? { ...m, content: m.content + ev.content } : m)))
          } else if (ev.type === 'status') {
            setStatus(ev.text)
          } else if (ev.type === 'done') {
            sessionIdRef.current = ev.session_id
            setActiveSessionId(ev.session_id)
          }
        }
      }
    } catch (e) {
      setMessages((prev) => prev.map((m) => (m.id === botId ? { ...m, content: '抱歉，出错了，稍后再试试好吗？🌙', streaming: false } : m)))
    } finally {
      setMessages((prev) => prev.map((m) => (m.id === botId ? { ...m, streaming: false } : m)))
      setBusy(false)
      setStatus('')
      loadSessions()
    }
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  return (
    <div className="app">
      <div className="tarot-card">
        <span className="corner tl" /><span className="corner tr" />
        <span className="corner bl" /><span className="corner br" />

        <div className={`backdrop${sidebarOpen ? ' show' : ''}`} onClick={() => setSidebarOpen(false)} />

        <aside className={`sidebar${sidebarOpen ? ' open' : ''}`}>
          <div className="side-brand">
            <span className="emblem"><MoonIcon size={22} /></span>
            <span className="brand-name">星语</span>
          </div>
          <button className="new-chat" onClick={newChat}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M12 5v14M5 12h14" /></svg>
            新对话
          </button>
          <div className="side-label">最近对话</div>
          <div className="history">
            {sessions.map((s) => (
              <button
                key={s.session_id}
                className={`history-item${s.session_id === activeSessionId ? ' active' : ''}`}
                onClick={() => openHistory(s)}
              >
                <span className="t">{s.title}</span>
                <span className="time">{formatTime(s.updated_at)}</span>
              </button>
            ))}
          </div>
        </aside>

        <div className="main">
          {view === 'home' ? (
            <div className="view">
              <div className="mobile-bar">
                <button className="menu-btn" onClick={() => setSidebarOpen(true)} aria-label="历史记录">
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M3 6h18M3 12h18M3 18h18" /></svg>
                </button>
                <span className="brand-name">星语</span>
              </div>
              <div className="home-body">
                <div className="greet">今天想聊点什么？</div>
                <div className="greet-sub">选一个模块，我来陪你慢慢聊</div>
                <div className="grid">
                  {MODULES.map((m) => (
                    <button
                      key={m.id}
                      className={`module-card${m.featured ? ' featured' : ''}`}
                      onClick={() => openModule(m)}
                      aria-label={m.name}
                    >
                      <span className="ic">{ICONS[m.id]}</span>
                      <span className="meta">
                        <span className="name">{m.name}{m.badge ? <em className="tag">{m.badge}</em> : null}</span>
                        <span className="sub">{m.sub}</span>
                        <span className="desc">{m.desc}</span>
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <div className="view">
              <div className="header">
                <button className="menu-btn" onClick={() => setSidebarOpen(true)} aria-label="历史记录">
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M3 6h18M3 12h18M3 18h18" /></svg>
                </button>
                <button className="back-btn" onClick={newChat} aria-label="返回">
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M19 12H5M12 19l-7-7 7-7" /></svg>
                </button>
                <div className="header-text">
                  <h1>{module ? module.name : '星语'}</h1>
                  <p>{module ? module.sub : ''}</p>
                </div>
              </div>
              <div className="messages">
                {messages.map((m) =>
                  m.role === 'user' ? (
                    <div key={m.id} className="row user">
                      <div className="bubble">{m.content}</div>
                    </div>
                  ) : (
                    <div key={m.id} className="row bot">
                      <div className="who">
                        <span className="mini-moon"><MoonIcon size={24} /></span>
                        <div className="bubble">
                          <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks]}>
                            {m.content}
                          </ReactMarkdown>
                          {m.streaming && m.content && <span className="cursor" />}
                          {m.streaming && !m.content && (
                            <span className="typing"><span /><span /><span /></span>
                          )}
                        </div>
                      </div>
                    </div>
                  )
                )}
                {loadingHistory && <div className="status-line">正在加载历史消息…</div>}
                {!loadingHistory && status && <div className="status-line">{status}</div>}
                <div ref={endRef} />
              </div>
              <div className="hint">按 Enter 发送 · Shift + Enter 换行</div>
              <div className="input-bar">
                <textarea
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="输入你的问题…"
                  disabled={loadingHistory}
                />
                <button className="send-btn" onClick={sendMessage} disabled={busy || loadingHistory} aria-label="发送">
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#241738" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M22 2 11 13" /><path d="M22 2 15 22 11 13 2 9z" /></svg>
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
