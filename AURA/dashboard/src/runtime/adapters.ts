import type {
  ContractIssue,
  RuntimeEquivalenceDimension,
  RuntimeTopologyEvent,
} from './contracts'

export interface RuntimeEdge {
  from: string
  to: string
  timestampMs: number
  evidence: string
}

export function classifyIssues(issues: ContractIssue[]): {
  errors: ContractIssue[]
  warnings: ContractIssue[]
} {
  return {
    errors: issues.filter((issue) => issue.severity === 'error'),
    warnings: issues.filter((issue) => issue.severity === 'warning'),
  }
}

export function governanceTone(classification: string): string {
  if (classification === 'PASS') {
    return '#166534'
  }
  if (classification === 'WARN' || classification === 'BOUNDED') {
    return '#92400e'
  }
  return '#991b1b'
}

export function confidencePercent(value: number): number {
  if (!Number.isFinite(value)) {
    return 0
  }
  return Math.max(0, Math.min(100, Math.round(value * 100)))
}

export function toEquivalenceRiskRows(dimensions: RuntimeEquivalenceDimension[]) {
  return dimensions.map((dimension) => ({
    id: dimension.dimension,
    label: dimension.dimension.split('_').join(' '),
    classification: dimension.classification,
    critical: dimension.critical,
    driftRatio: Number.isFinite(dimension.drift_ratio) ? dimension.drift_ratio : 0,
    delta: dimension.difference_count,
  }))
}

function asString(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function asNumber(value: unknown): number {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value
  }
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : 0
}

export function toRuntimeEdges(events: RuntimeTopologyEvent[]): RuntimeEdge[] {
  return events
    .map((event) => {
      const from = asString(event.from || event.fe_reference || event.source)
      const to = asString(event.to || event.be_reference || event.target)
      return {
        from,
        to,
        timestampMs: asNumber(event.timestamp_ms),
        evidence: asString(event.evidence || event.message),
      }
    })
    .filter((edge) => edge.from && edge.to)
}

export function summarizeRuntimeEdges(edges: RuntimeEdge[]): {
  nodeCount: number
  edgeCount: number
  earliestMs: number
  latestMs: number
} {
  if (!edges.length) {
    return { nodeCount: 0, edgeCount: 0, earliestMs: 0, latestMs: 0 }
  }
  const nodes = new Set<string>()
  let earliest = Number.POSITIVE_INFINITY
  let latest = 0
  for (const edge of edges) {
    nodes.add(edge.from)
    nodes.add(edge.to)
    earliest = Math.min(earliest, edge.timestampMs)
    latest = Math.max(latest, edge.timestampMs)
  }
  return {
    nodeCount: nodes.size,
    edgeCount: edges.length,
    earliestMs: earliest,
    latestMs: latest,
  }
}
