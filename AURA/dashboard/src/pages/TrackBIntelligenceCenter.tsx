import { useMemo, type CSSProperties } from 'react'
import { API_ROUTES } from '../config'
import { useApiData } from '../hooks/useApiData'
import { Grid, MetaText, PageContainer, PageHeader, SectionCard } from '../components/PagePrimitives'

interface IntelResponse {
  payload: Record<string, unknown>
  generated_at: string
}

function asRecord(value: unknown): Record<string, unknown> {
  if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
    return value as Record<string, unknown>
  }
  return {}
}

function asArray<T>(value: unknown): T[] {
  if (Array.isArray(value)) {
    return value as T[]
  }
  return []
}

function asNumber(value: unknown): number {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value
  }
  if (typeof value === 'string') {
    const parsed = Number(value)
    if (Number.isFinite(parsed)) {
      return parsed
    }
  }
  return 0
}

function asString(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function formatPercent(value: number): string {
  return `${value.toFixed(2)}%`
}

export default function TrackBIntelligenceCenter() {
  const overview = useApiData<IntelResponse>(API_ROUTES.trackBIntel.overview(), { intervalMs: 30_000 })
  const trends = useApiData<IntelResponse>(API_ROUTES.trackBIntel.trends(), { intervalMs: 30_000 })
  const patterns = useApiData<IntelResponse>(API_ROUTES.trackBIntel.patterns(), { intervalMs: 30_000 })
  const recommendations = useApiData<IntelResponse>(API_ROUTES.trackBIntel.recommendations(), { intervalMs: 30_000 })
  const learning = useApiData<IntelResponse>(API_ROUTES.trackBIntel.learning(), { intervalMs: 30_000 })
  const executive = useApiData<IntelResponse>(API_ROUTES.trackBIntel.executive(), { intervalMs: 30_000 })
  const forecast = useApiData<IntelResponse>(API_ROUTES.trackBIntel.forecast(), { intervalMs: 30_000 })

  const execPayload = asRecord(executive.data?.payload)
  const forecastPayload = asRecord(forecast.data?.payload)
  const trendsPayload = asRecord(trends.data?.payload)
  const auditTrend = asArray<Record<string, unknown>>(trendsPayload.audit_trend)
  const readinessTrend = asArray<Record<string, unknown>>(trendsPayload.readiness_trend)
  const learningTrend = asArray<Record<string, unknown>>(trendsPayload.learning_trend)
  const patternPayload = asRecord(patterns.data?.payload)
  const recommendationsPayload = asRecord(recommendations.data?.payload)
  const learningPayload = asRecord(learning.data?.payload)
  const clusters = asArray<Record<string, unknown>>(learningPayload.clusters)
  const rankedLessons = asArray<Record<string, unknown>>(learningPayload.ranked_lessons)

  const topRecommendations = useMemo(
    () => asArray<Record<string, unknown>>(recommendationsPayload.recommendations).slice(0, 20),
    [recommendationsPayload],
  )

  return (
    <PageContainer>
      <PageHeader
        title="Track-B Intelligence Center (M10)"
        subtitle="Cross-release analytics, pattern mining, recommendations, and forecasting over M8/M9 artifacts."
      />

      <Grid min={260}>
        <SectionCard
          title="Executive Health"
          action={
            <button style={buttonStyle} onClick={() => void executive.reload()} disabled={executive.loading}>
              {executive.loading ? 'Refreshing...' : 'Refresh'}
            </button>
          }
        >
          <MetaText>project_health={formatPercent(asNumber(execPayload.project_health))}</MetaText>
          <MetaText>release_health={asString(execPayload.release_health) || 'UNKNOWN'}</MetaText>
          <MetaText>audit_health={asString(execPayload.audit_health) || 'UNKNOWN'}</MetaText>
          <MetaText>blocker_count={asNumber(execPayload.blocker_count)}</MetaText>
          <MetaText>open_conflicts={asNumber(execPayload.open_conflict_count)}</MetaText>
          <MetaText>dependency_coverage={formatPercent(asNumber(execPayload.dependency_coverage_percent))}</MetaText>
          <MetaText>evidence_completeness={formatPercent(asNumber(execPayload.evidence_completeness_percent))}</MetaText>
        </SectionCard>

        <SectionCard
          title="Readiness Forecast"
          action={
            <button style={buttonStyle} onClick={() => void forecast.reload()} disabled={forecast.loading}>
              {forecast.loading ? 'Refreshing...' : 'Refresh'}
            </button>
          }
        >
          <MetaText>probability={formatPercent(asNumber(forecastPayload.readiness_probability_percent))}</MetaText>
          <MetaText>risk_level={asString(forecastPayload.risk_level) || 'UNKNOWN'}</MetaText>
          <MetaText>remaining_work_estimate={asNumber(forecastPayload.remaining_work_estimate)}</MetaText>
          <MetaText>sample_count={asNumber(forecastPayload.sample_count)}</MetaText>
        </SectionCard>

        <SectionCard
          title="Pattern Mining"
          action={
            <button style={buttonStyle} onClick={() => void patterns.reload()} disabled={patterns.loading}>
              {patterns.loading ? 'Refreshing...' : 'Refresh'}
            </button>
          }
        >
          <MetaText>recurring_failures={asArray(patternPayload.recurring_failures).length}</MetaText>
          <MetaText>dependency_issues={asArray(patternPayload.recurring_dependency_issues).length}</MetaText>
          <MetaText>conflict_categories={asArray(patternPayload.recurring_conflict_categories).length}</MetaText>
          <MetaText>readiness_blockers={asArray(patternPayload.repeated_readiness_blockers).length}</MetaText>
        </SectionCard>
      </Grid>

      <div style={{ marginTop: '1rem' }}>
        <Grid min={360}>
          <SectionCard
            title="Release & Readiness Trends"
            action={
              <button style={buttonStyle} onClick={() => void trends.reload()} disabled={trends.loading}>
                {trends.loading ? 'Refreshing...' : 'Refresh'}
              </button>
            }
          >
            <MetaText>audit_trend_entries={auditTrend.length}</MetaText>
            <MetaText>readiness_trend_entries={readinessTrend.length}</MetaText>
            <MetaText>learning_trend_entries={learningTrend.length}</MetaText>
            <div style={tableWrapStyle}>
              <table style={tableStyle}>
                <thead>
                  <tr>
                    <th style={thStyle}>Audit</th>
                    <th style={thStyle}>Completion</th>
                    <th style={thStyle}>Readiness</th>
                    <th style={thStyle}>Blockers</th>
                  </tr>
                </thead>
                <tbody>
                  {auditTrend.slice(0, 10).map((row) => (
                    <tr key={asString(row.audit_id)}>
                      <td style={tdStyle}>{asString(row.audit_id)}</td>
                      <td style={tdStyle}>{formatPercent(asNumber(row.completion_percent))}</td>
                      <td style={tdStyle}>{formatPercent(asNumber(row.production_readiness_percent))}</td>
                      <td style={tdStyle}>{asNumber(row.blocker_count)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </SectionCard>

          <SectionCard
            title="Recommendations"
            action={
              <button style={buttonStyle} onClick={() => void recommendations.reload()} disabled={recommendations.loading}>
                {recommendations.loading ? 'Refreshing...' : 'Refresh'}
              </button>
            }
          >
            <MetaText>recommendation_count={asArray(recommendationsPayload.recommendations).length}</MetaText>
            <div style={tableWrapStyle}>
              <table style={tableStyle}>
                <thead>
                  <tr>
                    <th style={thStyle}>Type</th>
                    <th style={thStyle}>Component</th>
                    <th style={thStyle}>Summary</th>
                  </tr>
                </thead>
                <tbody>
                  {topRecommendations.map((rec, index) => (
                    <tr key={`${asString(rec.recommendation_type)}-${index}`}>
                      <td style={tdStyle}>{asString(rec.recommendation_type)}</td>
                      <td style={tdStyle}>{asString(rec.component)}</td>
                      <td style={tdStyle}>{asString(rec.summary)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </SectionCard>
        </Grid>
      </div>

      <div style={{ marginTop: '1rem' }}>
        <Grid min={360}>
          <SectionCard
            title="Learning Trends"
            action={
              <button style={buttonStyle} onClick={() => void trends.reload()} disabled={trends.loading}>
                {trends.loading ? 'Refreshing...' : 'Refresh'}
              </button>
            }
          >
            <MetaText>learning_releases={learningTrend.length}</MetaText>
            <div style={tableWrapStyle}>
              <table style={tableStyle}>
                <thead>
                  <tr>
                    <th style={thStyle}>Release</th>
                    <th style={thStyle}>Total Lessons</th>
                    <th style={thStyle}>Entry Types</th>
                  </tr>
                </thead>
                <tbody>
                  {learningTrend.slice(0, 10).map((row) => (
                    <tr key={asString(row.release_tag)}>
                      <td style={tdStyle}>{asString(row.release_tag)}</td>
                      <td style={tdStyle}>{asNumber(row.total_lessons)}</td>
                      <td style={tdStyle}>
                        {asArray<Record<string, unknown>>(row.entry_type_counts)
                          .map((entry) => `${asString(entry.entry_type)}:${asNumber(entry.count)}`)
                          .join(', ')}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </SectionCard>

          <SectionCard
            title="Ranked Lessons"
            action={
              <button style={buttonStyle} onClick={() => void learning.reload()} disabled={learning.loading}>
                {learning.loading ? 'Refreshing...' : 'Refresh'}
              </button>
            }
          >
            <MetaText>ranked_lessons={rankedLessons.length}</MetaText>
            <div style={tableWrapStyle}>
              <table style={tableStyle}>
                <thead>
                  <tr>
                    <th style={thStyle}>Cluster</th>
                    <th style={thStyle}>Score</th>
                    <th style={thStyle}>Count</th>
                    <th style={thStyle}>Recurrence</th>
                  </tr>
                </thead>
                <tbody>
                  {rankedLessons.slice(0, 12).map((lesson) => (
                    <tr key={`${asString(lesson.entry_type)}-${asString(lesson.cluster_key)}`}>
                      <td style={tdStyle}>{asString(lesson.cluster_key)}</td>
                      <td style={tdStyle}>{asNumber(lesson.usefulness_score).toFixed(2)}</td>
                      <td style={tdStyle}>{asNumber(lesson.count)}</td>
                      <td style={tdStyle}>{asNumber(lesson.recurrence)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </SectionCard>
        </Grid>
      </div>

      <div style={{ marginTop: '1rem' }}>
        <Grid min={360}>
          <SectionCard
            title="Learning Intelligence"
            action={
              <button style={buttonStyle} onClick={() => void learning.reload()} disabled={learning.loading}>
                {learning.loading ? 'Refreshing...' : 'Refresh'}
              </button>
            }
          >
            <MetaText>total_lessons={asNumber(learningPayload.total_lessons)}</MetaText>
            <MetaText>clusters={clusters.length}</MetaText>
            <MetaText>stale_clusters={asArray(learningPayload.stale_clusters).length}</MetaText>
            <div style={tableWrapStyle}>
              <table style={tableStyle}>
                <thead>
                  <tr>
                    <th style={thStyle}>Entry Type</th>
                    <th style={thStyle}>Cluster Key</th>
                    <th style={thStyle}>Count</th>
                  </tr>
                </thead>
                <tbody>
                  {clusters.slice(0, 12).map((cluster) => (
                    <tr key={`${asString(cluster.entry_type)}-${asString(cluster.cluster_key)}`}>
                      <td style={tdStyle}>{asString(cluster.entry_type)}</td>
                      <td style={tdStyle}>{asString(cluster.cluster_key)}</td>
                      <td style={tdStyle}>{asNumber(cluster.count)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </SectionCard>

          <SectionCard
            title="Overview Snapshot"
            action={
              <button style={buttonStyle} onClick={() => void overview.reload()} disabled={overview.loading}>
                {overview.loading ? 'Refreshing...' : 'Refresh'}
              </button>
            }
          >
            <MetaText>classification={asString(overview.data?.payload?.classification) || 'UNKNOWN'}</MetaText>
            <MetaText>generated_at={asString(overview.data?.payload?.generated_at)}</MetaText>
            <MetaText>trend_ready={Boolean(overview.data?.payload?.trends) ? 'yes' : 'no'}</MetaText>
            <MetaText>patterns_ready={Boolean(overview.data?.payload?.patterns) ? 'yes' : 'no'}</MetaText>
            <MetaText>recommendations_ready={Boolean(overview.data?.payload?.recommendations) ? 'yes' : 'no'}</MetaText>
            <MetaText>learning_ready={Boolean(overview.data?.payload?.learning) ? 'yes' : 'no'}</MetaText>
          </SectionCard>
        </Grid>
      </div>
    </PageContainer>
  )
}

const buttonStyle: CSSProperties = {
  border: '1px solid #d1d5db',
  borderRadius: '6px',
  padding: '0.35rem 0.65rem',
  cursor: 'pointer',
  background: '#fff',
}

const tableWrapStyle: CSSProperties = {
  marginTop: '0.55rem',
  maxHeight: '260px',
  overflow: 'auto',
}

const tableStyle: CSSProperties = {
  width: '100%',
  borderCollapse: 'collapse',
  fontSize: '0.82rem',
}

const thStyle: CSSProperties = {
  textAlign: 'left',
  borderBottom: '1px solid #e5e7eb',
  padding: '0.38rem',
  background: '#f8fafc',
}

const tdStyle: CSSProperties = {
  padding: '0.38rem',
  borderBottom: '1px solid #f1f5f9',
  verticalAlign: 'top',
}
