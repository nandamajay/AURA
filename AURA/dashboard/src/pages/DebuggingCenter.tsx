import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { apiRequest, toErrorMessage } from '../api/client'
import { API_ROUTES } from '../config'
import { DataPanel } from '../components/DataPanel'
import { Grid, JsonBlock, MetaText, PageContainer, PageHeader, SectionCard } from '../components/PagePrimitives'
import { useRuntimeQuery } from '../runtime/useRuntimeQuery'

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
  recording_state?: string
  revision?: number
  recorded_at?: string
  finalized_at?: string
  prompt_count: number
  response_count: number
  execution_steps: number
  output_keys: string[]
  output_hash: string
  snapshot_hash?: string
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

interface ReplayStateResponse {
  task_id: string
  exists: boolean
  recording_state: 'missing' | 'mutable' | 'finalized' | string
  replayable: boolean
  integrity_ok: boolean
  revision?: number
  created_at?: number
  finalized_at?: number
  output_hash?: string
  snapshot_hash?: string
}

interface TimelineItem {
  id: string
  title: string
  detail: string
  tone: 'neutral' | 'ok' | 'warn'
}

interface EvidenceFile {
  path: string
  name: string
  extension: string
  size_bytes: number
  modified_at: string
}

interface EvidenceSection {
  root: string
  files: EvidenceFile[]
}

interface EvidenceIndexResponse {
  generated_at: string
  repo_root: string
  sections: Record<string, EvidenceSection>
}

interface EvidenceReadResponse {
  section: string
  relative_path: string
  absolute_path: string
  size_bytes: number
  returned_bytes: number
  truncated: boolean
  content: string
}

interface NondeterminismResult {
  findings: Array<Record<string, unknown>>
  risk_count: number
  recommendation: string
}

function toPreview(value: unknown, max = 160): string {
  const raw = typeof value === 'string' ? value : JSON.stringify(value)
  if (!raw) {
    return ''
  }
  return raw.length <= max ? raw : `${raw.slice(0, max)}...`
}

function replayBoundaryLabel(state: ReplayStateResponse | null): string {
  if (!state || !state.exists) {
    return 'non-replayable'
  }
  if (state.recording_state === 'finalized') {
    return 'finalized replay'
  }
  if (state.recording_state === 'mutable') {
    return 'mutable replay (not deterministic replayable yet)'
  }
  return `non-replayable (${state.recording_state})`
}

export default function DebuggingCenter() {
  const [searchParams] = useSearchParams()
  const sourceHint = searchParams.get('source') || ''
  const taskHint = searchParams.get('task') || ''

  const [replayTaskId, setReplayTaskId] = useState(taskHint)
  const [replayBusy, setReplayBusy] = useState(false)
  const [replayError, setReplayError] = useState('')
  const [replayState, setReplayState] = useState<ReplayStateResponse | null>(null)
  const [replayResult, setReplayResult] = useState<ReplayResponse | null>(null)

  const [evidenceReadError, setEvidenceReadError] = useState('')
  const [selectedSection, setSelectedSection] = useState('')
  const [selectedPath, setSelectedPath] = useState('')
  const [evidenceRead, setEvidenceRead] = useState<EvidenceReadResponse | null>(null)
  const [evidenceFilter, setEvidenceFilter] = useState('')
  const {
    data: evidenceIndex,
    error: evidenceIndexError,
    loading: evidenceLoading,
    reload: reloadEvidenceIndex,
  } = useRuntimeQuery<EvidenceIndexResponse>(
    'debug-evidence-index',
    API_ROUTES.knowledge.evidenceIndex(),
    { intervalMs: 60_000, ttlMs: 10_000 },
  )

  const [determinismCode, setDeterminismCode] = useState('')
  const [determinismResult, setDeterminismResult] = useState<NondeterminismResult | null>(null)
  const [determinismError, setDeterminismError] = useState('')
  const [determinismBusy, setDeterminismBusy] = useState(false)

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

    if (replay.finalized_at) {
      steps.push({
        id: 'finalized',
        title: 'Replay Finalized',
        detail: `Finalized at ${new Date(replay.finalized_at).toLocaleString()}`,
        tone: 'ok',
      })
    }

    steps.push({
      id: 'replay-start',
      title: 'Replay Executed',
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

  const evidenceSections = useMemo(() => {
    return evidenceIndex?.sections ? Object.keys(evidenceIndex.sections).sort() : []
  }, [evidenceIndex])

  const evidenceFiles = useMemo(() => {
    if (!selectedSection || !evidenceIndex?.sections[selectedSection]) {
      return []
    }
    const files = evidenceIndex.sections[selectedSection].files
    const needle = evidenceFilter.trim().toLowerCase()
    if (!needle) {
      return files
    }
    return files.filter((file) => file.path.toLowerCase().includes(needle) || file.name.toLowerCase().includes(needle))
  }, [evidenceFilter, evidenceIndex, selectedSection])

  useEffect(() => {
    if (!taskHint) {
      return
    }
    void loadReplay(taskHint)
    // intentionally only on initial hint
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [taskHint])

  useEffect(() => {
    if (!evidenceIndex) {
      return
    }
    const sections = Object.keys(evidenceIndex.sections || {})
    if (sections.length && !selectedSection) {
      setSelectedSection(sections[0])
    }
  }, [evidenceIndex, selectedSection])

  async function loadReplay(taskIdOverride?: string) {
    const taskId = (taskIdOverride || replayTaskId).trim()
    if (!taskId) {
      return
    }

    setReplayBusy(true)
    setReplayError('')
    setReplayResult(null)
    setReplayState(null)
    try {
      const state = await apiRequest<ReplayStateResponse>(API_ROUTES.tasks.replayState(taskId))
      setReplayState(state)
      if (state.replayable) {
        const result = await apiRequest<ReplayResponse>(API_ROUTES.tasks.replay(taskId))
        setReplayResult(result)
      }
    } catch (error) {
      setReplayError(toErrorMessage(error))
    } finally {
      setReplayBusy(false)
    }
  }

  async function loadEvidenceFile(section: string, path: string) {
    setEvidenceReadError('')
    setEvidenceRead(null)
    setSelectedPath(path)
    try {
      const response = await apiRequest<EvidenceReadResponse>(API_ROUTES.knowledge.evidenceRead(section, path, 120_000))
      setEvidenceRead(response)
    } catch (error) {
      setEvidenceReadError(toErrorMessage(error))
    }
  }

  async function runDeterminismCheck(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!determinismCode.trim()) {
      return
    }
    setDeterminismBusy(true)
    setDeterminismError('')
    try {
      const response = await apiRequest<NondeterminismResult>(API_ROUTES.memory.nondeterminismCheck(), {
        method: 'POST',
        body: JSON.stringify({ source_code: determinismCode }),
      })
      setDeterminismResult(response)
    } catch (error) {
      setDeterminismError(toErrorMessage(error))
      setDeterminismResult(null)
    } finally {
      setDeterminismBusy(false)
    }
  }

  return (
    <PageContainer>
      <PageHeader
        title="Replay & Evidence Explorer"
        subtitle="Inspect finalized vs mutable replay boundaries, lineage hashes, determinism findings, and runtime evidence artifacts."
      />

      {sourceHint ? (
        <div style={{ marginBottom: '1rem' }}>
          <MetaText>Source focus from Architecture Lab: {sourceHint}</MetaText>
        </div>
      ) : null}

      <Grid>
        <SectionCard title="Replay Boundary Inspection">
          <form
            onSubmit={(event) => {
              event.preventDefault()
              void loadReplay()
            }}
            style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center' }}
          >
            <input
              value={replayTaskId}
              onChange={(event) => setReplayTaskId(event.target.value)}
              placeholder="task_id"
              style={inputStyle}
            />
            <button type="submit" style={buttonStyle} disabled={replayBusy || !replayTaskId.trim()}>
              {replayBusy ? 'Loading…' : 'Inspect Replay'}
            </button>
          </form>

          <div style={{ marginTop: '0.7rem', display: 'grid', gap: '0.3rem' }}>
            {replayError ? <MetaText>{replayError}</MetaText> : null}
            <MetaText>Boundary: {replayBoundaryLabel(replayState)}</MetaText>
            {replayState ? (
              <>
                <MetaText>
                  replayable={replayState.replayable ? 'yes' : 'no'} | integrity={replayState.integrity_ok ? 'ok' : 'n/a'}
                </MetaText>
                <MetaText>
                  revision={replayState.revision ?? 0} | output_hash={replayState.output_hash || '(none)'}
                </MetaText>
                <MetaText>snapshot_hash={replayState.snapshot_hash || '(none)'}</MetaText>
              </>
            ) : (
              <MetaText>No replay state loaded yet.</MetaText>
            )}
          </div>
        </SectionCard>

        <SectionCard title="Replay Failure / Non-Replayable Semantics">
          <MetaText>- `finalized`: deterministic replay expected, hash verifiable.</MetaText>
          <MetaText>- `mutable`: execution capture in progress; not deterministic replay artifact yet.</MetaText>
          <MetaText>- `missing`: no task_log available; replay not possible.</MetaText>
          <MetaText>- transient stream state (WS/SSE queues) is non-replayable by design.</MetaText>
        </SectionCard>
      </Grid>

      <div style={{ marginTop: '1rem' }}>
        <SectionCard title="Replay Lifecycle Timeline">
          {replayTimeline.length === 0 ? (
            <MetaText>No finalized replay timeline loaded.</MetaText>
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
          <SectionCard title="Determinism Inspector">
            <form onSubmit={runDeterminismCheck} style={{ display: 'grid', gap: '0.5rem' }}>
              <textarea
                value={determinismCode}
                onChange={(event) => setDeterminismCode(event.target.value)}
                placeholder="Paste Python code snippet to scan for nondeterminism patterns"
                style={textAreaStyle}
              />
              <button type="submit" style={buttonStyle} disabled={determinismBusy || !determinismCode.trim()}>
                {determinismBusy ? 'Scanning…' : 'Run Determinism Scan'}
              </button>
            </form>
            <div style={{ marginTop: '0.65rem' }}>
              {determinismError ? <MetaText>{determinismError}</MetaText> : null}
              {determinismResult ? <JsonBlock data={determinismResult} /> : <MetaText>No determinism scan executed yet.</MetaText>}
            </div>
          </SectionCard>

          <SectionCard title="Evidence Browser">
            <div style={{ display: 'flex', gap: '0.45rem', flexWrap: 'wrap' }}>
              <button style={buttonStyle} onClick={() => void reloadEvidenceIndex()} disabled={evidenceLoading}>
                {evidenceLoading ? 'Loading…' : 'Load Evidence Index'}
              </button>
              <input
                value={evidenceFilter}
                onChange={(event) => setEvidenceFilter(event.target.value)}
                placeholder="Filter evidence files"
                style={inputStyle}
              />
              {evidenceSections.length ? (
                <select value={selectedSection} onChange={(event) => setSelectedSection(event.target.value)} style={inputStyle}>
                  {evidenceSections.map((section) => (
                    <option key={section} value={section}>
                      {section}
                    </option>
                  ))}
                </select>
              ) : null}
            </div>
            {evidenceIndexError ? <MetaText>{evidenceIndexError}</MetaText> : null}
            {evidenceReadError ? <MetaText>{evidenceReadError}</MetaText> : null}
            <div style={{ marginTop: '0.6rem', display: 'grid', gap: '0.35rem', maxHeight: '200px', overflowY: 'auto' }}>
              {evidenceFiles.slice(0, 120).map((file) => (
                <button
                  key={file.path}
                  onClick={() => void loadEvidenceFile(selectedSection, file.path)}
                  style={{
                    ...evidenceFileButtonStyle,
                    borderColor: selectedPath === file.path ? '#1d4ed8' : '#cbd5e1',
                  }}
                >
                  <strong style={{ fontSize: '0.78rem' }}>{file.path}</strong>
                  <span style={{ color: '#64748b', fontSize: '0.73rem' }}>
                    {Math.round(file.size_bytes / 1024)}KB · {new Date(file.modified_at).toLocaleString()}
                  </span>
                </button>
              ))}
              {!evidenceFiles.length ? <MetaText>No evidence files loaded yet.</MetaText> : null}
            </div>
          </SectionCard>
        </Grid>
      </div>

      {evidenceRead ? (
        <div style={{ marginTop: '1rem' }}>
          <SectionCard
            title={`Evidence File: ${evidenceRead.relative_path}`}
            action={<MetaText>{evidenceRead.truncated ? 'truncated preview' : 'full preview'}</MetaText>}
          >
            <pre style={metricsStyle}>{evidenceRead.content}</pre>
          </SectionCard>
        </div>
      ) : null}

      <div style={{ marginTop: '1rem' }}>
        <Grid>
          <DataPanel title="Audit Ledger" endpoint={API_ROUTES.governance.auditList(30)} intervalMs={15_000} />
          <DataPanel title="Replay Incidents" endpoint={API_ROUTES.memory.replayIncidents(30)} intervalMs={15_000} />
          <DataPanel title="Ops Incidents" endpoint={API_ROUTES.memory.opsIncidents(30)} intervalMs={15_000} />
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
  maxHeight: '340px',
  overflow: 'auto',
}

const inputStyle: React.CSSProperties = {
  border: '1px solid #cbd5e1',
  borderRadius: '6px',
  padding: '0.42rem 0.6rem',
  minWidth: '220px',
}

const textAreaStyle: React.CSSProperties = {
  border: '1px solid #cbd5e1',
  borderRadius: '6px',
  padding: '0.55rem 0.6rem',
  minHeight: '140px',
  fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
  fontSize: '0.8rem',
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

const evidenceFileButtonStyle: React.CSSProperties = {
  textAlign: 'left',
  border: '1px solid #cbd5e1',
  borderRadius: '6px',
  background: '#fff',
  padding: '0.45rem 0.55rem',
  display: 'grid',
  gap: '0.12rem',
  cursor: 'pointer',
}
