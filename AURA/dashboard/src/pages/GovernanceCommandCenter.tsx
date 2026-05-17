import { useEffect, useMemo, useState, type CSSProperties } from 'react'
import { apiRequest, toErrorMessage } from '../api/client'
import { ENDPOINTS } from '../config'
import { DataPanel } from '../components/DataPanel'
import { Grid, JsonBlock, MetaText, PageContainer, PageHeader, SectionCard } from '../components/PagePrimitives'

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

interface ChainSummary {
  verified: number
  mismatched: number
  unverifiable: number
  missingHashes: number
}

const CHAIN_SEED = '0'.repeat(64)

function computeChainHash(previousHash: string, entry: AuditEntry): string {
  const material = [
    previousHash || CHAIN_SEED,
    String(entry.timestamp),
    entry.event_type,
    entry.target_type,
    entry.target_id,
    entry.user_id || '',
  ].join('|')
  const bytes = new TextEncoder().encode(material)
  const hex = Array.from(bytes)
    .map((value) => value.toString(16).padStart(2, '0'))
    .join('')
  return hex.slice(0, 64)
}

function summarizeChain(entries: AuditEntry[]): ChainSummary {
  if (!entries.length) {
    return { verified: 0, mismatched: 0, unverifiable: 0, missingHashes: 0 }
  }

  let verified = 0
  let mismatched = 0
  let unverifiable = 0
  let missingHashes = 0

  for (const entry of entries) {
    if (!entry.chain_hash) {
      missingHashes += 1
    }
  }

  for (let index = 0; index < entries.length; index += 1) {
    const current = entries[index]
    const previous = entries[index + 1]

    if (!current.chain_hash) {
      continue
    }

    if (!previous) {
      unverifiable += 1
      continue
    }

    if (current.id - previous.id !== 1) {
      unverifiable += 1
      continue
    }

    const expected = computeChainHash(previous.chain_hash || CHAIN_SEED, current)
    if (expected === current.chain_hash.toLowerCase()) {
      verified += 1
    } else {
      mismatched += 1
    }
  }

  return { verified, mismatched, unverifiable, missingHashes }
}

export default function GovernanceCommandCenter() {
  const [actionName, setActionName] = useState('infrastructure_escalation')
  const [confidence, setConfidence] = useState(0.6)
  const [destructive, setDestructive] = useState(false)
  const [explicitlyApproved, setExplicitlyApproved] = useState(false)

  const [result, setResult] = useState<unknown>(null)
  const [error, setError] = useState('')

  const [auditEntries, setAuditEntries] = useState<AuditEntry[]>([])
  const [auditError, setAuditError] = useState('')
  const [auditLoading, setAuditLoading] = useState(false)
  const [auditLastUpdated, setAuditLastUpdated] = useState(0)
  const [userFilter, setUserFilter] = useState('all')
  const [eventFilter, setEventFilter] = useState('all')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')

  const chainSummary = useMemo(() => summarizeChain(auditEntries), [auditEntries])

  const availableUsers = useMemo(() => {
    return Array.from(new Set(auditEntries.map((entry) => entry.user_id || 'system'))).sort()
  }, [auditEntries])

  const availableEventTypes = useMemo(() => {
    return Array.from(new Set(auditEntries.map((entry) => entry.event_type))).sort()
  }, [auditEntries])

  const filteredTimeline = useMemo(() => {
    const fromMs = dateFrom ? new Date(`${dateFrom}T00:00:00`).getTime() : 0
    const toMs = dateTo ? new Date(`${dateTo}T23:59:59`).getTime() : Number.POSITIVE_INFINITY

    return auditEntries.filter((entry) => {
      const userValue = entry.user_id || 'system'
      const timestampMs = entry.timestamp * 1000
      if (userFilter !== 'all' && userValue !== userFilter) {
        return false
      }
      if (eventFilter !== 'all' && entry.event_type !== eventFilter) {
        return false
      }
      if (timestampMs < fromMs || timestampMs > toMs) {
        return false
      }
      return true
    })
  }, [auditEntries, dateFrom, dateTo, eventFilter, userFilter])

  useEffect(() => {
    let cancelled = false

    async function loadAudit() {
      setAuditLoading(true)
      try {
        const response = await apiRequest<AuditResponse>(`${ENDPOINTS.audit}?limit=250`)
        if (!cancelled) {
          setAuditEntries(response.entries || [])
          setAuditError('')
          setAuditLastUpdated(Date.now())
        }
      } catch (err) {
        if (!cancelled) {
          setAuditError(toErrorMessage(err))
        }
      } finally {
        if (!cancelled) {
          setAuditLoading(false)
        }
      }
    }

    void loadAudit()
    const timer = window.setInterval(() => {
      void loadAudit()
    }, 20_000)

    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [])

  async function checkAction(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    try {
      const response = await apiRequest(`${ENDPOINTS.charter}/check-action`, {
        method: 'POST',
        body: JSON.stringify({
          action_type: actionName,
          confidence,
          destructive,
          explicitly_approved: explicitlyApproved,
        }),
      })
      setResult(response)
    } catch (err) {
      setError(toErrorMessage(err))
      setResult(null)
    }
  }

  return (
    <PageContainer>
      <PageHeader
        title="Governance Command Center"
        subtitle="Approval governance timeline with policy checks and append-only audit chain verification."
      />

      <Grid>
        <SectionCard title="Policy Check Action">
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
              Destructive action
            </label>
            <label style={checkboxStyle}>
              <input
                type="checkbox"
                checked={explicitlyApproved}
                onChange={(e) => setExplicitlyApproved(e.target.checked)}
              />
              Explicitly approved
            </label>
            <button style={buttonStyle} type="submit">
              Evaluate Action
            </button>
          </form>
          <div style={{ marginTop: '0.75rem' }}>
            {error ? <MetaText>{error}</MetaText> : null}
            {result ? <JsonBlock data={result} /> : <MetaText>No policy check executed yet.</MetaText>}
          </div>
        </SectionCard>

        <DataPanel title="Charter Summary" endpoint={`${ENDPOINTS.charter}/summary`} intervalMs={20_000} />
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
              <input type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} style={inputStyle} />
              <input type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)} style={inputStyle} />
            </div>

            {auditError ? <MetaText>{auditError}</MetaText> : null}
            <MetaText>
              Chain hash verification: {chainSummary.verified} verified | {chainSummary.mismatched} mismatched |{' '}
              {chainSummary.unverifiable} unverifiable | {chainSummary.missingHashes} missing hashes
            </MetaText>
            <MetaText>
              Showing {filteredTimeline.length} entries | Last refresh:{' '}
              {auditLastUpdated ? new Date(auditLastUpdated).toLocaleTimeString() : 'never'} | {auditLoading ? 'Refreshing...' : 'Idle'}
            </MetaText>

            {filteredTimeline.length === 0 ? (
              <MetaText>No timeline entries match current filters.</MetaText>
            ) : (
              <div style={{ display: 'grid', gap: '0.45rem' }}>
                {filteredTimeline.map((entry) => (
                  <div key={entry.id} style={timelineRowStyle}>
                    <strong style={{ fontSize: '0.84rem' }}>{entry.event_type}</strong>
                    <MetaText>
                      {new Date(entry.timestamp * 1000).toLocaleString()} | user={entry.user_id || 'system'} | target=
                      {entry.target_type}:{entry.target_id}
                    </MetaText>
                    <MetaText>session={entry.session_id}</MetaText>
                    <MetaText>chain_hash={entry.chain_hash || '(missing)'}</MetaText>
                  </div>
                ))}
              </div>
            )}
          </div>
        </SectionCard>
      </div>

      <div style={{ marginTop: '1rem' }}>
        <Grid>
          <DataPanel title="Integrity Report" endpoint={`${ENDPOINTS.charter}/integrity/report`} intervalMs={20_000} />
          <DataPanel title="Fail-Safe Report" endpoint={`${ENDPOINTS.charter}/failsafe/report`} intervalMs={20_000} />
          <DataPanel title="Violations" endpoint={`${ENDPOINTS.charter}/violations`} intervalMs={20_000} />
        </Grid>
      </div>
    </PageContainer>
  )
}

const inputStyle: CSSProperties = {
  border: '1px solid #cbd5e1',
  borderRadius: '6px',
  padding: '0.45rem 0.6rem',
}

const labelStyle: CSSProperties = {
  display: 'grid',
  gap: '0.35rem',
  fontSize: '0.88rem',
}

const checkboxStyle: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: '0.45rem',
  fontSize: '0.88rem',
}

const buttonStyle: CSSProperties = {
  border: '1px solid #0f172a',
  borderRadius: '6px',
  background: '#0f172a',
  color: '#fff',
  padding: '0.5rem 0.75rem',
  cursor: 'pointer',
}

const timelineRowStyle: CSSProperties = {
  border: '1px solid #dbe3ec',
  borderRadius: '7px',
  background: '#f8fafc',
  padding: '0.55rem 0.65rem',
  display: 'grid',
  gap: '0.2rem',
}
