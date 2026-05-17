import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { apiRequest, toErrorMessage } from '../api/client'
import { ENDPOINTS } from '../config'
import { DataPanel } from '../components/DataPanel'
import { Grid, JsonBlock, MetaText, PageContainer, PageHeader, SectionCard } from '../components/PagePrimitives'

interface ReplayPrompt {
  role?: string
  content?: string
}

interface ReplayContext {
  seed?: number
  model_version?: string
}

interface ReplayPayload {
  success: boolean
  fidelity: string
  task_id: string
  agent_type: string
  context?: ReplayContext
  recorded_at?: string
  prompt_count: number
  response_count: number
  execution_steps: number
  output_keys: string[]
  output_hash: string
  prompts?: ReplayPrompt[]
  responses?: unknown[]
  execution?: unknown[]
  output?: Record<string, unknown>
  replayed_at: string
}

interface ReplayResponse {
  task_id: string
  requested_by: string
  integrity_ok: boolean
  replay: ReplayPayload
}

interface TimelineItem {
  id: string
  title: string
  detail: string
  tone: 'neutral' | 'ok' | 'warn'
}

function toPreview(value: unknown, max = 160): string {
  const raw = typeof value === 'string' ? value : JSON.stringify(value)
  if (!raw) {
    return ''
  }
  return raw.length <= max ? raw : `${raw.slice(0, max)}...`
}

export default function DebuggingCenter() {
  const [searchParams] = useSearchParams()
  const [metrics, setMetrics] = useState('')
  const [metricsError, setMetricsError] = useState('')
  const [replayTaskId, setReplayTaskId] = useState('')
  const [replayBusy, setReplayBusy] = useState(false)
  const [replayError, setReplayError] = useState('')
  const [replayResult, setReplayResult] = useState<ReplayResponse | null>(null)

  const sourceHint = searchParams.get('source') || ''

  const replayTimeline = useMemo<TimelineItem[]>(() => {
    if (!replayResult) {
      return []
    }

    const replay = replayResult.replay
    const prompts = replay.prompts || []
    const responses = replay.responses || []
    const execution = replay.execution || []
    const steps: TimelineItem[] = []

    if (replay.recorded_at) {
      steps.push({
        id: 'recorded',
        title: 'Task Recorded',
        detail: `Recorded at ${new Date(replay.recorded_at).toLocaleString()}`,
        tone: 'neutral',
      })
    }

    steps.push({
      id: 'replay-start',
      title: 'Replay Started',
      detail: `Replayed at ${new Date(replay.replayed_at).toLocaleString()}`,
      tone: 'neutral',
    })

    const llmCycles = Math.max(prompts.length, responses.length)
    for (let index = 0; index < llmCycles; index += 1) {
      const prompt = prompts[index]
      const response = responses[index]

      if (prompt) {
        steps.push({
          id: `prompt-${index}`,
          title: `LLM Prompt #${index + 1}`,
          detail: `${prompt.role || 'system'}: ${toPreview(prompt.content, 140)}`,
          tone: 'neutral',
        })
      }

      if (response !== undefined) {
        steps.push({
          id: `response-${index}`,
          title: `LLM Response #${index + 1}`,
          detail: toPreview(response, 140),
          tone: 'neutral',
        })
      }
    }

    execution.slice(0, 25).forEach((step, index) => {
      steps.push({
        id: `exec-${index}`,
        title: `Execution Step #${index + 1}`,
        detail: toPreview(step, 180),
        tone: 'neutral',
      })
    })

    steps.push({
      id: 'result',
      title: replayResult.integrity_ok ? 'Integrity Verified' : 'Integrity Mismatch',
      detail: replay.output_hash ? `output_hash=${replay.output_hash}` : 'No output hash found',
      tone: replayResult.integrity_ok ? 'ok' : 'warn',
    })

    return steps
  }, [replayResult])

  useEffect(() => {
    let cancelled = false

    async function loadMetrics() {
      try {
        const response = await fetch(ENDPOINTS.metrics)
        if (!response.ok) {
          throw new Error(`Metrics request failed (${response.status})`)
        }
        const text = await response.text()
        if (!cancelled) {
          setMetrics(text)
          setMetricsError('')
        }
      } catch (error) {
        if (!cancelled) {
          setMetricsError(error instanceof Error ? error.message : 'Metrics fetch failed')
        }
      }
    }

    void loadMetrics()
    const timer = setInterval(loadMetrics, 30_000)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [])

  async function loadReplay(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const taskId = replayTaskId.trim()
    if (!taskId) {
      return
    }

    setReplayBusy(true)
    setReplayError('')
    try {
      const result = await apiRequest<ReplayResponse>(`${ENDPOINTS.tasks}/${encodeURIComponent(taskId)}/replay`)
      setReplayResult(result)
    } catch (error) {
      setReplayResult(null)
      setReplayError(toErrorMessage(error))
    } finally {
      setReplayBusy(false)
    }
  }

  return (
    <PageContainer>
      <PageHeader
        title="Debugging Center"
        subtitle="Operational debugging surface: replay timeline, metrics, audits, and incident ledgers."
      />

      {sourceHint ? (
        <div style={{ marginBottom: '1rem' }}>
          <MetaText>Source focus from Architecture Lab: {sourceHint}</MetaText>
        </div>
      ) : null}

      <Grid>
        <SectionCard title="Task Replay Viewer">
          <form onSubmit={loadReplay} style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
            <input
              value={replayTaskId}
              onChange={(event) => setReplayTaskId(event.target.value)}
              placeholder="task_id"
              style={inputStyle}
            />
            <button type="submit" style={buttonStyle} disabled={replayBusy || !replayTaskId.trim()}>
              {replayBusy ? 'Loading...' : 'Replay'}
            </button>
          </form>
          <div style={{ marginTop: '0.7rem' }}>
            {replayError ? <MetaText>{replayError}</MetaText> : null}
            {replayResult ? (
              <div style={{ display: 'grid', gap: '0.4rem' }}>
                <MetaText>
                  Fidelity: {replayResult.replay.fidelity} | Integrity: {replayResult.integrity_ok ? 'OK' : 'FAILED'}
                </MetaText>
                <MetaText>
                  Agent: {replayResult.replay.agent_type} | Seed: {replayResult.replay.context?.seed ?? 'n/a'} | Model:{' '}
                  {replayResult.replay.context?.model_version ?? 'n/a'}
                </MetaText>
                <MetaText>
                  Prompts: {replayResult.replay.prompt_count} | Responses: {replayResult.replay.response_count} | Execution steps:{' '}
                  {replayResult.replay.execution_steps}
                </MetaText>
              </div>
            ) : (
              <MetaText>Submit a task id to load replay timeline.</MetaText>
            )}
          </div>
        </SectionCard>

        <SectionCard title="Core Metrics (/metrics)">
          {metricsError ? <MetaText>{metricsError}</MetaText> : null}
          <pre style={metricsStyle}>{metrics || 'Loading metrics...'}</pre>
        </SectionCard>
        <DataPanel title="Health" endpoint={ENDPOINTS.health} includeAuth={false} intervalMs={10_000} />
      </Grid>

      <div style={{ marginTop: '1rem' }}>
        <SectionCard title="Replay Timeline">
          {replayTimeline.length === 0 ? (
            <MetaText>No replay timeline loaded.</MetaText>
          ) : (
            <div style={{ display: 'grid', gap: '0.45rem' }}>
              {replayTimeline.map((item) => (
                <div key={item.id} style={timelineRowStyle(item.tone)}>
                  <strong style={{ fontSize: '0.84rem' }}>{item.title}</strong>
                  <MetaText>{item.detail}</MetaText>
                </div>
              ))}
            </div>
          )}
        </SectionCard>
      </div>

      {replayResult ? (
        <div style={{ marginTop: '1rem' }}>
          <Grid>
            <SectionCard title="Replay Summary Payload">
              <JsonBlock data={replayResult.replay} />
            </SectionCard>
            <SectionCard title="Replay Output">
              <JsonBlock data={replayResult.replay.output || {}} />
            </SectionCard>
          </Grid>
        </div>
      ) : null}

      <div style={{ marginTop: '1rem' }}>
        <Grid>
          <DataPanel title="Audit Ledger" endpoint={`${ENDPOINTS.audit}?limit=30`} intervalMs={15_000} />
          <DataPanel title="Failure Ledger" endpoint={`${ENDPOINTS.memory}/failures?limit=30`} intervalMs={15_000} />
          <DataPanel title="Ops Incidents" endpoint={`${ENDPOINTS.memory}/ops-incidents?limit=30`} intervalMs={15_000} />
        </Grid>
      </div>
    </PageContainer>
  )
}

const metricsStyle: React.CSSProperties = {
  margin: 0,
  fontSize: '0.76rem',
  lineHeight: 1.35,
  background: '#0f172a',
  color: '#e2e8f0',
  borderRadius: '6px',
  padding: '0.75rem',
  maxHeight: '300px',
  overflow: 'auto',
}

const inputStyle: React.CSSProperties = {
  border: '1px solid #cbd5e1',
  borderRadius: '6px',
  padding: '0.42rem 0.6rem',
  minWidth: '260px',
}

const buttonStyle: React.CSSProperties = {
  border: '1px solid #0f172a',
  borderRadius: '6px',
  background: '#0f172a',
  color: '#ffffff',
  padding: '0.4rem 0.65rem',
  fontSize: '0.82rem',
  cursor: 'pointer',
}

function timelineRowStyle(tone: TimelineItem['tone']): React.CSSProperties {
  const borderColor = tone === 'ok' ? '#22c55e' : tone === 'warn' ? '#ef4444' : '#cbd5e1'
  return {
    border: `1px solid ${borderColor}`,
    borderRadius: '7px',
    background: '#f8fafc',
    padding: '0.5rem 0.6rem',
    display: 'grid',
    gap: '0.2rem',
  }
}
