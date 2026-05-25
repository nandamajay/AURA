import { useMemo, useState, type CSSProperties } from 'react'
import { API_ROUTES } from '../config'
import { Grid, MetaText, PageContainer, PageHeader, SectionCard } from '../components/PagePrimitives'
import { classifyIssues, confidencePercent, governanceTone, summarizeRuntimeEdges, toEquivalenceRiskRows, toRuntimeEdges } from '../runtime/adapters'
import type {
  RuntimeArtifactsIndexResponse,
  RuntimeConfidenceResponse,
  RuntimeEquivalenceResponse,
  RuntimeGovernanceSummaryResponse,
  RuntimeTopologyResponse,
} from '../runtime/contracts'
import { useRuntimeQuery } from '../runtime/useRuntimeQuery'

const TOPOLOGY_GRAPH_WIDTH = 920
const TOPOLOGY_GRAPH_HEIGHT = 280

export default function RuntimeCognitionCenter() {
  const [topologySection, setTopologySection] = useState('fe_be_links')
  const [criticalOnly, setCriticalOnly] = useState(false)

  const {
    data: governance,
    loading: governanceLoading,
    error: governanceError,
    reload: reloadGovernance,
  } = useRuntimeQuery<RuntimeGovernanceSummaryResponse>(
    'runtime-governance-summary',
    API_ROUTES.runtime.governanceSummary(),
    { intervalMs: 12_000, ttlMs: 4_000 },
  )

  const {
    data: confidence,
    loading: confidenceLoading,
    error: confidenceError,
    reload: reloadConfidence,
  } = useRuntimeQuery<RuntimeConfidenceResponse>(
    'runtime-confidence',
    API_ROUTES.runtime.confidence(),
    { intervalMs: 12_000, ttlMs: 4_000 },
  )

  const {
    data: equivalence,
    loading: equivalenceLoading,
    error: equivalenceError,
    reload: reloadEquivalence,
  } = useRuntimeQuery<RuntimeEquivalenceResponse>(
    'runtime-equivalence',
    API_ROUTES.runtime.equivalenceQuery(criticalOnly, 80),
    { intervalMs: 12_000, ttlMs: 4_000 },
  )

  const {
    data: topology,
    loading: topologyLoading,
    error: topologyError,
    reload: reloadTopology,
  } = useRuntimeQuery<RuntimeTopologyResponse>(
    'runtime-topology',
    API_ROUTES.runtime.topologyQuery(topologySection, 120),
    { intervalMs: 12_000, ttlMs: 4_000 },
  )

  const {
    data: artifacts,
    loading: artifactsLoading,
    error: artifactsError,
    reload: reloadArtifacts,
  } = useRuntimeQuery<RuntimeArtifactsIndexResponse>(
    'runtime-artifacts-index',
    API_ROUTES.runtime.artifactsIndexQuery(50),
    { intervalMs: 20_000, ttlMs: 6_000 },
  )

  const equivalenceRows = useMemo(() => {
    return toEquivalenceRiskRows(equivalence?.dimensions || [])
  }, [equivalence?.dimensions])

  const topologyEdges = useMemo(() => {
    return toRuntimeEdges(topology?.events || [])
  }, [topology?.events])

  const topologySummary = useMemo(() => summarizeRuntimeEdges(topologyEdges), [topologyEdges])

  const topologyLayout = useMemo(() => {
    const nodes = Array.from(new Set(topologyEdges.flatMap((edge) => [edge.from, edge.to])))
    const nodeIndex = new Map(nodes.map((node, index) => [node, index]))
    const nodeSpacing = nodes.length > 1 ? (TOPOLOGY_GRAPH_WIDTH - 90) / (nodes.length - 1) : 0

    return {
      nodes,
      position(node: string) {
        const index = nodeIndex.get(node) || 0
        return {
          x: 45 + index * nodeSpacing,
          y: 140,
        }
      },
    }
  }, [topologyEdges])

  const governanceIssues = classifyIssues(governance?.lineage_consistency?.issues || [])
  const confidenceIssues = classifyIssues(confidence?.validation?.issues || [])
  const topologyIssues = classifyIssues(topology?.integrity?.issues || [])

  return (
    <PageContainer>
      <PageHeader
        title="Runtime Cognition Center"
        subtitle="Contract-first runtime governance, equivalence, topology, confidence, and replay lineage visibility."
      />

      <Grid min={260}>
        <SectionCard
          title="Runtime Governance Decision"
          action={
            <button style={buttonStyle} onClick={() => void reloadGovernance()} disabled={governanceLoading}>
              {governanceLoading ? 'Refreshing...' : 'Refresh'}
            </button>
          }
        >
          {governanceError ? <MetaText>{governanceError}</MetaText> : null}
          <StatusPill
            label={governance?.classification || 'UNKNOWN'}
            tone={governanceTone(governance?.classification || 'UNKNOWN')}
          />
          <MetaText>promotion_eligible={governance?.promotion_eligible ? 'true' : 'false'}</MetaText>
          <MetaText>
            confidence={governance?.confidence_score ?? 0} / threshold={governance?.confidence_threshold ?? 0}
          </MetaText>
          <MetaText>
            critical_divergence_count={governance?.critical_divergence_count ?? 0} | runtime_sensitive_impact_count={governance?.runtime_sensitive_impact_count ?? 0}
          </MetaText>
          <MetaText>deterministic_replay_ready={governance?.deterministic_replay_ready ? 'true' : 'false'}</MetaText>
          {governance?.fail_closed_reasons?.length ? (
            <ul style={listStyle}>
              {governance.fail_closed_reasons.map((reason) => (
                <li key={reason} style={listItemStyle}>
                  {reason}
                </li>
              ))}
            </ul>
          ) : (
            <MetaText>No fail-closed reasons emitted.</MetaText>
          )}
          <MetaText>lineage_validation_errors={governanceIssues.errors.length}</MetaText>
          <MetaText>lineage_validation_warnings={governanceIssues.warnings.length}</MetaText>
        </SectionCard>

        <SectionCard
          title="Runtime Confidence Analysis"
          action={
            <button style={buttonStyle} onClick={() => void reloadConfidence()} disabled={confidenceLoading}>
              {confidenceLoading ? 'Refreshing...' : 'Refresh'}
            </button>
          }
        >
          {confidenceError ? <MetaText>{confidenceError}</MetaText> : null}
          <StatusPill
            label={confidence?.classification || 'UNKNOWN'}
            tone={governanceTone(confidence?.classification || 'UNKNOWN')}
          />
          <ProgressBar value={confidencePercent(confidence?.runtime_confidence || 0)} threshold={confidencePercent(confidence?.confidence_threshold || 0)} />
          <MetaText>runtime_confidence={(confidence?.runtime_confidence ?? 0).toFixed(3)}</MetaText>
          <MetaText>threshold={(confidence?.confidence_threshold ?? 0).toFixed(3)}</MetaText>
          <MetaText>delta={(confidence?.confidence_delta_from_threshold ?? 0).toFixed(3)}</MetaText>
          <MetaText>governance_blocked={confidence?.governance_blocked ? 'true' : 'false'}</MetaText>
          <MetaText>stale_state={confidence?.stale_state ? 'true' : 'false'} {confidence?.stale_reason || ''}</MetaText>
          <MetaText>validation_errors={confidenceIssues.errors.length}</MetaText>
          <MetaText>validation_warnings={confidenceIssues.warnings.length}</MetaText>
        </SectionCard>
      </Grid>

      <div style={{ marginTop: '1rem' }}>
        <Grid>
          <SectionCard
            title="Runtime Equivalence Comparison"
            action={
              <div style={{ display: 'flex', gap: '0.4rem', alignItems: 'center' }}>
                <label style={checkboxStyle}>
                  <input type="checkbox" checked={criticalOnly} onChange={(event) => setCriticalOnly(event.target.checked)} />
                  critical only
                </label>
                <button style={buttonStyle} onClick={() => void reloadEquivalence()} disabled={equivalenceLoading}>
                  {equivalenceLoading ? 'Refreshing...' : 'Refresh'}
                </button>
              </div>
            }
          >
            {equivalenceError ? <MetaText>{equivalenceError}</MetaText> : null}
            <MetaText>
              confidence_score={(equivalence?.summary?.confidence_score ?? 0).toFixed(3)} | critical_divergence_count={equivalence?.summary?.critical_divergence_count ?? 0} | total_differences={equivalence?.summary?.total_differences ?? 0}
            </MetaText>
            <MetaText>unsafe_regions={(equivalence?.unsafe_regions || []).join(', ') || 'none'}</MetaText>
            <div style={{ overflowX: 'auto', marginTop: '0.6rem' }}>
              <table style={tableStyle}>
                <thead>
                  <tr>
                    <th style={thStyle}>dimension</th>
                    <th style={thStyle}>classification</th>
                    <th style={thStyle}>critical</th>
                    <th style={thStyle}>drift_ratio</th>
                    <th style={thStyle}>difference_count</th>
                  </tr>
                </thead>
                <tbody>
                  {equivalenceRows.map((row) => (
                    <tr key={row.id} style={row.critical ? criticalRowStyle : undefined}>
                      <td style={tdStyle}>{row.label}</td>
                      <td style={tdStyle}>{row.classification}</td>
                      <td style={tdStyle}>{row.critical ? 'yes' : 'no'}</td>
                      <td style={tdStyle}>{row.driftRatio.toFixed(3)}</td>
                      <td style={tdStyle}>{row.delta}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </SectionCard>

          <SectionCard
            title="Runtime Topology Graph"
            action={
              <div style={{ display: 'flex', gap: '0.4rem', alignItems: 'center' }}>
                <select value={topologySection} onChange={(event) => setTopologySection(event.target.value)} style={inputStyle}>
                  {(topology?.sections || ['fe_be_links']).map((section) => (
                    <option key={section} value={section}>
                      {section}
                    </option>
                  ))}
                </select>
                <button style={buttonStyle} onClick={() => void reloadTopology()} disabled={topologyLoading}>
                  {topologyLoading ? 'Refreshing...' : 'Refresh'}
                </button>
              </div>
            }
          >
            {topologyError ? <MetaText>{topologyError}</MetaText> : null}
            <MetaText>
              section={topology?.section || topologySection} | events={topology?.pagination?.total || 0} | nodes={topologySummary.nodeCount} | edges={topologySummary.edgeCount}
            </MetaText>
            <MetaText>topology_validation_errors={topologyIssues.errors.length} | topology_validation_warnings={topologyIssues.warnings.length}</MetaText>

            <svg viewBox={`0 0 ${TOPOLOGY_GRAPH_WIDTH} ${TOPOLOGY_GRAPH_HEIGHT}`} width="100%" height="280" style={graphStyle}>
              {topologyEdges.map((edge, index) => {
                const from = topologyLayout.position(edge.from)
                const to = topologyLayout.position(edge.to)
                return (
                  <g key={`${edge.from}-${edge.to}-${index}`}>
                    <line x1={from.x} y1={from.y} x2={to.x} y2={to.y} stroke="#0f766e" strokeWidth={2} />
                    <text x={(from.x + to.x) / 2} y={from.y - 10} textAnchor="middle" fontSize="10" fill="#0f172a">
                      {Math.round(edge.timestampMs)}ms
                    </text>
                  </g>
                )
              })}
              {topologyLayout.nodes.map((node) => {
                const point = topologyLayout.position(node)
                return (
                  <g key={node}>
                    <circle cx={point.x} cy={point.y} r={17} fill="#1e3a8a" stroke="#fff" strokeWidth={2} />
                    <text x={point.x} y={point.y + 34} textAnchor="middle" fontSize="10" fill="#0f172a">
                      {node}
                    </text>
                  </g>
                )
              })}
            </svg>
          </SectionCard>
        </Grid>
      </div>

      <div style={{ marginTop: '1rem' }}>
        <SectionCard
          title="Replay Lineage Exploration"
          action={
            <button style={buttonStyle} onClick={() => void reloadArtifacts()} disabled={artifactsLoading}>
              {artifactsLoading ? 'Refreshing...' : 'Refresh'}
            </button>
          }
        >
          {artifactsError ? <MetaText>{artifactsError}</MetaText> : null}
          <MetaText>Runtime artifact contracts tracked: {artifacts?.pagination.total || 0}</MetaText>
          <div style={{ overflowX: 'auto', marginTop: '0.6rem' }}>
            <table style={tableStyle}>
              <thead>
                <tr>
                  <th style={thStyle}>artifact</th>
                  <th style={thStyle}>classification</th>
                  <th style={thStyle}>lineage_id</th>
                  <th style={thStyle}>session_id</th>
                  <th style={thStyle}>replay_fingerprint</th>
                  <th style={thStyle}>valid</th>
                </tr>
              </thead>
              <tbody>
                {(artifacts?.artifacts || []).map((item) => (
                  <tr key={item.metadata.artifact_type}>
                    <td style={tdStyle}>{item.metadata.artifact_type}</td>
                    <td style={tdStyle}>{item.metadata.classification || 'unknown'}</td>
                    <td style={tdStyle}>{item.metadata.lineage_id || '-'}</td>
                    <td style={tdStyle}>{item.metadata.session_id || '-'}</td>
                    <td style={tdStyle}>{shortHash(item.metadata.replay_fingerprint)}</td>
                    <td style={tdStyle}>{item.validation.valid ? 'yes' : 'no'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </SectionCard>
      </div>
    </PageContainer>
  )
}

function shortHash(value: string): string {
  if (!value) {
    return '-'
  }
  return `${value.slice(0, 12)}...${value.slice(-8)}`
}

function StatusPill({ label, tone }: { label: string; tone: string }) {
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        borderRadius: '999px',
        background: `${tone}22`,
        color: tone,
        border: `1px solid ${tone}55`,
        padding: '0.25rem 0.55rem',
        fontSize: '0.75rem',
        fontWeight: 700,
        marginBottom: '0.4rem',
      }}
    >
      {label}
    </span>
  )
}

function ProgressBar({ value, threshold }: { value: number; threshold: number }) {
  return (
    <div style={{ margin: '0.35rem 0 0.7rem' }}>
      <div style={progressShellStyle}>
        <div style={{ ...progressValueStyle, width: `${value}%` }} />
        <div style={{ ...thresholdMarkerStyle, left: `${threshold}%` }} />
      </div>
      <MetaText>confidence={value}% | threshold={threshold}%</MetaText>
    </div>
  )
}

const inputStyle: CSSProperties = {
  border: '1px solid #cbd5e1',
  borderRadius: '6px',
  padding: '0.35rem 0.5rem',
  fontSize: '0.8rem',
}

const buttonStyle: CSSProperties = {
  border: '1px solid #1e293b',
  borderRadius: '6px',
  background: '#1e293b',
  color: '#fff',
  padding: '0.35rem 0.65rem',
  fontSize: '0.78rem',
  cursor: 'pointer',
}

const checkboxStyle: CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: '0.25rem',
  fontSize: '0.78rem',
  color: '#334155',
}

const graphStyle: CSSProperties = {
  marginTop: '0.6rem',
  background: '#f8fafc',
  border: '1px solid #dbe3ec',
  borderRadius: '8px',
}

const tableStyle: CSSProperties = {
  width: '100%',
  borderCollapse: 'collapse',
  fontSize: '0.8rem',
}

const thStyle: CSSProperties = {
  textAlign: 'left',
  borderBottom: '1px solid #cbd5e1',
  padding: '0.35rem 0.4rem',
  color: '#334155',
}

const tdStyle: CSSProperties = {
  borderBottom: '1px solid #e2e8f0',
  padding: '0.35rem 0.4rem',
  color: '#0f172a',
}

const criticalRowStyle: CSSProperties = {
  background: '#fef2f2',
}

const listStyle: CSSProperties = {
  margin: '0.45rem 0',
  paddingLeft: '1rem',
  color: '#92400e',
}

const listItemStyle: CSSProperties = {
  fontSize: '0.8rem',
  marginBottom: '0.2rem',
}

const progressShellStyle: CSSProperties = {
  position: 'relative',
  height: '8px',
  background: '#e2e8f0',
  borderRadius: '999px',
  overflow: 'hidden',
}

const progressValueStyle: CSSProperties = {
  position: 'absolute',
  left: 0,
  top: 0,
  bottom: 0,
  background: '#0f766e',
}

const thresholdMarkerStyle: CSSProperties = {
  position: 'absolute',
  top: '-2px',
  bottom: '-2px',
  width: '2px',
  background: '#991b1b',
}
