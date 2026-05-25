import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiRequest, toErrorMessage } from '../api/client'
import { API_ROUTES } from '../config'
import { DataPanel } from '../components/DataPanel'
import { Grid, JsonBlock, MetaText, PageContainer, PageHeader, SectionCard } from '../components/PagePrimitives'
import { useRuntimeQuery } from '../runtime/useRuntimeQuery'

interface AuditEntry {
  id: number
  timestamp: number
  user_id: string | null
  session_id: string
  event_type: string
  target_type: string
  target_id: string
  before_state: string | null
  after_state: string | null
  chain_hash: string | null
}

interface AuditResponse {
  entries: AuditEntry[]
  count: number
}

interface TimelineStats {
  approvals: number
  escalations: number
  failures: number
  retries: number
  policy: number
  other: number
}

function classifyEvent(eventType: string): keyof TimelineStats {
  if (eventType.includes('approval')) {
    if (eventType.includes('escalat')) {
      return 'escalations'
    }
    return 'approvals'
  }
  if (eventType.includes('retry') || eventType.includes('task.queued')) {
    return 'retries'
  }
  if (eventType.includes('failed') || eventType.includes('timeout') || eventType.includes('rejected')) {
    return 'failures'
  }
  if (eventType.includes('governance') || eventType.includes('charter') || eventType.includes('policy')) {
    return 'policy'
  }
  return 'other'
}

function continuitySummary(entries: AuditEntry[]): {
  contiguous: number
  gaps: number
  nonMonotonicTime: number
} {
  if (entries.length <= 1) {
    return { contiguous: entries.length, gaps: 0, nonMonotonicTime: 0 }
  }

  let contiguous = 0
  let gaps = 0
  let nonMonotonicTime = 0

  for (let index = 0; index < entries.length - 1; index += 1) {
    const current = entries[index]
    const next = entries[index + 1]
    if (current.id === next.id + 1) {
      contiguous += 1
    } else {
      gaps += 1
    }
    if (current.timestamp < next.timestamp) {
      nonMonotonicTime += 1
    }
  }

  return { contiguous, gaps, nonMonotonicTime }
}

function eventTone(eventType: string): string {
  const kind = classifyEvent(eventType)
  if (kind === 'failures') {
    return '#991b1b'
  }
  if (kind === 'escalations' || kind === 'retries') {
    return '#92400e'
  }
  if (kind === 'approvals' || kind === 'policy') {
    return '#0f766e'
  }
  return '#334155'
}

function approvalHint(status: string): string {
  if (!status) {
    return 'No action executed yet.'
  }
  if (status === 'pending') {
    return 'Pending explicit human review.'
  }
  if (status === 'passed') {
    return 'Approved transition recorded.'
  }
  if (status === 'failed') {
    return 'Rejected transition recorded.'
  }
  if (status === 'in_progress') {
    return 'Escalation in progress.'
  }
  return `Status: ${status}`
}

export default function GovernanceCommandCenter() {
  const [actionName, setActionName] = useState('infrastructure_escalation')
  const [confidence, setConfidence] = useState(0.6)
  const [destructive, setDestructive] = useState(false)
  const [explicitlyApproved, setExplicitlyApproved] = useState(false)

  const [result, setResult] = useState<Record<string, unknown> | null>(null)
  const [error, setError] = useState('')

  const [userFilter, setUserFilter] = useState('all')
  const [eventFilter, setEventFilter] = useState('all')
  const [searchTarget, setSearchTarget] = useState('')
  const { data: auditData, error: auditError, loading: auditLoading, lastUpdated: auditLastUpdated } = useRuntimeQuery<AuditResponse>(
    'governance-audit',
    API_ROUTES.governance.auditList(300),
    { intervalMs: 15_000, ttlMs: 3_000 },
  )
  const auditEntries = auditData?.entries || []

  const timelineStats = useMemo<TimelineStats>(() => {
    const stats: TimelineStats = {
      approvals: 0,
      escalations: 0,
      failures: 0,
      retries: 0,
      policy: 0,
      other: 0,
    }
    for (const entry of auditEntries) {
      const kind = classifyEvent(entry.event_type)
      stats[kind] += 1
    }
    return stats
  }, [auditEntries])

  const ordering = useMemo(() => continuitySummary(auditEntries), [auditEntries])

  const availableUsers = useMemo(() => {
    return Array.from(new Set(auditEntries.map((entry) => entry.user_id || 'system'))).sort()
  }, [auditEntries])

  const availableEventTypes = useMemo(() => {
    return Array.from(new Set(auditEntries.map((entry) => entry.event_type))).sort()
  }, [auditEntries])

  const filteredTimeline = useMemo(() => {
    const targetNeedle = searchTarget.trim().toLowerCase()
    return auditEntries.filter((entry) => {
      const userValue = entry.user_id || 'system'
      if (userFilter !== 'all' && userValue !== userFilter) {
        return false
      }
      if (eventFilter !== 'all' && entry.event_type !== eventFilter) {
        return false
      }
      if (targetNeedle && !`${entry.target_type}:${entry.target_id}`.toLowerCase().includes(targetNeedle)) {
        return false
      }
      return true
    })
  }, [auditEntries, eventFilter, searchTarget, userFilter])

  async function checkAction(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    setResult(null)
    try {
      const response = await apiRequest<Record<string, unknown>>(API_ROUTES.charter.checkAction(), {
        method: 'POST',
        body: JSON.stringify({
          action: actionName,
          confidence,
          context: {
            destructive,
            explicitly_approved: explicitlyApproved,
          },
        }),
      })
      setResult(response)
    } catch (err) {
      setError(toErrorMessage(err))
    }
  }

  const resultStatus = typeof result?.allowed === 'boolean' ? (result.allowed ? 'passed' : 'failed') : ''

  return (
    <PageContainer>
      <PageHeader
        title="Governance Timeline Viewer"
        subtitle="Deterministic governance chronology: approvals, escalations, retries, failures, and policy checks with audit visibility."
      />

      <Grid>
        <SectionCard title="Policy Evaluation (Dry-Run)">
          <form onSubmit={checkAction} style={{ display: 'grid', gap: '0.5rem' }}>
            <input
              style={inputStyle}
              value={actionName}
              onChange={(e) => setActionName(e.target.value)}
              placeholder="Action name"
            />
            <label style={labelStyle}>
              Confidence: {confidence.toFixed(2)}
              <input
                type="range"
                min={0}
                max={1}
                step={0.01}
                value={confidence}
                onChange={(e) => setConfidence(Number(e.target.value))}
              />
            </label>
            <label style={checkboxStyle}>
              <input type="checkbox" checked={destructive} onChange={(e) => setDestructive(e.target.checked)} />
              Destructive intent
            </label>
            <label style={checkboxStyle}>
              <input
                type="checkbox"
                checked={explicitlyApproved}
                onChange={(e) => setExplicitlyApproved(e.target.checked)}
              />
              Explicitly approved context
            </label>
            <button style={buttonStyle} type="submit">
              Evaluate Policy
            </button>
          </form>
          <div style={{ marginTop: '0.7rem' }}>
            {error ? <MetaText>{error}</MetaText> : null}
            <MetaText>{approvalHint(resultStatus)}</MetaText>
            {result ? <JsonBlock data={result} /> : null}
          </div>
        </SectionCard>

        <SectionCard title="Timeline Classification Summary">
          <MetaText>approvals={timelineStats.approvals}</MetaText>
          <MetaText>escalations={timelineStats.escalations}</MetaText>
          <MetaText>failures={timelineStats.failures}</MetaText>
          <MetaText>retries={timelineStats.retries}</MetaText>
          <MetaText>policy={timelineStats.policy}</MetaText>
          <MetaText>other={timelineStats.other}</MetaText>
          <div style={{ marginTop: '0.55rem' }}>
            <MetaText>
              Deterministic ordering checks: contiguous_pairs={ordering.contiguous}, id_gaps={ordering.gaps},
              non_monotonic_timestamps={ordering.nonMonotonicTime}
            </MetaText>
          </div>
        </SectionCard>
      </Grid>

      <div style={{ marginTop: '1rem' }}>
        <SectionCard title="Audit Timeline">
          <div style={{ display: 'grid', gap: '0.7rem' }}>
            <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
              <select value={eventFilter} onChange={(event) => setEventFilter(event.target.value)} style={inputStyle}>
                <option value="all">All Events</option>
                {availableEventTypes.map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
              <select value={userFilter} onChange={(event) => setUserFilter(event.target.value)} style={inputStyle}>
                <option value="all">All Users</option>
                {availableUsers.map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
              <input
                style={inputStyle}
                value={searchTarget}
                onChange={(event) => setSearchTarget(event.target.value)}
                placeholder="Filter target type:id"
              />
            </div>

            {auditError ? <MetaText>{auditError}</MetaText> : null}
            <MetaText>
              Showing {filteredTimeline.length} entries | Last refresh:{' '}
              {auditLastUpdated ? new Date(auditLastUpdated).toLocaleTimeString() : 'never'} |{' '}
              {auditLoading ? 'Refreshing…' : 'Idle'}
            </MetaText>

            {filteredTimeline.length === 0 ? (
              <MetaText>No timeline entries match current filters.</MetaText>
            ) : (
              <div style={{ display: 'grid', gap: '0.45rem' }}>
                {filteredTimeline.map((entry) => {
                  const tone = eventTone(entry.event_type)
                  const replayLink = entry.target_type === 'task' ? `/debug?task=${encodeURIComponent(entry.target_id)}` : ''
                  return (
                    <div key={entry.id} style={{ ...timelineRowStyle, borderColor: `${tone}55` }}>
                      <strong style={{ fontSize: '0.84rem', color: tone }}>{entry.event_type}</strong>
                      <MetaText>
                        {new Date(entry.timestamp * 1000).toLocaleString()} | user={entry.user_id || 'system'} | target=
                        {entry.target_type}:{entry.target_id}
                      </MetaText>
                      <MetaText>session={entry.session_id} | id={entry.id}</MetaText>
                      {replayLink ? (
                        <Link to={replayLink} style={linkStyle}>
                          Inspect linked replay
                        </Link>
                      ) : null}
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        </SectionCard>
      </div>

      <div style={{ marginTop: '1rem' }}>
        <Grid>
          <DataPanel title="Governance Evidence Summary" endpoint={API_ROUTES.governance.evidenceSummary()} intervalMs={20_000} />
          <DataPanel title="Governance Approvals" endpoint={API_ROUTES.governance.approvalsList('pending', 50)} intervalMs={20_000} />
          <DataPanel title="Charter Pending Approvals" endpoint={API_ROUTES.charter.pendingApprovals()} intervalMs={20_000} />
          <DataPanel title="Fail-Safe Report" endpoint={API_ROUTES.charter.failsafeReport()} intervalMs={20_000} />
          <DataPanel title="Integrity Report" endpoint={API_ROUTES.charter.integrityReport()} intervalMs={20_000} />
        </Grid>
      </div>
    </PageContainer>
  )
}

const inputStyle: React.CSSProperties = {
  border: '1px solid #cbd5e1',
  borderRadius: '6px',
  padding: '0.45rem 0.6rem',
}

const labelStyle: React.CSSProperties = {
  display: 'grid',
  gap: '0.35rem',
  fontSize: '0.88rem',
}

const checkboxStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: '0.45rem',
  fontSize: '0.88rem',
}

const buttonStyle: React.CSSProperties = {
  border: '1px solid #0f172a',
  borderRadius: '6px',
  background: '#0f172a',
  color: '#fff',
  padding: '0.5rem 0.75rem',
  cursor: 'pointer',
}

const timelineRowStyle: React.CSSProperties = {
  border: '1px solid #dbe3ec',
  borderRadius: '7px',
  background: '#f8fafc',
  padding: '0.55rem 0.65rem',
  display: 'grid',
  gap: '0.2rem',
}

const linkStyle: React.CSSProperties = {
  color: '#1d4ed8',
  textDecoration: 'none',
  fontSize: '0.8rem',
}
