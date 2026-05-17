import { useEffect, useMemo, useState } from 'react'
import { apiRequest, toErrorMessage } from '../api/client'
import { ENDPOINTS } from '../config'

type ChatMessageKind = 'system' | 'command' | 'response' | 'error'

interface ChatMessage {
  id: string
  kind: ChatMessageKind
  text: string
  at: number
}

interface ChatPanelProps {
  currentPath: string
  currentPageLabel: string
}

const QUICK_COMMANDS = ['/status', '/agents', '/queue'] as const

export default function ChatPanel({ currentPath, currentPageLabel }: ChatPanelProps) {
  const [expanded, setExpanded] = useState(false)
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [messages, setMessages] = useState<ChatMessage[]>(() => [
    {
      id: `m-${Date.now()}`,
      kind: 'system',
      text: 'Quick actions only: /status /agents /queue',
      at: Date.now(),
    },
  ])

  const contextHint = useMemo(() => {
    if (currentPath === '/agents') return 'Context: monitor active agents and process state.'
    if (currentPath === '/migration') return 'Context: submit migration tasks and monitor queue.'
    if (currentPath === '/simulation') return 'Context: run simulation scenarios and review findings.'
    if (currentPath === '/patches') return 'Context: inspect patch details and evidence.'
    if (currentPath === '/approvals' || currentPath === '/approval') {
      return 'Context: process approval actions and review queues.'
    }
    return `Context: ${currentPageLabel}`
  }, [currentPageLabel, currentPath])

  useEffect(() => {
    pushMessage('system', contextHint)
  }, [contextHint])

  function pushMessage(kind: ChatMessageKind, text: string) {
    setMessages((prev) => {
      const next: ChatMessage = {
        id: `m-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`,
        kind,
        text,
        at: Date.now(),
      }
      return [...prev.slice(-49), next]
    })
  }

  async function runQuickCommand(raw: string) {
    const cmd = raw.trim()
    if (!cmd) {
      return
    }

    pushMessage('command', cmd)
    setBusy(true)
    try {
      if (cmd === '/status') {
        const data = await apiRequest<{ status: string; uptime_seconds?: number }>(ENDPOINTS.health, undefined, {
          includeAuth: false,
        })
        pushMessage('response', `core=${data.status} uptime=${Math.round(data.uptime_seconds || 0)}s`)
      } else if (cmd === '/agents') {
        const data = await apiRequest<{ count: number }>(`${ENDPOINTS.agents}/running`)
        pushMessage('response', `running_agents=${data.count}`)
      } else if (cmd === '/queue') {
        const data = await apiRequest<{
          P0_critical: number
          P1_normal: number
          P2_background: number
          running: number
        }>(`${ENDPOINTS.tasks}/queue/stats`)
        pushMessage(
          'response',
          `queue P0=${data.P0_critical} P1=${data.P1_normal} P2=${data.P2_background} running=${data.running}`,
        )
      } else {
        pushMessage('error', 'Unsupported command. Use /status /agents /queue')
      }
    } catch (error) {
      pushMessage('error', toErrorMessage(error))
    } finally {
      setBusy(false)
    }
  }

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const cmd = input
    setInput('')
    await runQuickCommand(cmd)
  }

  return (
    <aside style={panelWrapStyle}>
      <div style={panelStyle(expanded)}>
        <button
          type="button"
          style={headerButtonStyle}
          onClick={() => setExpanded((prev) => !prev)}
          aria-label={expanded ? 'Collapse quick panel' : 'Expand quick panel'}
        >
          <span style={{ fontWeight: 700 }}>Quick Panel</span>
          <span style={{ fontSize: '0.75rem', color: '#cbd5e1' }}>
            {expanded ? 'Collapse' : 'Expand'}
          </span>
        </button>

        {expanded ? (
          <>
            <div style={messagesWrapStyle}>
              {messages.map((message) => (
                <div key={message.id} style={messageRowStyle(message.kind)}>
                  <div style={{ fontSize: '0.68rem', color: '#64748b' }}>{new Date(message.at).toLocaleTimeString()}</div>
                  <div>{message.text}</div>
                </div>
              ))}
            </div>

            <div style={quickCommandBarStyle}>
              {QUICK_COMMANDS.map((cmd) => (
                <button key={cmd} type="button" style={quickButtonStyle} disabled={busy} onClick={() => void runQuickCommand(cmd)}>
                  {cmd}
                </button>
              ))}
            </div>

            <form onSubmit={onSubmit} style={inputBarStyle}>
              <input
                value={input}
                onChange={(event) => setInput(event.target.value)}
                placeholder="Enter /status, /agents, or /queue"
                style={inputStyle}
              />
              <button type="submit" style={sendButtonStyle} disabled={busy || !input.trim()}>
                {busy ? '...' : 'Run'}
              </button>
            </form>
          </>
        ) : null}
      </div>
    </aside>
  )
}

const panelWrapStyle: React.CSSProperties = {
  position: 'fixed',
  right: '1rem',
  bottom: '1rem',
  zIndex: 30,
}

function panelStyle(expanded: boolean): React.CSSProperties {
  return {
    width: '320px',
    height: expanded ? '400px' : '48px',
    borderRadius: '10px',
    border: '1px solid #334155',
    background: '#0f172a',
    color: '#e2e8f0',
    display: 'grid',
    gridTemplateRows: expanded ? '48px 1fr auto auto' : '48px',
    boxShadow: '0 10px 30px rgba(2, 6, 23, 0.4)',
    overflow: 'hidden',
  }
}

const headerButtonStyle: React.CSSProperties = {
  width: '100%',
  border: 0,
  background: '#111827',
  color: '#e2e8f0',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  padding: '0.5rem 0.7rem',
  cursor: 'pointer',
}

const messagesWrapStyle: React.CSSProperties = {
  padding: '0.5rem',
  overflowY: 'auto',
  display: 'grid',
  gap: '0.35rem',
  background: '#0b1220',
}

function messageRowStyle(kind: ChatMessageKind): React.CSSProperties {
  const border = kind === 'error' ? '#dc2626' : kind === 'command' ? '#2563eb' : '#334155'
  return {
    border: `1px solid ${border}`,
    borderRadius: '6px',
    padding: '0.35rem 0.45rem',
    fontSize: '0.76rem',
    lineHeight: 1.35,
    background: '#0f172a',
  }
}

const quickCommandBarStyle: React.CSSProperties = {
  display: 'flex',
  gap: '0.4rem',
  padding: '0.45rem 0.5rem',
  borderTop: '1px solid #334155',
}

const quickButtonStyle: React.CSSProperties = {
  border: '1px solid #475569',
  borderRadius: '6px',
  background: '#1e293b',
  color: '#e2e8f0',
  padding: '0.28rem 0.5rem',
  fontSize: '0.74rem',
  cursor: 'pointer',
}

const inputBarStyle: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: '1fr auto',
  gap: '0.45rem',
  padding: '0.5rem',
  borderTop: '1px solid #334155',
}

const inputStyle: React.CSSProperties = {
  border: '1px solid #475569',
  borderRadius: '6px',
  background: '#111827',
  color: '#e2e8f0',
  padding: '0.36rem 0.5rem',
  fontSize: '0.78rem',
}

const sendButtonStyle: React.CSSProperties = {
  border: '1px solid #475569',
  borderRadius: '6px',
  background: '#334155',
  color: '#e2e8f0',
  padding: '0.34rem 0.55rem',
  fontSize: '0.76rem',
  cursor: 'pointer',
}
