/** AURA dashboard API/WS contract registry with normalized route building. */

declare global {
  interface Window {
    __AURA_CONFIG__?: {
      API_URL: string
      WS_URL: string
    }
  }
}

type RouteAction = 'approve' | 'reject'
type QueryValue = string | number | boolean | undefined

interface ResolvedApi {
  origin: string
  basePath: string
  apiV1Prefix: string
}

const runtimeConfig = window.__AURA_CONFIG__ || {
  API_URL: 'http://localhost:8000',
  WS_URL: 'ws://localhost:8001/ws',
}

function stripTrailingSlash(value: string): string {
  return value.replace(/\/+$/, '')
}

function normalizePath(value: string): string {
  if (!value) {
    return ''
  }
  const normalized = value.replace(/\/{2,}/g, '/')
  if (normalized === '/') {
    return ''
  }
  return normalized.startsWith('/') ? normalized : `/${normalized}`
}

function resolveApi(rawBase: string): ResolvedApi {
  const resolved = new URL(rawBase || '/', window.location.origin)
  const path = normalizePath(stripTrailingSlash(resolved.pathname))

  // Already pinned to /api/v1.
  if (path.endsWith('/api/v1')) {
    return {
      origin: resolved.origin,
      basePath: path,
      apiV1Prefix: '',
    }
  }

  // When API base is /api (nginx proxy mode), /api/v1 on UI maps to backend /api/v1.
  if (path.endsWith('/api')) {
    return {
      origin: resolved.origin,
      basePath: path,
      apiV1Prefix: '/v1',
    }
  }

  // Direct core mode (localhost:8000): backend already serves /api/v1 directly.
  return {
    origin: resolved.origin,
    basePath: path,
    apiV1Prefix: '/api/v1',
  }
}

function joinUrl(origin: string, basePath: string, path: string): string {
  return `${stripTrailingSlash(origin)}${normalizePath(basePath)}${normalizePath(path)}`
}

function normalizeDuplicateApiPrefix(url: string): string {
  return url.replace(/\/api\/api\/v1(\/|$)/g, '/api/v1$1')
}

function buildWsAbsolute(rawWs: string): string {
  const raw = (rawWs || '').trim()
  if (raw.startsWith('ws://') || raw.startsWith('wss://')) {
    return stripTrailingSlash(raw)
  }
  if (raw.startsWith('http://') || raw.startsWith('https://')) {
    const parsed = new URL(raw)
    const wsProto = parsed.protocol === 'https:' ? 'wss:' : 'ws:'
    return `${wsProto}//${parsed.host}${normalizePath(stripTrailingSlash(parsed.pathname))}`
  }

  const wsProto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${wsProto}//${window.location.host}${normalizePath(raw || '/ws')}`
}

const resolvedApi = resolveApi(runtimeConfig.API_URL)

function buildApi(path: string): string {
  return normalizeDuplicateApiPrefix(joinUrl(resolvedApi.origin, resolvedApi.basePath, path))
}

function buildApiV1(path: string): string {
  return buildApi(resolvedApi.apiV1Prefix ? `${resolvedApi.apiV1Prefix}${normalizePath(path)}` : normalizePath(path))
}

function encodePathSegment(value: string): string {
  return encodeURIComponent(value.trim())
}

function withQuery(url: string, query: Record<string, QueryValue>): string {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined) {
      continue
    }
    params.set(key, String(value))
  }
  const suffix = params.toString()
  if (!suffix) {
    return url
  }
  return `${url}${url.includes('?') ? '&' : '?'}${suffix}`
}

export const API_BASE = buildApi('/')
export const WS_URL = stripTrailingSlash(buildWsAbsolute(runtimeConfig.WS_URL || '/ws')).endsWith('/ws')
  ? stripTrailingSlash(buildWsAbsolute(runtimeConfig.WS_URL || '/ws'))
  : `${stripTrailingSlash(buildWsAbsolute(runtimeConfig.WS_URL || '/ws'))}/ws`

export function wsUrlWithToken(token: string): string {
  if (!token) {
    return WS_URL
  }
  return withQuery(WS_URL, { token })
}

export const API_ROUTES = {
  health: () => buildApi('/health/ready'),
  runtimeOverview: () => buildApi('/health/runtime-overview'),
  metrics: () => buildApi('/metrics'),
  auth: {
    login: () => buildApiV1('/auth/login'),
    me: () => buildApiV1('/auth/me'),
    logout: () => buildApiV1('/auth/logout'),
  },
  agents: {
    root: () => buildApiV1('/agents'),
    running: () => buildApiV1('/agents/running'),
    watchdog: () => buildApiV1('/agents/watchdog'),
    circuitBreakers: () => buildApiV1('/agents/circuit-breakers'),
    spawn: (agentType: string) => buildApiV1(`/agents/${encodePathSegment(agentType)}/spawn`),
    byId: (agentId: string) => buildApiV1(`/agents/${encodePathSegment(agentId)}`),
  },
  tasks: {
    root: () => buildApiV1('/tasks'),
    list: (page = 1, limit = 50) => withQuery(buildApiV1('/tasks'), { page, limit }),
    queueStats: () => buildApiV1('/tasks/queue/stats'),
    replayState: (taskId: string) => buildApiV1(`/tasks/${encodePathSegment(taskId)}/replay/state`),
    replay: (taskId: string) => buildApiV1(`/tasks/${encodePathSegment(taskId)}/replay`),
  },
  patches: {
    root: () => buildApiV1('/patches'),
    list: (limit = 20) => withQuery(buildApiV1('/patches/'), { limit }),
    byId: (patchId: string) => buildApiV1(`/patches/${encodePathSegment(patchId)}`),
    diff: (patchId: string) => buildApiV1(`/patches/${encodePathSegment(patchId)}/diff`),
    evidence: (patchId: string) => buildApiV1(`/patches/${encodePathSegment(patchId)}/evidence`),
    submitApproval: (patchId: string) => buildApiV1(`/patches/${encodePathSegment(patchId)}/submit-approval`),
  },
  knowledge: {
    root: () => buildApiV1('/knowledge'),
    rules: (limit = 60) => withQuery(buildApiV1('/knowledge/rules'), { limit }),
    search: (q: string, limit = 60) => withQuery(buildApiV1('/knowledge/search'), { q, limit }),
    export: () => buildApiV1('/knowledge/export'),
    evidenceReadBase: () => buildApiV1('/knowledge/evidence/read'),
    evidenceIndex: (limit = 500, maxDepth = 4) =>
      withQuery(buildApiV1('/knowledge/evidence/index'), { limit, max_depth: maxDepth }),
    evidenceRead: (section: string, relativePath: string, maxBytes = 120_000) =>
      withQuery(buildApiV1('/knowledge/evidence/read'), {
        section,
        relative_path: relativePath,
        max_bytes: maxBytes,
      }),
  },
  memory: {
    root: () => buildApiV1('/memory'),
    summary: () => buildApiV1('/memory/summary'),
    decisions: (limit = 20) => withQuery(buildApiV1('/memory/decisions'), { limit }),
    failures: (limit = 20) => withQuery(buildApiV1('/memory/failures'), { limit }),
    replayIncidents: (limit = 20) => withQuery(buildApiV1('/memory/replay-incidents'), { limit }),
    risks: (limit = 20) => withQuery(buildApiV1('/memory/risks'), { limit }),
    debt: (limit = 20) => withQuery(buildApiV1('/memory/debt'), { limit }),
    drift: (limit = 20) => withQuery(buildApiV1('/memory/drift'), { limit }),
    opsIncidents: (limit = 30) => withQuery(buildApiV1('/memory/ops-incidents'), { limit }),
    nondeterminismCheck: () => buildApiV1('/memory/validation/nondeterminism-check'),
    learningTimeline: (limit = 200) => withQuery(buildApiV1('/memory/learning/timeline'), { limit }),
    maintainerIntelligence: (limit = 200) =>
      withQuery(buildApiV1('/memory/maintainer/intelligence'), { limit }),
  },
  charter: {
    root: () => buildApiV1('/charter'),
    checkAction: () => buildApiV1('/charter/check-action'),
    enforce: () => buildApiV1('/charter/enforce'),
    highRiskActions: () => buildApiV1('/charter/high-risk-actions'),
    pendingApprovals: () => buildApiV1('/charter/approvals/pending'),
    approvalAction: (requestId: string, action: RouteAction) =>
      buildApiV1(`/charter/approvals/${encodePathSegment(requestId)}/${action}`),
    failsafeReport: () => buildApiV1('/charter/failsafe/report'),
    integrityReport: () => buildApiV1('/charter/integrity/report'),
  },
  governance: {
    approvals: () => buildApiV1('/governance/approvals'),
    approvalsList: (status = 'pending', limit = 50, page = 1) =>
      withQuery(buildApiV1('/governance/approvals'), { status, limit, page }),
    audit: () => buildApiV1('/governance/audit'),
    auditList: (limit = 100, eventType?: string, targetType?: string) =>
      withQuery(buildApiV1('/governance/audit'), { limit, event_type: eventType, target_type: targetType }),
    approvalById: (approvalId: string) => buildApiV1(`/governance/approvals/${encodePathSegment(approvalId)}`),
    evidenceSummary: () => buildApiV1('/governance/summary/evidence'),
  },
  simulation: {
    root: () => buildApiV1('/simulation'),
    scenarios: () => buildApiV1('/simulation/scenarios'),
    byId: (simulationId: string) => buildApiV1(`/simulation/${encodePathSegment(simulationId)}`),
  },
  runtime: {
    artifactsIndex: () => buildApiV1('/runtime/artifacts/index'),
    artifactsIndexQuery: (limit = 50, page = 1) =>
      withQuery(buildApiV1('/runtime/artifacts/index'), { limit, page }),
    artifactsRead: () => buildApiV1('/runtime/artifacts/read'),
    governanceSummary: () => buildApiV1('/runtime/governance/summary'),
    topology: () => buildApiV1('/runtime/topology'),
    topologyQuery: (section: string, limit = 120, page = 1) =>
      withQuery(buildApiV1('/runtime/topology'), { section, limit, page }),
    equivalence: () => buildApiV1('/runtime/equivalence'),
    equivalenceQuery: (criticalOnly = false, limit = 80, page = 1) =>
      withQuery(buildApiV1('/runtime/equivalence'), { critical_only: criticalOnly, limit, page }),
    confidence: () => buildApiV1('/runtime/confidence'),
  },
  trackB: {
    artifactsIndex: () => buildApiV1('/track-b/artifacts/index'),
    artifactsIndexQuery: (
      limit = 50,
      page = 1,
      artifactName = '',
      classification = '',
      stageId = '',
      decisionState = '',
      readinessStatus = '',
      taskId = '',
      component = '',
      includeInvalid = true,
      strictValidation = true,
    ) =>
      withQuery(buildApiV1('/track-b/artifacts/index'), {
        limit,
        page,
        artifact_name: artifactName || undefined,
        classification: classification || undefined,
        stage_id: stageId || undefined,
        decision_state: decisionState || undefined,
        readiness_status: readinessStatus || undefined,
        task_id: taskId || undefined,
        component: component || undefined,
        include_invalid: includeInvalid,
        strict_validation: strictValidation,
      }),
    artifactById: (artifactId: string) => buildApiV1(`/track-b/artifacts/${encodePathSegment(artifactId)}`),
    lineage: () => buildApiV1('/track-b/lineage'),
    lineageQuery: (componentQuery = '', reverseNodeId = '', includeInvalid = true, strictValidation = true) =>
      withQuery(buildApiV1('/track-b/lineage'), {
        component_query: componentQuery || undefined,
        reverse_node_id: reverseNodeId || undefined,
        include_invalid: includeInvalid,
        strict_validation: strictValidation,
      }),
    auditsIndex: () => buildApiV1('/track-b/audits/index'),
    auditsIndexQuery: (limit = 50, page = 1) =>
      withQuery(buildApiV1('/track-b/audits/index'), { limit, page }),
    auditById: (auditId: string) => buildApiV1(`/track-b/audits/${encodePathSegment(auditId)}`),
    releasesIndex: () => buildApiV1('/track-b/releases/index'),
    releasesIndexQuery: (limit = 50, page = 1) =>
      withQuery(buildApiV1('/track-b/releases/index'), { limit, page }),
    releaseByTag: (releaseTag: string) => buildApiV1(`/track-b/releases/${encodePathSegment(releaseTag)}`),
    dashboardReleaseSummary: () => buildApiV1('/track-b/dashboard/release-summary'),
    dashboardReadiness: () => buildApiV1('/track-b/dashboard/readiness'),
    dashboardReadinessHistory: () => buildApiV1('/track-b/dashboard/readiness-history'),
    dashboardDependencyCoverage: () => buildApiV1('/track-b/dashboard/dependency-coverage'),
    dashboardConflicts: () => buildApiV1('/track-b/dashboard/conflicts'),
    dashboardEquivalence: () => buildApiV1('/track-b/dashboard/equivalence'),
    dashboardAuditHistory: (limit = 50) =>
      withQuery(buildApiV1('/track-b/dashboard/audit-history'), { limit }),
    dashboardReleaseHistory: (limit = 50) =>
      withQuery(buildApiV1('/track-b/dashboard/release-history'), { limit }),
    learningIndex: () => buildApiV1('/track-b/learning/index'),
    learningIndexQuery: (limit = 100, page = 1) =>
      withQuery(buildApiV1('/track-b/learning/index'), { limit, page }),
    learningPatterns: () => buildApiV1('/track-b/learning/patterns'),
    search: (q = '', kind = '', limit = 100) =>
      withQuery(buildApiV1('/track-b/search'), {
        q: q || undefined,
        kind: kind || undefined,
        limit,
      }),
  },
  trackBIntel: {
    overview: () => buildApiV1('/track-b-intel/overview'),
    trends: () => buildApiV1('/track-b-intel/trends'),
    patterns: () => buildApiV1('/track-b-intel/patterns'),
    recommendations: () => buildApiV1('/track-b-intel/recommendations'),
    learning: () => buildApiV1('/track-b-intel/learning'),
    executive: () => buildApiV1('/track-b-intel/executive'),
    forecast: () => buildApiV1('/track-b-intel/forecast'),
  },
} as const

// Backward-compatible flat endpoint map for existing pages/components.
export const ENDPOINTS = {
  health: API_ROUTES.health(),
  runtimeOverview: API_ROUTES.runtimeOverview(),
  metrics: API_ROUTES.metrics(),
  login: API_ROUTES.auth.login(),
  me: API_ROUTES.auth.me(),
  logout: API_ROUTES.auth.logout(),
  agents: API_ROUTES.agents.root(),
  tasks: API_ROUTES.tasks.root(),
  patches: API_ROUTES.patches.root(),
  knowledge: API_ROUTES.knowledge.root(),
  memory: API_ROUTES.memory.root(),
  charter: API_ROUTES.charter.root(),
  approvals: API_ROUTES.governance.approvals(),
  audit: API_ROUTES.governance.audit(),
  simulation: API_ROUTES.simulation.root(),
  runtimeArtifactsIndex: API_ROUTES.runtime.artifactsIndex(),
  runtimeArtifactsRead: API_ROUTES.runtime.artifactsRead(),
  runtimeGovernanceSummary: API_ROUTES.runtime.governanceSummary(),
  runtimeTopology: API_ROUTES.runtime.topology(),
  runtimeEquivalence: API_ROUTES.runtime.equivalence(),
  runtimeConfidence: API_ROUTES.runtime.confidence(),
  trackBArtifactsIndex: API_ROUTES.trackB.artifactsIndex(),
  trackBLineage: API_ROUTES.trackB.lineage(),
  trackBReadiness: API_ROUTES.trackB.dashboardReadiness(),
  trackBLearningIndex: API_ROUTES.trackB.learningIndex(),
  trackBIntelOverview: API_ROUTES.trackBIntel.overview(),
  evidenceIndex: API_ROUTES.knowledge.evidenceIndex(),
  evidenceRead: API_ROUTES.knowledge.evidenceReadBase(),
} as const
