import { useApiData } from '../hooks/useApiData'
import { ErrorText, JsonBlock, MetaText, SectionCard, formatTimestamp } from './PagePrimitives'

export function DataPanel({
  title,
  endpoint,
  intervalMs = 0,
  includeAuth = true,
}: {
  title: string
  endpoint: string
  intervalMs?: number
  includeAuth?: boolean
}) {
  const { data, loading, error, lastUpdated, reload } = useApiData(endpoint, { intervalMs, includeAuth })

  return (
    <SectionCard
      title={title}
      action={(
        <button style={buttonStyle} onClick={() => void reload()} disabled={loading}>
          {loading ? 'Loading...' : 'Refresh'}
        </button>
      )}
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
        <MetaText>Endpoint: {endpoint}</MetaText>
        {error ? <ErrorText message={error} /> : null}
        {data ? <JsonBlock data={data} /> : <MetaText>{loading ? 'Loading...' : 'No data yet'}</MetaText>}
        <MetaText>Last update: {formatTimestamp(lastUpdated)}</MetaText>
      </div>
    </SectionCard>
  )
}

const buttonStyle: React.CSSProperties = {
  border: '1px solid #d1d5db',
  borderRadius: '6px',
  padding: '0.35rem 0.65rem',
  cursor: 'pointer',
  background: '#fff',
}
