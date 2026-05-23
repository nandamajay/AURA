/** AURA Dashboard configuration — injected by nginx or fallback. */

declare global {
  interface Window {
    __AURA_CONFIG__?: {
      API_URL: string
      WS_URL: string
    }
  }
}

const config = window.__AURA_CONFIG__ || {
  API_URL: 'http://localhost:8000',
  WS_URL: 'ws://localhost:8001/ws',
}

export const API_BASE = config.API_URL
export const WS_URL = config.WS_URL.endsWith('/ws') ? config.WS_URL : `${config.WS_URL.replace(/\/$/, '')}/ws`

// API endpoints
export const ENDPOINTS = {
  health: `${API_BASE}/health/ready`,
  runtimeOverview: `${API_BASE}/health/runtime-overview`,
  metrics: `${API_BASE}/metrics`,
  login: `${API_BASE}/api/v1/auth/login`,
  me: `${API_BASE}/api/v1/auth/me`,
  logout: `${API_BASE}/api/v1/auth/logout`,
  agents: `${API_BASE}/api/v1/agents`,
  tasks: `${API_BASE}/api/v1/tasks`,
  patches: `${API_BASE}/api/v1/patches`,
  knowledge: `${API_BASE}/api/v1/knowledge`,
  memory: `${API_BASE}/api/v1/memory`,
  charter: `${API_BASE}/api/v1/charter`,
  approvals: `${API_BASE}/api/v1/governance/approvals`,
  audit: `${API_BASE}/api/v1/governance/audit`,
  simulation: `${API_BASE}/api/v1/simulation`,
  evidenceIndex: `${API_BASE}/api/v1/knowledge/evidence/index`,
  evidenceRead: `${API_BASE}/api/v1/knowledge/evidence/read`,
} as const
