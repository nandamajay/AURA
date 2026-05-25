import { useEffect, useMemo, useRef, useState, type CSSProperties } from 'react'
import { apiRequest, toErrorMessage } from '../api/client'
import { API_ROUTES, wsUrlWithToken } from '../config'
import { useApiData } from '../hooks/useApiData'
import { useAuthStore } from '../store/useAuthStore'
import { Grid, JsonBlock, MetaText, PageContainer, PageHeader, SectionCard } from '../components/PagePrimitives'

interface AgentCatalog {
  agent_types: string[]
}

interface RunningAgent {
  agent_id: string
  task_id: string
  agent_type: string
  requested_by: string
  pid: number
  status: string
  progress_percent: number
  last_message: string
  output_dir?: string
  created_at: number
  runtime_seconds: number
}

interface RunningAgentsResponse {
  agents: RunningAgent[]
  count: number
}

interface WatchdogState {
  agent_id: string
  task_id: string
  agent_type: string
  status: string
  memory_mb: number
  cpu_percent: number
  lifetime_seconds: number
}

interface WatchdogResponse {
  count: number
  max_watches: number
  states: Record<string, WatchdogState>
}

interface RuntimeOverviewDomainStats {
  dispatches: number
  starvation_events: number
  fairness_overrides: number
  last_queue_wait_ms: number
}

interface RuntimeOverview {
  queue_isolation?: {
    per_domain?: Record<string, RuntimeOverviewDomainStats>
  }
  tasks?: {
    domain_activity?: Record<
      string,
      {
        total: number
        running: number
        queued: number
        failed: number
        completed: number
      }
    >
    retry_pressure?: {
      retry_pending_tasks: number
      tasks_with_retry_lineage: number
    }
  }
  websocket?: {
    available?: boolean
    payload?: {
      event_buffer_size?: number
      event_buffer_capacity?: number
      buffer_evictions_total?: number
      sse_drop_total?: number
      domain_ingest_count?: Record<string, number>
      domain_ws_delivery_count?: Record<string, number>
      domain_sse_delivery_count?: Record<string, number>
    }
    error?: string
  }
  pressure_alerts?: Array<{
    severity: string
    surface: string
    message: string
  }>
}

type AgentCardStatus = 'running' | 'queued' | 'completed' | 'failed' | 'timeout'

interface AgentCard {
  agentId: string
  taskId: string
  agentType: string
  status: AgentCardStatus
  progress: number
  cpuPercent: number
  memoryMb: number
  durationSeconds: number
  createdAt: number
  lastMessage: string
  outputDir: string
  updatedAt: number
}

interface StreamEvent {
  id: string
  eventType: string
  timestamp: string
  source: {
    agentId: string
    taskId: string
    agentType: string
  }
  payload: Record<string, unknown>
}

const WS_CHANNELS = ['agent.lifecycle', 'task.orchestration', 'system']
const STATUS_COLORS: Record<AgentCardStatus, string> = {
  running: '#22c55e',
  queued: '#9ca3af',
  completed: '#3b82f6',
  failed: '#ef4444',
  timeout: '#f59e0b',
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function asString(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : fallback
}

function asNumber(value: unknown, fallback = 0): number {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value
  }
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

function clampProgress(value: number): number {
  if (!Number.isFinite(value)) {
    return 0
  }
  return Math.max(0, Math.min(100, Math.round(value)))
}

function toCardStatus(raw: string): AgentCardStatus {
  if (raw === 'running') {
    return 'running'
  }
  if (raw === 'queued' || raw === 'pending') {
    return 'queued'
  }
  if (raw === 'completed' || raw === 'success') {
    return 'completed'
  }
  if (raw === 'timeout') {
    return 'timeout'
  }
  return 'failed'
}

export default function LiveAgentObservability() {
  const { token } = useAuthStore()
  const [agentType, setAgentType] = useState('learning')
  const [spawnResult, setSpawnResult] = useState<unknown>(null)
  const [spawnError, setSpawnError] = useState('')
  const [spawning, setSpawning] = useState(false)
  const [controlError, setControlError] = useState('')

  const [wsConnected, setWsConnected] = useState(false)
  const [wsError, setWsError] = useState('')
  const [events, setEvents] = useState<StreamEvent[]>([])
  const [agentCards, setAgentCards] = useState<Record<string, AgentCard>>({})
  const [focusedAgentId, setFocusedAgentId] = useState('')
  const wsRef = useRef<WebSocket | null>(null)

  const { data: catalog } = useApiData<AgentCatalog>(API_ROUTES.agents.root(), { intervalMs: 20_000 })
  const { data: running, reload: reloadRunning } = useApiData<RunningAgentsResponse>(API_ROUTES.agents.running())
  const { data: watchdog, reload: reloadWatchdog } = useApiData<WatchdogResponse>(API_ROUTES.agents.watchdog())
  const { data: breakers, reload: reloadBreakers } = useApiData(API_ROUTES.agents.circuitBreakers())
  const { data: runtimeOverview, reload: reloadRuntimeOverview } = useApiData<RuntimeOverview>(API_ROUTES.runtimeOverview(), {
    intervalMs: 12_000,
  })

  const options = useMemo(() => {
    return catalog?.agent_types?.length ? catalog.agent_types : ['learning', 'validation', 'refactor']
  }, [catalog])

  const orderedCards = useMemo(() => {
    return Object.values(agentCards).sort((a, b) => b.updatedAt - a.updatedAt)
  }, [agentCards])

  const focusedEvents = useMemo(() => {
    if (!focusedAgentId) {
      return []
    }
    return events.filter((event) => event.source.agentId === focusedAgentId).slice(0, 15)
  }, [events, focusedAgentId])

  const domainRows = useMemo(() => {
    const domainActivity = runtimeOverview?.tasks?.domain_activity || {}
    const isolation = runtimeOverview?.queue_isolation?.per_domain || {}
    const domains = Array.from(new Set([...Object.keys(domainActivity), ...Object.keys(isolation)])).sort()
    return domains.map((domain) => ({
      domain,
      activity: domainActivity[domain],
      isolation: isolation[domain],
    }))
  }, [runtimeOverview])

  const wsEndpoint = useMemo(() => wsUrlWithToken(token), [token])

  useEffect(() => {
    if (!running && !watchdog) {
      return
    }

    setAgentCards((prev) => {
      const now = Date.now()
      const nowSeconds = Math.floor(now / 1000)
      const next: Record<string, AgentCard> = { ...prev }

      for (const agent of running?.agents ?? []) {
        const existing = next[agent.agent_id]
        const createdAt = asNumber(agent.created_at, existing?.createdAt ?? nowSeconds)
        next[agent.agent_id] = {
          agentId: agent.agent_id,
          taskId: agent.task_id,
          agentType: agent.agent_type,
          status: toCardStatus(agent.status),
          progress: clampProgress(asNumber(agent.progress_percent, existing?.progress ?? 0)),
          cpuPercent: existing?.cpuPercent ?? 0,
          memoryMb: existing?.memoryMb ?? 0,
          durationSeconds: Math.max(existing?.durationSeconds ?? 0, asNumber(agent.runtime_seconds, 0)),
          createdAt,
          lastMessage: asString(agent.last_message, existing?.lastMessage ?? ''),
          outputDir: asString(agent.output_dir, existing?.outputDir ?? ''),
          updatedAt: now,
        }
      }

      for (const state of Object.values(watchdog?.states ?? {})) {
        const existing = next[state.agent_id]
        const createdAt = existing?.createdAt ?? nowSeconds - Math.round(asNumber(state.lifetime_seconds, 0))
        next[state.agent_id] = {
          agentId: state.agent_id,
          taskId: state.task_id || existing?.taskId || '',
          agentType: state.agent_type || existing?.agentType || 'unknown',
          status: toCardStatus(state.status || existing?.status || 'running'),
          progress: existing?.progress ?? 0,
          cpuPercent: Math.round(asNumber(state.cpu_percent, existing?.cpuPercent ?? 0)),
          memoryMb: Math.round(asNumber(state.memory_mb, existing?.memoryMb ?? 0)),
          durationSeconds: Math.max(asNumber(state.lifetime_seconds, 0), existing?.durationSeconds ?? 0),
          createdAt,
          lastMessage: existing?.lastMessage ?? '',
          outputDir: existing?.outputDir ?? '',
          updatedAt: now,
        }
      }
      return next
    })
  }, [running, watchdog])

  useEffect(() => {
    const ws = new WebSocket(wsEndpoint)
    wsRef.current = ws

    ws.onopen = () => {
      setWsConnected(true)
      setWsError('')
      ws.send(
        JSON.stringify({
          action: 'subscribe',
          channels: WS_CHANNELS,
          auth: token ? { type: 'bearer', token } : undefined,
        }),
      )
    }

    ws.onmessage = (message) => {
      try {
        const data = JSON.parse(message.data as string)
        if (data.action) {
          return
        }

        const payload = isRecord(data.payload) ? data.payload : {}
        const source = isRecord(data.source) ? data.source : {}
        const sourceAgentId = asString(source.agent_id)
        const sourceTaskId = asString(source.task_id)
        const sourceAgentType = asString(source.agent_type)

        const event: StreamEvent = {
          id: data.event_id || `${Date.now()}-${Math.random().toString(16).slice(2)}`,
          eventType: data.event_type || 'unknown',
          timestamp: data.timestamp || new Date().toISOString(),
          source: {
            agentId: sourceAgentId,
            taskId: sourceTaskId,
            agentType: sourceAgentType,
          },
          payload,
        }

        setEvents((prev) => [event, ...prev].slice(0, 50))

        const agentId = sourceAgentId || asString(payload.agent_id)
        if (!agentId) {
          return
        }

        const eventType = asString(data.event_type)
        const nextStatusFromPayload = asString(payload.status)
        const progressFromPayload = clampProgress(asNumber(payload.progress_percent, 0))
        const memoryFromPayload = Math.round(asNumber(payload.memory_mb, 0))
        const cpuFromPayload = Math.round(asNumber(payload.cpu_percent, 0))
        const messageFromPayload = asString(payload.message)

        setAgentCards((prev) => {
          const now = Date.now()
          const nowSeconds = Math.floor(now / 1000)
          const existing = prev[agentId]
          const base: AgentCard = existing ?? {
            agentId,
            taskId: sourceTaskId || asString(payload.task_id),
            agentType: sourceAgentType || asString(payload.agent_type, 'unknown'),
            status: 'queued',
            progress: 0,
            cpuPercent: 0,
            memoryMb: 0,
            durationSeconds: 0,
            createdAt: nowSeconds,
            lastMessage: '',
            outputDir: '',
            updatedAt: now,
          }

          const next: AgentCard = {
            ...base,
            taskId: sourceTaskId || asString(payload.task_id, base.taskId),
            agentType: sourceAgentType || asString(payload.agent_type, base.agentType),
            updatedAt: now,
          }

          if (eventType === 'agent.registered' || eventType === 'agent.spawned' || eventType === 'task.started') {
            next.status = 'running'
            next.progress = Math.max(next.progress, 1)
          } else if (eventType === 'task.queued') {
            next.status = 'queued'
          } else if (eventType === 'task.progress') {
            next.status = 'running'
            next.progress = progressFromPayload || next.progress
            next.lastMessage = messageFromPayload || next.lastMessage
          } else if (eventType === 'agent.heartbeat') {
            next.status = 'running'
            next.cpuPercent = cpuFromPayload || next.cpuPercent
            next.memoryMb = memoryFromPayload || next.memoryMb
          } else if (eventType === 'agent.completed' || eventType === 'task.completed') {
            next.status = 'completed'
            next.progress = 100
            next.lastMessage = 'Completed'
          } else if (eventType === 'agent.timeout') {
            next.status = 'timeout'
            next.lastMessage = 'Timed out by watchdog'
          } else if (
            eventType === 'agent.failed' ||
            eventType === 'agent.killed' ||
            eventType === 'task.cancelled'
          ) {
            next.status = 'failed'
            next.lastMessage = asString(payload.error, next.lastMessage || 'Execution failed')
          } else if (nextStatusFromPayload) {
            next.status = toCardStatus(nextStatusFromPayload)
          }

          if (next.progress > 0) {
            next.durationSeconds = Math.max(
              next.durationSeconds,
              Math.max(0, nowSeconds - next.createdAt),
            )
          }

          return { ...prev, [agentId]: next }
        })
      } catch {
        // ignore malformed messages
      }
    }

    ws.onerror = () => {
      setWsError('WebSocket error. Live stream unavailable.')
    }

    ws.onclose = (event) => {
      setWsConnected(false)
      if (!event.wasClean) {
        setWsError(`WebSocket closed (${event.code}).`)
      }
    }

    return () => {
      ws.close()
    }
  }, [token, wsEndpoint])

  async function refreshSnapshots() {
    await Promise.all([reloadRunning(), reloadWatchdog(), reloadBreakers(), reloadRuntimeOverview()])
  }

  async function spawn() {
    setSpawnError('')
    setSpawnResult(null)
    setControlError('')
    setSpawning(true)

    try {
      const result = await apiRequest(API_ROUTES.agents.spawn(agentType), {
        method: 'POST',
      })
      setSpawnResult(result)
    } catch (error) {
      setSpawnError(toErrorMessage(error))
    } finally {
      setSpawning(false)
    }
  }

  async function killAgent(agentId: string) {
    setControlError('')
    try {
      await apiRequest(API_ROUTES.agents.byId(agentId), { method: 'DELETE' })
      setAgentCards((prev) => {
        const existing = prev[agentId]
        if (!existing) {
          return prev
        }
        return {
          ...prev,
          [agentId]: {
            ...existing,
            status: 'failed',
            lastMessage: 'Killed by operator',
            updatedAt: Date.now(),
          },
        }
      })
    } catch (error) {
      setControlError(toErrorMessage(error))
    }
  }

  return (
    <PageContainer>
      <PageHeader
        title="Live Agent Observability"
        subtitle="Live agent grid with WebSocket lifecycle updates, resource usage, and operator controls."
      />

      <Grid>
        <SectionCard title="Spawn Agent">
          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
            <select value={agentType} onChange={(e) => setAgentType(e.target.value)} style={inputStyle}>
              {options.map((option) => (
                <option value={option} key={option}>
                  {option}
                </option>
              ))}
            </select>
            <button onClick={() => void spawn()} style={buttonStyle} disabled={spawning}>
              {spawning ? 'Spawning...' : 'Spawn'}
            </button>
            <button onClick={() => void refreshSnapshots()} style={buttonStyle}>
              Refresh Snapshot
            </button>
          </div>
          <div style={{ marginTop: '0.75rem' }}>
            {spawnError ? <MetaText>{spawnError}</MetaText> : null}
            {controlError ? <MetaText>{controlError}</MetaText> : null}
            {spawnResult ? <JsonBlock data={spawnResult} /> : null}
          </div>
        </SectionCard>

        <SectionCard title="Stream Status">
          <MetaText>Socket: {wsConnected ? 'connected' : 'disconnected'}</MetaText>
          <MetaText>URL: {wsEndpoint}</MetaText>
          <MetaText>auth_token_attached={token ? 'true' : 'false'}</MetaText>
          <MetaText>Channels: {WS_CHANNELS.join(', ')}</MetaText>
          {wsError ? <MetaText>{wsError}</MetaText> : null}
        </SectionCard>
      </Grid>

      <div style={{ marginTop: '1rem' }}>
        <SectionCard
          title="Agent Grid"
          action={<MetaText>{orderedCards.length} tracked</MetaText>}
        >
          {orderedCards.length === 0 ? (
            <MetaText>No active agents yet. Spawn an agent or submit a task to populate live cards.</MetaText>
          ) : (
            <div style={agentGridStyle}>
              {orderedCards.map((card) => {
                const warning = card.status === 'running' && (card.cpuPercent >= 80 || card.memoryMb >= 1024)
                const accent = warning ? '#f59e0b' : STATUS_COLORS[card.status]
                const runtime = Math.max(card.durationSeconds, Math.floor(Date.now() / 1000) - card.createdAt)

                return (
                  <article
                    key={card.agentId}
                    style={{
                      ...agentCardStyle,
                      borderColor: accent,
                      boxShadow: focusedAgentId === card.agentId ? `0 0 0 2px ${accent}33` : 'none',
                    }}
                  >
                    <header style={{ display: 'flex', justifyContent: 'space-between', gap: '0.5rem' }}>
                      <strong style={{ fontSize: '0.84rem' }}>{card.agentId}</strong>
                      <span style={statusPillStyle(card.status, warning)}>{warning ? 'warning' : card.status}</span>
                    </header>

                    <MetaText>{card.agentType}</MetaText>

                    <div style={{ marginTop: '0.5rem' }}>
                      <div style={progressTrackStyle}>
                        <div style={progressFillStyle(card.progress, accent)} />
                      </div>
                      <MetaText>{card.progress}% complete</MetaText>
                    </div>

                    <div style={{ marginTop: '0.45rem', display: 'grid', gap: '0.2rem' }}>
                      <MetaText>CPU: {card.cpuPercent}%</MetaText>
                      <MetaText>MEM: {card.memoryMb} MB</MetaText>
                      <MetaText>Time: {runtime}s</MetaText>
                      {card.lastMessage ? <MetaText>Info: {card.lastMessage}</MetaText> : null}
                    </div>

                    <div style={{ marginTop: '0.6rem', display: 'flex', gap: '0.4rem', flexWrap: 'wrap' }}>
                      {card.status === 'running' ? (
                        <button style={dangerButtonStyle} onClick={() => void killAgent(card.agentId)}>
                          Kill
                        </button>
                      ) : null}
                      <button style={secondaryButtonStyle} onClick={() => setFocusedAgentId(card.agentId)}>
                        {card.status === 'running' ? 'Log' : 'Output'}
                      </button>
                    </div>
                  </article>
                )
              })}
            </div>
          )}
        </SectionCard>
      </div>

      <div style={{ marginTop: '1rem' }}>
        <Grid>
          <SectionCard title="Focused Agent">
            {focusedAgentId && agentCards[focusedAgentId] ? (
              <JsonBlock data={agentCards[focusedAgentId]} />
            ) : (
              <MetaText>Select Log/Output on an agent card to inspect details.</MetaText>
            )}
          </SectionCard>
          <SectionCard title="Circuit Breakers">
            <JsonBlock data={breakers || {}} />
          </SectionCard>
        </Grid>
      </div>

      <div style={{ marginTop: '1rem' }}>
        <Grid>
          <SectionCard title="Runtime Pressure Surface">
            <MetaText>
              retry_pending={runtimeOverview?.tasks?.retry_pressure?.retry_pending_tasks || 0} | replay_buffer=
              {runtimeOverview?.websocket?.payload?.event_buffer_size || 0}/
              {runtimeOverview?.websocket?.payload?.event_buffer_capacity || 0}
            </MetaText>
            <MetaText>
              ws_sse_drop_total={runtimeOverview?.websocket?.payload?.sse_drop_total || 0} | buffer_evictions=
              {runtimeOverview?.websocket?.payload?.buffer_evictions_total || 0}
            </MetaText>
            <MetaText>
              websocket_metrics={runtimeOverview?.websocket?.available ? 'available' : runtimeOverview?.websocket?.error || 'unavailable'}
            </MetaText>
            <div style={{ marginTop: '0.6rem' }}>
              {runtimeOverview?.pressure_alerts?.length ? (
                <div style={{ display: 'grid', gap: '0.3rem' }}>
                  {runtimeOverview.pressure_alerts.slice(0, 8).map((alert, index) => (
                    <div key={`${alert.surface}-${index}`} style={eventRowStyle}>
                      <strong style={{ fontSize: '0.76rem' }}>{alert.surface}</strong>
                      <MetaText>
                        severity={alert.severity} | {alert.message}
                      </MetaText>
                    </div>
                  ))}
                </div>
              ) : (
                <MetaText>No active pressure alerts.</MetaText>
              )}
            </div>
          </SectionCard>

          <SectionCard title="Per-Domain Coexistence Health">
            {domainRows.length === 0 ? (
              <MetaText>No domain-tagged activity available.</MetaText>
            ) : (
              <div style={{ display: 'grid', gap: '0.4rem', maxHeight: '320px', overflowY: 'auto' }}>
                {domainRows.map((row) => (
                  <div key={row.domain} style={eventRowStyle}>
                    <strong style={{ fontSize: '0.82rem' }}>{row.domain}</strong>
                    <MetaText>
                      total={row.activity?.total || 0} running={row.activity?.running || 0} queued=
                      {row.activity?.queued || 0} failed={row.activity?.failed || 0}
                    </MetaText>
                    <MetaText>
                      dispatches={row.isolation?.dispatches || 0} fairness_overrides=
                      {row.isolation?.fairness_overrides || 0} starvation_events=
                      {row.isolation?.starvation_events || 0} wait_ms={row.isolation?.last_queue_wait_ms || 0}
                    </MetaText>
                  </div>
                ))}
              </div>
            )}
          </SectionCard>
        </Grid>
      </div>

      <div style={{ marginTop: '1rem' }}>
        <SectionCard title="Recent Stream Events">
          {events.length === 0 ? (
            <MetaText>No events received yet.</MetaText>
          ) : (
            <div style={{ display: 'grid', gap: '0.5rem' }}>
              {events.map((event) => (
                <div key={event.id} style={eventRowStyle}>
                  <strong style={{ fontSize: '0.84rem' }}>{event.eventType}</strong>
                  <MetaText>{new Date(event.timestamp).toLocaleTimeString()}</MetaText>
                  {event.source.agentId ? (
                    <MetaText>
                      {event.source.agentId} ({event.source.agentType || 'unknown'})
                    </MetaText>
                  ) : null}
                  <JsonBlock data={event.payload} />
                </div>
              ))}
            </div>
          )}
        </SectionCard>
      </div>

      {focusedEvents.length > 0 ? (
        <div style={{ marginTop: '1rem' }}>
          <SectionCard title={`Focused Events: ${focusedAgentId}`}>
            <div style={{ display: 'grid', gap: '0.5rem' }}>
              {focusedEvents.map((event) => (
                <div key={event.id} style={eventRowStyle}>
                  <strong style={{ fontSize: '0.84rem' }}>{event.eventType}</strong>
                  <MetaText>{new Date(event.timestamp).toLocaleTimeString()}</MetaText>
                  <JsonBlock data={event.payload} />
                </div>
              ))}
            </div>
          </SectionCard>
        </div>
      ) : null}
    </PageContainer>
  )
}

const inputStyle: CSSProperties = {
  border: '1px solid #cbd5e1',
  borderRadius: '6px',
  padding: '0.45rem 0.6rem',
}

const buttonStyle: CSSProperties = {
  border: '1px solid #0f172a',
  borderRadius: '6px',
  background: '#0f172a',
  color: '#fff',
  padding: '0.45rem 0.75rem',
  cursor: 'pointer',
}

const eventRowStyle: CSSProperties = {
  border: '1px solid #e2e8f0',
  borderRadius: '6px',
  padding: '0.55rem',
  background: '#f8fafc',
}

const agentGridStyle: CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
  gap: '0.8rem',
}

const agentCardStyle: CSSProperties = {
  border: '1px solid #cbd5e1',
  borderRadius: '8px',
  background: '#ffffff',
  padding: '0.65rem',
}

function statusPillStyle(status: AgentCardStatus, warning: boolean): CSSProperties {
  const background = warning ? '#f59e0b' : STATUS_COLORS[status]
  return {
    borderRadius: '999px',
    padding: '0.1rem 0.45rem',
    color: '#ffffff',
    fontSize: '0.7rem',
    fontWeight: 700,
    background,
    textTransform: 'uppercase',
  }
}

const progressTrackStyle: CSSProperties = {
  height: '9px',
  borderRadius: '999px',
  overflow: 'hidden',
  border: '1px solid #dbe3ec',
  background: '#f1f5f9',
}

function progressFillStyle(progress: number, color: string): CSSProperties {
  return {
    width: `${progress}%`,
    height: '100%',
    background: color,
    transition: 'width 200ms linear',
  }
}

const dangerButtonStyle: CSSProperties = {
  border: '1px solid #b91c1c',
  borderRadius: '6px',
  background: '#b91c1c',
  color: '#ffffff',
  padding: '0.34rem 0.55rem',
  fontSize: '0.75rem',
  cursor: 'pointer',
}

const secondaryButtonStyle: CSSProperties = {
  border: '1px solid #334155',
  borderRadius: '6px',
  background: '#ffffff',
  color: '#0f172a',
  padding: '0.34rem 0.55rem',
  fontSize: '0.75rem',
  cursor: 'pointer',
}
