import { Link } from 'react-router-dom'
import { ENDPOINTS } from '../config'
import { useApiData } from '../hooks/useApiData'
import { Grid, MetaText, PageContainer, PageHeader, SectionCard } from '../components/PagePrimitives'

interface QueueStats {
  P0_critical: number
  P1_normal: number
  P2_background: number
  running: number
  completed_today: number
  failed_today: number
  fairness_overrides_total: number
  starvation_events_total: number
}

interface DomainActivity {
  total: number
  running: number
  queued: number
  failed: number
  completed: number
}

interface RuntimeOverview {
  generated_at: string
  classification: {
    operational: string
    determinism: string
  }
  queue: QueueStats
  replay: {
    finalized: number
    mutable: number
  }
  governance: {
    approvals: Record<string, number>
    audit_last_hour: number
  }
  websocket: {
    available: boolean
    payload?: {
      event_buffer_size?: number
      event_buffer_capacity?: number
      sse_drop_total?: number
      buffer_evictions_total?: number
      domain_ingest_count?: Record<string, number>
      domain_ws_delivery_count?: Record<string, number>
      domain_sse_delivery_count?: Record<string, number>
      buffer_counts_by_domain?: Record<string, number>
    }
    error?: string
  }
  tasks: {
    status_counts: Record<string, number>
    retry_pressure: {
      retry_pending_tasks: number
      tasks_with_retry_lineage: number
    }
    domain_activity: Record<string, DomainActivity>
  }
  pressure_alerts: Array<{
    severity: string
    surface: string
    message: string
  }>
}

function formatSince(iso: string): string {
  if (!iso) {
    return 'unknown'
  }
  const ts = new Date(iso).getTime()
  if (!Number.isFinite(ts)) {
    return 'unknown'
  }
  const deltaSeconds = Math.max(0, Math.floor((Date.now() - ts) / 1000))
  if (deltaSeconds < 60) {
    return `${deltaSeconds}s ago`
  }
  if (deltaSeconds < 3600) {
    return `${Math.floor(deltaSeconds / 60)}m ago`
  }
  return `${Math.floor(deltaSeconds / 3600)}h ago`
}

function sumValues(value: Record<string, number> | undefined): number {
  if (!value) {
    return 0
  }
  return Object.values(value).reduce((acc, item) => acc + item, 0)
}

function statusTone(value: string): string {
  if (value === 'stable' || value === 'strong') {
    return '#166534'
  }
  if (value.includes('bounded')) {
    return '#92400e'
  }
  return '#991b1b'
}

function GlobalCommandCenter() {
  const { data, loading, error, lastUpdated } = useApiData<RuntimeOverview>(ENDPOINTS.runtimeOverview, {
    intervalMs: 10_000,
  })

  const websocket = data?.websocket?.payload
  const queue = data?.queue
  const replay = data?.replay
  const retry = data?.tasks?.retry_pressure
  const domainActivity = data?.tasks?.domain_activity || {}

  const totalActive = (queue?.P0_critical || 0) + (queue?.P1_normal || 0) + (queue?.P2_background || 0)
  const wsDrops = websocket?.sse_drop_total || 0
  const bufferEvictions = websocket?.buffer_evictions_total || 0
  const domainRows = Object.entries(domainActivity).sort((a, b) => b[1].total - a[1].total)

  return (
    <PageContainer>
      <PageHeader
        title="Runtime Operations Dashboard"
        subtitle="Evidence-backed operator view: queue pressure, replay integrity surfaces, governance flow, and coexistence signals."
      />

      <Grid min={220}>
        <StatusTile
          title="Operational Class"
          value={data?.classification?.operational || 'unknown'}
          detail="Derived from runtime pressure alerts"
          tone={statusTone(data?.classification?.operational || '')}
        />
        <StatusTile
          title="Determinism Class"
          value={data?.classification?.determinism || 'unknown'}
          detail="Current deterministic control-plane signal"
          tone={statusTone(data?.classification?.determinism || '')}
        />
        <StatusTile
          title="Queue Pressure"
          value={`${totalActive} queued`}
          detail={`P0=${queue?.P0_critical || 0}, P1=${queue?.P1_normal || 0}, P2=${queue?.P2_background || 0}`}
          tone={(queue?.starvation_events_total || 0) > 0 ? '#92400e' : '#0f766e'}
        />
        <StatusTile
          title="Replay Health"
          value={`finalized ${replay?.finalized || 0}`}
          detail={`mutable ${replay?.mutable || 0} (non-finalized traces)`}
          tone={(replay?.mutable || 0) > 0 ? '#92400e' : '#0f766e'}
        />
        <StatusTile
          title="Retry Activity"
          value={`${retry?.retry_pending_tasks || 0} pending`}
          detail={`lineage-bearing tasks ${retry?.tasks_with_retry_lineage || 0}`}
          tone={(retry?.retry_pending_tasks || 0) > 0 ? '#92400e' : '#0f766e'}
        />
        <StatusTile
          title="Websocket/SSE"
          value={data?.websocket?.available ? 'available' : 'unavailable'}
          detail={`drops ${wsDrops} | evictions ${bufferEvictions}`}
          tone={!data?.websocket?.available ? '#991b1b' : wsDrops > 0 || bufferEvictions > 0 ? '#92400e' : '#0f766e'}
        />
        <StatusTile
          title="Governance Flow"
          value={`${data?.governance?.approvals?.pending || 0} pending`}
          detail={`audit writes (1h) ${data?.governance?.audit_last_hour || 0}`}
          tone={(data?.governance?.approvals?.pending || 0) > 0 ? '#92400e' : '#0f766e'}
        />
        <StatusTile
          title="Last Snapshot"
          value={data?.generated_at ? formatSince(data.generated_at) : 'never'}
          detail={loading ? 'Refreshing…' : error || `UI fetch ${lastUpdated ? 'ok' : 'pending'}`}
          tone={error ? '#991b1b' : '#334155'}
        />
      </Grid>

      <div style={{ marginTop: '1rem' }}>
        <Grid>
          <SectionCard title="Operational Alert Surface">
            {error ? <MetaText>{error}</MetaText> : null}
            {!data?.pressure_alerts?.length ? (
              <MetaText>No active pressure alerts in latest snapshot.</MetaText>
            ) : (
              <div style={{ display: 'grid', gap: '0.45rem' }}>
                {data.pressure_alerts.map((alert, index) => (
                  <div key={`${alert.surface}-${index}`} style={alertRowStyle(alert.severity)}>
                    <strong style={{ fontSize: '0.82rem' }}>{alert.surface}</strong>
                    <MetaText>
                      severity={alert.severity} | {alert.message}
                    </MetaText>
                  </div>
                ))}
              </div>
            )}
          </SectionCard>

          <SectionCard title="Coexistence Pressure Snapshot">
            <MetaText>Domain ingest total: {sumValues(websocket?.domain_ingest_count)}</MetaText>
            <MetaText>Domain WS deliveries: {sumValues(websocket?.domain_ws_delivery_count)}</MetaText>
            <MetaText>Domain SSE deliveries: {sumValues(websocket?.domain_sse_delivery_count)}</MetaText>
            <MetaText>
              Replay buffer occupancy: {websocket?.event_buffer_size || 0}/{websocket?.event_buffer_capacity || 0}
            </MetaText>
            <MetaText>
              Fairness overrides: {queue?.fairness_overrides_total || 0} | Starvation events: {queue?.starvation_events_total || 0}
            </MetaText>
            <MetaText>WS metric source: {data?.websocket?.available ? 'ws-server /metrics/coexistence' : data?.websocket?.error || 'unavailable'}</MetaText>
          </SectionCard>
        </Grid>
      </div>

      <div style={{ marginTop: '1rem' }}>
        <SectionCard title="Plugin / Domain Activity">
          {domainRows.length === 0 ? (
            <MetaText>No domain-tagged task activity available yet.</MetaText>
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table style={tableStyle}>
                <thead>
                  <tr>
                    <th style={thStyle}>domain</th>
                    <th style={thStyle}>total</th>
                    <th style={thStyle}>running</th>
                    <th style={thStyle}>queued</th>
                    <th style={thStyle}>failed</th>
                    <th style={thStyle}>completed</th>
                  </tr>
                </thead>
                <tbody>
                  {domainRows.map(([domain, values]) => (
                    <tr key={domain}>
                      <td style={tdStyle}>{domain}</td>
                      <td style={tdStyle}>{values.total}</td>
                      <td style={tdStyle}>{values.running}</td>
                      <td style={tdStyle}>{values.queued}</td>
                      <td style={tdStyle}>{values.failed}</td>
                      <td style={tdStyle}>{values.completed}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </SectionCard>
      </div>

      <div style={{ marginTop: '1rem' }}>
        <SectionCard title="Operator Workflows">
          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
            <QuickLink to="/debug" label="Replay Explorer" />
            <QuickLink to="/governance" label="Governance Timeline" />
            <QuickLink to="/agents" label="Domain Observability" />
            <QuickLink to="/learning" label="Failure / Memory Ledgers" />
            <QuickLink to="/knowledge" label="Knowledge Context" />
          </div>
          <div style={{ marginTop: '0.65rem' }}>
            <MetaText>
              Architecture-aware UX mode: bounded guarantees are surfaced explicitly; non-guaranteed behavior is not hidden.
            </MetaText>
          </div>
        </SectionCard>
      </div>
    </PageContainer>
  )
}

function StatusTile({
  title,
  value,
  detail,
  tone,
}: {
  title: string
  value: string
  detail: string
  tone: string
}) {
  return (
    <div style={tileStyle}>
      <div style={{ fontSize: '0.72rem', color: '#64748b', textTransform: 'uppercase' }}>{title}</div>
      <div style={{ fontSize: '1.08rem', fontWeight: 700, marginTop: '0.2rem', color: tone }}>{value}</div>
      <MetaText>{detail}</MetaText>
    </div>
  )
}

function QuickLink({ to, label }: { to: string; label: string }) {
  return (
    <Link
      to={to}
      style={{
        textDecoration: 'none',
        color: '#0f172a',
        border: '1px solid #cbd5e1',
        borderRadius: '999px',
        padding: '0.35rem 0.8rem',
        background: '#f8fafc',
        fontSize: '0.82rem',
      }}
    >
      {label}
    </Link>
  )
}

function alertRowStyle(severity: string): React.CSSProperties {
  const color = severity === 'bounded' ? '#92400e' : severity === 'critical' ? '#991b1b' : '#334155'
  return {
    border: '1px solid #dbe3ec',
    borderRadius: '7px',
    padding: '0.5rem 0.6rem',
    background: '#f8fafc',
    color,
    display: 'grid',
    gap: '0.2rem',
  }
}

const tileStyle: React.CSSProperties = {
  background: '#fff',
  border: '1px solid #e2e8f0',
  borderRadius: '8px',
  padding: '0.85rem',
  boxShadow: '0 1px 2px rgba(0,0,0,0.04)',
}

const tableStyle: React.CSSProperties = {
  width: '100%',
  borderCollapse: 'collapse',
  fontSize: '0.82rem',
}

const thStyle: React.CSSProperties = {
  textAlign: 'left',
  padding: '0.5rem',
  borderBottom: '1px solid #dbe3ec',
  color: '#475569',
  textTransform: 'uppercase',
  fontSize: '0.72rem',
}

const tdStyle: React.CSSProperties = {
  padding: '0.5rem',
  borderBottom: '1px solid #eef2f7',
}

export default GlobalCommandCenter
