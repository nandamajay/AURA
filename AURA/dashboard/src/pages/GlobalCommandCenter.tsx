import { Link } from 'react-router-dom'
import { ENDPOINTS } from '../config'
import { useApiData } from '../hooks/useApiData'
import { Grid, MetaText, PageContainer, PageHeader, SectionCard } from '../components/PagePrimitives'

interface HealthStatus {
  status: string
  version: string
  uptime_seconds: number
  components?: Array<{ name: string; status: string; latency_ms: number }>
}

function GlobalCommandCenter() {
  const { data, loading, error, lastUpdated } = useApiData<HealthStatus>(ENDPOINTS.health, {
    includeAuth: false,
    intervalMs: 30_000,
  })

  return (
    <PageContainer>
      <PageHeader
        title="Global Command Center"
        subtitle="Central control for the Audio Upstream Refactor Agent platform"
      />

      <Grid min={220}>
        <StatusTile title="System" value={data?.status || 'unknown'} detail={error || 'Core readiness'} />
        <StatusTile title="Version" value={data?.version || 'n/a'} detail="Core release" />
        <StatusTile title="Uptime" value={formatUptime(data?.uptime_seconds || 0)} detail="Service uptime" />
        <StatusTile
          title="Last Check"
          value={loading ? 'updating' : 'ok'}
          detail={lastUpdated ? new Date(lastUpdated).toLocaleTimeString() : 'not yet'}
        />
      </Grid>

      <div style={{ marginTop: '1rem' }}>
        <SectionCard title="Service Health Components">
          {data?.components?.length ? (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))', gap: '0.75rem' }}>
              {data.components.map((component) => (
                <div key={component.name} style={chipStyle}>
                  <strong>{component.name}</strong>
                  <MetaText>
                    status={component.status} latency={component.latency_ms}ms
                  </MetaText>
                </div>
              ))}
            </div>
          ) : (
            <MetaText>{error || 'No component data returned yet.'}</MetaText>
          )}
        </SectionCard>
      </div>

      <div style={{ marginTop: '1rem' }}>
        <SectionCard title="Quick Navigation">
          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
            <QuickLink to="/migration" label="Driver Migration Center" />
            <QuickLink to="/agents" label="Live Agent Observability" />
            <QuickLink to="/knowledge" label="Knowledge Graph Center" />
            <QuickLink to="/simulation" label="Simulation Control Center" />
            <QuickLink to="/approvals" label="Approval Operations" />
            <QuickLink to="/governance" label="Governance Command Center" />
          </div>
        </SectionCard>
      </div>
    </PageContainer>
  )
}

function StatusTile({ title, value, detail }: { title: string; value: string; detail: string }) {
  return (
    <div style={tileStyle}>
      <div style={{ fontSize: '0.74rem', color: '#64748b', textTransform: 'uppercase' }}>{title}</div>
      <div style={{ fontSize: '1.15rem', fontWeight: 600, marginTop: '0.2rem' }}>{value}</div>
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
        fontSize: '0.84rem',
      }}
    >
      {label}
    </Link>
  )
}

const tileStyle: React.CSSProperties = {
  background: '#fff',
  border: '1px solid #e2e8f0',
  borderRadius: '8px',
  padding: '0.9rem',
  boxShadow: '0 1px 2px rgba(0,0,0,0.04)',
}

const chipStyle: React.CSSProperties = {
  border: '1px solid #e2e8f0',
  borderRadius: '8px',
  padding: '0.6rem',
  background: '#f8fafc',
}

function formatUptime(seconds: number): string {
  const totalMinutes = Math.floor(seconds / 60)
  const days = Math.floor(totalMinutes / (60 * 24))
  const hours = Math.floor((totalMinutes % (60 * 24)) / 60)
  const minutes = totalMinutes % 60
  if (days > 0) {
    return `${days}d ${hours}h`
  }
  if (hours > 0) {
    return `${hours}h ${minutes}m`
  }
  return `${minutes}m`
}

export default GlobalCommandCenter
