import { useMemo, useState, type CSSProperties } from 'react'
import { API_ROUTES } from '../config'
import { useApiData } from '../hooks/useApiData'
import { Grid, MetaText, PageContainer, PageHeader, SectionCard } from '../components/PagePrimitives'

interface ValidationIssue {
  code: string
  message: string
  severity: string
}

interface ContractValidation {
  valid: boolean
  issues: ValidationIssue[]
}

interface SummaryResponse {
  payload: Record<string, unknown>
  generated_at: string
  validation?: ContractValidation
}

interface ArtifactMetadata {
  artifact_id: string
  artifact_name: string
  artifact_file: string
  component: string
  classification: string
  decision_state: string
  readiness_status: string
  task_id: string
  modified_at: string
}

interface ArtifactRecord {
  metadata: ArtifactMetadata
  validation: ContractValidation
}

interface ArtifactIndexResponse {
  artifacts: ArtifactRecord[]
  pagination: {
    total: number
    page: number
    limit: number
  }
  validation: ContractValidation
}

interface LineageNode {
  node_id: string
  node_type: string
  label: string
}

interface LineageEdge {
  from_id: string
  to_id: string
  relation: string
}

interface LineageResponse {
  nodes: LineageNode[]
  edges: LineageEdge[]
  validation: ContractValidation
}

interface SearchResponse {
  query: string
  kind: string
  total: number
  results: Array<{
    kind: string
    id: string
    title: string
    summary: string
    path: string
  }>
}

interface LearningResponse {
  learning_entries: Array<{
    entry_id: string
    entry_type: string
    title: string
    path: string
    classification: string
    schema_version: string
  }>
  pagination: {
    total: number
  }
}

interface ReadinessHistoryRow {
  artifact_id: string
  component: string
  decision_state: string
  readiness_status: string
  classification: string
  score_percent: number
  modified_at: string
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

function formatPercent(value: number): string {
  return `${value.toFixed(2)}%`
}

function formatTime(value: string): string {
  if (!value) {
    return 'n/a'
  }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }
  return date.toLocaleString()
}

function statusTone(classification: string): CSSProperties {
  const text = classification.toUpperCase()
  if (text.includes('PASS')) {
    return { background: '#ecfdf3', color: '#166534', border: '1px solid #86efac' }
  }
  if (text.includes('WARN')) {
    return { background: '#fffbeb', color: '#92400e', border: '1px solid #fde68a' }
  }
  return { background: '#fef2f2', color: '#991b1b', border: '1px solid #fecaca' }
}

function StatusPill({ value }: { value: string }) {
  return (
    <span
      style={{
        ...statusTone(value),
        display: 'inline-flex',
        borderRadius: '999px',
        padding: '0.18rem 0.55rem',
        fontSize: '0.75rem',
        fontWeight: 700,
      }}
    >
      {value || 'UNKNOWN'}
    </span>
  )
}

function MetricRow({ label, value }: { label: string; value: string | number }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.8rem', fontSize: '0.85rem' }}>
      <span style={{ color: '#334155' }}>{label}</span>
      <strong>{value}</strong>
    </div>
  )
}

export default function TrackBVisibilityCenter() {
  const [componentQuery, setComponentQuery] = useState('q6apm_dai_prepare')
  const [reverseNodeId, setReverseNodeId] = useState('')
  const [searchQuery, setSearchQuery] = useState('q6apm_dai_prepare')
  const [searchKind, setSearchKind] = useState('')

  const releaseSummary = useApiData<SummaryResponse>(API_ROUTES.trackB.dashboardReleaseSummary(), { intervalMs: 20_000 })
  const readiness = useApiData<SummaryResponse>(API_ROUTES.trackB.dashboardReadiness(), { intervalMs: 20_000 })
  const readinessHistory = useApiData<SummaryResponse>(API_ROUTES.trackB.dashboardReadinessHistory(), { intervalMs: 20_000 })
  const dependencyCoverage = useApiData<SummaryResponse>(API_ROUTES.trackB.dashboardDependencyCoverage(), { intervalMs: 20_000 })
  const conflictOverview = useApiData<SummaryResponse>(API_ROUTES.trackB.dashboardConflicts(), { intervalMs: 20_000 })
  const equivalenceOverview = useApiData<SummaryResponse>(API_ROUTES.trackB.dashboardEquivalence(), { intervalMs: 20_000 })
  const auditHistory = useApiData<SummaryResponse>(API_ROUTES.trackB.dashboardAuditHistory(100), { intervalMs: 30_000 })
  const releaseHistory = useApiData<SummaryResponse>(API_ROUTES.trackB.dashboardReleaseHistory(100), { intervalMs: 30_000 })
  const artifactsIndex = useApiData<ArtifactIndexResponse>(
    API_ROUTES.trackB.artifactsIndexQuery(100, 1, '', '', '', '', '', '', componentQuery),
    { intervalMs: 30_000 },
  )
  const lineage = useApiData<LineageResponse>(
    API_ROUTES.trackB.lineageQuery(componentQuery, reverseNodeId, true, true),
    { intervalMs: 20_000 },
  )
  const learning = useApiData<LearningResponse>(API_ROUTES.trackB.learningIndexQuery(120, 1), { intervalMs: 30_000 })
  const learningPatterns = useApiData<{ payload: Record<string, unknown> }>(API_ROUTES.trackB.learningPatterns(), { intervalMs: 30_000 })
  const search = useApiData<SearchResponse>(API_ROUTES.trackB.search(searchQuery, searchKind, 120), { intervalMs: 15_000 })

  const readinessPayload = readiness.data?.payload || {}
  const conflictPayload = conflictOverview.data?.payload || {}
  const equivalencePayload = equivalenceOverview.data?.payload || {}
  const releasePayload = releaseSummary.data?.payload || {}
  const readinessHistoryRows = asArray<ReadinessHistoryRow>(readinessHistory.data?.payload?.history)
  const dependencyRows = useMemo(() => {
    const coverage = asRecord(dependencyCoverage.data?.payload?.coverage)
    return Object.keys(coverage)
      .sort()
      .map((key) => {
        const node = asRecord(coverage[key])
        return {
          bucket: key,
          resolved: asNumber(node.resolved),
          total: asNumber(node.total),
          coveragePercent: asNumber(node.coverage_percent),
        }
      })
  }, [dependencyCoverage.data?.payload?.coverage])
  const conflictRows = asArray<Record<string, unknown>>(conflictPayload.categories).map((row) => ({
    category: asString(row.category),
    count: asNumber(row.count),
  }))
  const equivalenceStates = asRecord(equivalencePayload.states)

  return (
    <PageContainer>
      <PageHeader
        title="Track-B Visibility Center (M9)"
        subtitle="Deterministic visibility for M8 upstreaming artifacts: dashboard, lineage, readiness, learning ingestion, and search."
      />

      <Grid min={260}>
        <SectionCard
          title="Release Summary"
          action={
            <button style={buttonStyle} onClick={() => void releaseSummary.reload()} disabled={releaseSummary.loading}>
              {releaseSummary.loading ? 'Refreshing...' : 'Refresh'}
            </button>
          }
        >
          <StatusPill value={asString(releasePayload.classification)} />
          <div style={metricListStyle}>
            <MetricRow label="Release Tag" value={asString(releasePayload.release_tag) || 'n/a'} />
            <MetricRow label="Schema Version" value={asString(releasePayload.schema_version) || 'n/a'} />
            <MetricRow label="Audit Status" value={asString(releasePayload.audit_status) || 'n/a'} />
            <MetricRow label="Release Count" value={asNumber(releasePayload.release_count)} />
            <MetricRow label="Audit Count" value={asNumber(releasePayload.audit_count)} />
          </div>
          {releaseSummary.error ? <MetaText>{releaseSummary.error}</MetaText> : null}
        </SectionCard>

        <SectionCard
          title="Readiness"
          action={
            <button style={buttonStyle} onClick={() => void readiness.reload()} disabled={readiness.loading}>
              {readiness.loading ? 'Refreshing...' : 'Refresh'}
            </button>
          }
        >
          <StatusPill value={asString(readinessPayload.classification)} />
          <div style={metricListStyle}>
            <MetricRow label="Completion" value={formatPercent(asNumber(readinessPayload.completion_percent))} />
            <MetricRow label="Production Readiness" value={formatPercent(asNumber(readinessPayload.production_readiness_percent))} />
            <MetricRow label="Blockers" value={asNumber(readinessPayload.blocker_count)} />
            <MetricRow label="Fail-Closed Count" value={asNumber(readinessPayload.fail_closed_count)} />
            <MetricRow label="Dependency Coverage" value={formatPercent(asNumber(readinessPayload.dependency_coverage_percent))} />
            <MetricRow label="Open Conflicts" value={asNumber(readinessPayload.open_conflict_count)} />
            <MetricRow label="Evidence Completeness" value={formatPercent(asNumber(readinessPayload.evidence_completeness_percent))} />
            <MetricRow label="Audit Health" value={asString(readinessPayload.audit_health) || 'UNKNOWN'} />
            <MetricRow label="Release Health" value={asString(readinessPayload.release_health) || 'UNKNOWN'} />
          </div>
          {readiness.error ? <MetaText>{readiness.error}</MetaText> : null}
        </SectionCard>

        <SectionCard
          title="Dependency Coverage"
          action={
            <button style={buttonStyle} onClick={() => void dependencyCoverage.reload()} disabled={dependencyCoverage.loading}>
              {dependencyCoverage.loading ? 'Refreshing...' : 'Refresh'}
            </button>
          }
        >
          <table style={tableStyle}>
            <thead>
              <tr>
                <th style={thStyle}>Bucket</th>
                <th style={thStyle}>Resolved</th>
                <th style={thStyle}>Total</th>
                <th style={thStyle}>Coverage</th>
              </tr>
            </thead>
            <tbody>
              {dependencyRows.map((row) => (
                <tr key={row.bucket}>
                  <td style={tdStyle}>{row.bucket}</td>
                  <td style={tdStyle}>{row.resolved}</td>
                  <td style={tdStyle}>{row.total}</td>
                  <td style={tdStyle}>{formatPercent(row.coveragePercent)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {dependencyCoverage.error ? <MetaText>{dependencyCoverage.error}</MetaText> : null}
        </SectionCard>

        <SectionCard
          title="Conflict Overview"
          action={
            <button style={buttonStyle} onClick={() => void conflictOverview.reload()} disabled={conflictOverview.loading}>
              {conflictOverview.loading ? 'Refreshing...' : 'Refresh'}
            </button>
          }
        >
          <div style={metricListStyle}>
            <MetricRow label="Open Conflicts" value={asNumber(conflictPayload.open_conflicts)} />
            <MetricRow label="Resolved Conflicts" value={asNumber(conflictPayload.resolved_conflicts)} />
          </div>
          <table style={tableStyle}>
            <thead>
              <tr>
                <th style={thStyle}>Category</th>
                <th style={thStyle}>Count</th>
              </tr>
            </thead>
            <tbody>
              {conflictRows.map((row) => (
                <tr key={row.category}>
                  <td style={tdStyle}>{row.category}</td>
                  <td style={tdStyle}>{row.count}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {conflictOverview.error ? <MetaText>{conflictOverview.error}</MetaText> : null}
        </SectionCard>

        <SectionCard
          title="Equivalence Overview"
          action={
            <button style={buttonStyle} onClick={() => void equivalenceOverview.reload()} disabled={equivalenceOverview.loading}>
              {equivalenceOverview.loading ? 'Refreshing...' : 'Refresh'}
            </button>
          }
        >
          <div style={metricListStyle}>
            <MetricRow label="UNIQUE_EQUIVALENT" value={asNumber(equivalenceStates.UNIQUE_EQUIVALENT)} />
            <MetricRow label="MULTI_EQUIVALENT" value={asNumber(equivalenceStates.MULTI_EQUIVALENT)} />
            <MetricRow label="NO_EQUIVALENT" value={asNumber(equivalenceStates.NO_EQUIVALENT)} />
            <MetricRow label="CONFLICTING_EVIDENCE" value={asNumber(equivalenceStates.CONFLICTING_EVIDENCE)} />
          </div>
          {equivalenceOverview.error ? <MetaText>{equivalenceOverview.error}</MetaText> : null}
        </SectionCard>
      </Grid>

      <div style={{ marginTop: '1rem' }}>
        <Grid min={320}>
          <SectionCard
            title="Readiness Trend"
            action={
              <button style={buttonStyle} onClick={() => void readinessHistory.reload()} disabled={readinessHistory.loading}>
                {readinessHistory.loading ? 'Refreshing...' : 'Refresh'}
              </button>
            }
          >
            <MetaText>Rows: {readinessHistoryRows.length}</MetaText>
            <div style={tableWrapStyle}>
              <table style={tableStyle}>
                <thead>
                  <tr>
                    <th style={thStyle}>Component</th>
                    <th style={thStyle}>Decision</th>
                    <th style={thStyle}>Readiness</th>
                    <th style={thStyle}>Score</th>
                    <th style={thStyle}>Updated</th>
                  </tr>
                </thead>
                <tbody>
                  {readinessHistoryRows.slice(0, 20).map((row) => (
                    <tr key={row.artifact_id}>
                      <td style={tdStyle}>{row.component}</td>
                      <td style={tdStyle}>{row.decision_state}</td>
                      <td style={tdStyle}>{row.readiness_status}</td>
                      <td style={tdStyle}>{formatPercent(row.score_percent)}</td>
                      <td style={tdStyle}>{formatTime(row.modified_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </SectionCard>

          <SectionCard
            title="Audit History"
            action={
              <button style={buttonStyle} onClick={() => void auditHistory.reload()} disabled={auditHistory.loading}>
                {auditHistory.loading ? 'Refreshing...' : 'Refresh'}
              </button>
            }
          >
            <MetaText>Total: {asNumber(auditHistory.data?.payload?.total)}</MetaText>
            <div style={tableWrapStyle}>
              <table style={tableStyle}>
                <thead>
                  <tr>
                    <th style={thStyle}>Artifact</th>
                    <th style={thStyle}>Classification</th>
                    <th style={thStyle}>Schema</th>
                  </tr>
                </thead>
                <tbody>
                  {asArray<Record<string, unknown>>(auditHistory.data?.payload?.audits)
                    .slice(0, 20)
                    .map((audit) => (
                      <tr key={asString(audit.audit_id)}>
                        <td style={tdStyle}>{asString(audit.artifact_name)}</td>
                        <td style={tdStyle}>{asString(audit.classification)}</td>
                        <td style={tdStyle}>{asString(audit.schema_version)}</td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          </SectionCard>

          <SectionCard
            title="Release History"
            action={
              <button style={buttonStyle} onClick={() => void releaseHistory.reload()} disabled={releaseHistory.loading}>
                {releaseHistory.loading ? 'Refreshing...' : 'Refresh'}
              </button>
            }
          >
            <MetaText>Total: {asNumber(releaseHistory.data?.payload?.total)}</MetaText>
            <div style={tableWrapStyle}>
              <table style={tableStyle}>
                <thead>
                  <tr>
                    <th style={thStyle}>Tag</th>
                    <th style={thStyle}>Schema Status</th>
                    <th style={thStyle}>Audit Status</th>
                  </tr>
                </thead>
                <tbody>
                  {asArray<Record<string, unknown>>(releaseHistory.data?.payload?.releases)
                    .slice(0, 20)
                    .map((release) => (
                      <tr key={asString(release.release_tag)}>
                        <td style={tdStyle}>{asString(release.release_tag)}</td>
                        <td style={tdStyle}>{asString(release.schema_status)}</td>
                        <td style={tdStyle}>{asString(release.audit_status)}</td>
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
            title="Lineage Navigation"
            action={
              <button style={buttonStyle} onClick={() => void lineage.reload()} disabled={lineage.loading}>
                {lineage.loading ? 'Refreshing...' : 'Refresh'}
              </button>
            }
          >
            <div style={controlRowStyle}>
              <input
                style={inputStyle}
                value={componentQuery}
                onChange={(event) => setComponentQuery(event.target.value)}
                placeholder="component query"
              />
              <input
                style={inputStyle}
                value={reverseNodeId}
                onChange={(event) => setReverseNodeId(event.target.value)}
                placeholder="reverse node id (optional)"
              />
            </div>
            <MetaText>
              nodes={lineage.data?.nodes.length || 0} edges={lineage.data?.edges.length || 0}
            </MetaText>
            <div style={tableWrapStyle}>
              <table style={tableStyle}>
                <thead>
                  <tr>
                    <th style={thStyle}>Node</th>
                    <th style={thStyle}>Type</th>
                    <th style={thStyle}>Label</th>
                  </tr>
                </thead>
                <tbody>
                  {(lineage.data?.nodes || []).slice(0, 25).map((node) => (
                    <tr key={node.node_id}>
                      <td style={tdStyle}>
                        <button style={linkButtonStyle} onClick={() => setReverseNodeId(node.node_id)}>
                          {node.node_id}
                        </button>
                      </td>
                      <td style={tdStyle}>{node.node_type}</td>
                      <td style={tdStyle}>{node.label}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {lineage.data && !lineage.data.validation.valid ? (
              <MetaText>Lineage validation errors: {lineage.data.validation.issues.map((issue) => issue.code).join(', ')}</MetaText>
            ) : null}
          </SectionCard>

          <SectionCard
            title="Search & Discovery"
            action={
              <button style={buttonStyle} onClick={() => void search.reload()} disabled={search.loading}>
                {search.loading ? 'Searching...' : 'Search'}
              </button>
            }
          >
            <div style={controlRowStyle}>
              <input
                style={inputStyle}
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
                placeholder="component / symbol / conflict / audit / release / lesson / readiness"
              />
              <select style={inputStyle} value={searchKind} onChange={(event) => setSearchKind(event.target.value)}>
                <option value="">all kinds</option>
                <option value="artifact">artifact</option>
                <option value="audit">audit</option>
                <option value="release">release</option>
                <option value="lesson">lesson</option>
              </select>
            </div>
            <MetaText>Results: {search.data?.total || 0}</MetaText>
            <div style={tableWrapStyle}>
              <table style={tableStyle}>
                <thead>
                  <tr>
                    <th style={thStyle}>Kind</th>
                    <th style={thStyle}>Title</th>
                    <th style={thStyle}>Summary</th>
                  </tr>
                </thead>
                <tbody>
                  {(search.data?.results || []).slice(0, 30).map((row) => (
                    <tr key={`${row.kind}-${row.id}`}>
                      <td style={tdStyle}>{row.kind}</td>
                      <td style={tdStyle}>{row.title}</td>
                      <td style={tdStyle}>{row.summary}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {search.error ? <MetaText>{search.error}</MetaText> : null}
          </SectionCard>
        </Grid>
      </div>

      <div style={{ marginTop: '1rem' }}>
        <Grid min={360}>
          <SectionCard
            title="Artifact Inventory"
            action={
              <button style={buttonStyle} onClick={() => void artifactsIndex.reload()} disabled={artifactsIndex.loading}>
                {artifactsIndex.loading ? 'Refreshing...' : 'Refresh'}
              </button>
            }
          >
            <MetaText>
              Total artifacts={artifactsIndex.data?.pagination.total || 0} | validation=
              {artifactsIndex.data?.validation.valid ? 'PASS' : 'FAIL_CLOSED'}
            </MetaText>
            <div style={tableWrapStyle}>
              <table style={tableStyle}>
                <thead>
                  <tr>
                    <th style={thStyle}>File</th>
                    <th style={thStyle}>Component</th>
                    <th style={thStyle}>Decision</th>
                    <th style={thStyle}>Readiness</th>
                  </tr>
                </thead>
                <tbody>
                  {(artifactsIndex.data?.artifacts || []).map((item) => (
                    <tr key={item.metadata.artifact_id}>
                      <td style={tdStyle}>{item.metadata.artifact_file}</td>
                      <td style={tdStyle}>{item.metadata.component}</td>
                      <td style={tdStyle}>{item.metadata.decision_state || '-'}</td>
                      <td style={tdStyle}>{item.metadata.readiness_status || '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </SectionCard>

          <SectionCard
            title="Learning Center Integration"
            action={
              <button style={buttonStyle} onClick={() => void learning.reload()} disabled={learning.loading}>
                {learning.loading ? 'Refreshing...' : 'Refresh'}
              </button>
            }
          >
            <MetaText>Total learning entries={learning.data?.pagination.total || 0}</MetaText>
            <MetaText>Deduplication is source-sha based; release and lineage backlinks preserved.</MetaText>
            <div style={tableWrapStyle}>
              <table style={tableStyle}>
                <thead>
                  <tr>
                    <th style={thStyle}>Type</th>
                    <th style={thStyle}>Title</th>
                    <th style={thStyle}>Class</th>
                  </tr>
                </thead>
                <tbody>
                  {(learning.data?.learning_entries || []).slice(0, 25).map((entry) => (
                    <tr key={entry.entry_id}>
                      <td style={tdStyle}>{entry.entry_type}</td>
                      <td style={tdStyle}>{entry.title}</td>
                      <td style={tdStyle}>{entry.classification || '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <MetaText>
              Pattern classification: {asString(learningPatterns.data?.payload?.classification) || 'UNKNOWN'} |
              readiness examples={asNumber(asRecord(learningPatterns.data?.payload?.readiness_examples).artifact_count)}
            </MetaText>
            {learning.error ? <MetaText>{learning.error}</MetaText> : null}
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
  maxHeight: '270px',
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

const metricListStyle: CSSProperties = {
  display: 'grid',
  gap: '0.3rem',
  marginTop: '0.6rem',
}

const controlRowStyle: CSSProperties = {
  display: 'grid',
  gridTemplateColumns: '1fr 1fr',
  gap: '0.5rem',
  marginBottom: '0.55rem',
}

const inputStyle: CSSProperties = {
  border: '1px solid #cbd5e1',
  borderRadius: '6px',
  padding: '0.38rem 0.45rem',
  fontSize: '0.83rem',
}

const linkButtonStyle: CSSProperties = {
  border: 'none',
  background: 'transparent',
  color: '#0369a1',
  textDecoration: 'underline',
  cursor: 'pointer',
  padding: 0,
  fontSize: '0.78rem',
}
