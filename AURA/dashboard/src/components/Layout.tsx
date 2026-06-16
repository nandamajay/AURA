import { useEffect, useMemo, useState } from 'react'
import { Link, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { apiRequest, toErrorMessage } from '../api/client'
import { API_ROUTES } from '../config'
import { useAuthStore } from '../store/useAuthStore'
import { clearRuntimeQueryCache } from '../runtime/useRuntimeQuery'
import ChatPanel from './ChatPanel'
import TeachingOverlay from './TeachingOverlay'
import { DEFAULT_FLOWS, isFlowCompleted, markFlowCompleted } from '../teaching/TeachingEngine'

const NAV_ITEMS = [
  { path: '/', label: 'Global Command Center', icon: 'GCC' },
  { path: '/migration', label: 'Driver Migration Center', icon: 'DMC' },
  { path: '/knowledge', label: 'Knowledge Graph Center', icon: 'KGC' },
  { path: '/maintainers', label: 'Maintainer Intelligence', icon: 'MIC' },
  { path: '/learning', label: 'Learning Center', icon: 'LRN' },
  { path: '/agents', label: 'Live Agent Observability', icon: 'LAO' },
  { path: '/architecture', label: 'Architecture Lab', icon: 'LAB' },
  { path: '/patches', label: 'Patch Review War Room', icon: 'PRW' },
  { path: '/debug', label: 'Debugging Center', icon: 'DBG' },
  { path: '/simulation', label: 'Simulation Control Center', icon: 'SIM' },
  { path: '/approvals', label: 'Approval Operations', icon: 'APR' },
  { path: '/approval', label: 'Approval Operations', icon: 'APR' },
  { path: '/governance', label: 'Governance Command Center', icon: 'GOV' },
  { path: '/runtime', label: 'Runtime Cognition Center', icon: 'RTC' },
  { path: '/track-b', label: 'Track-B Visibility Center', icon: 'TBV' },
  { path: '/track-b-intel', label: 'Track-B Intelligence Center', icon: 'TBI' },
]

interface MeResponse {
  id: string
  email: string
  role: string
}

function Layout() {
  const location = useLocation()
  const navigate = useNavigate()
  const {
    token,
    user,
    tokenExpiryEpoch,
    refreshSupported,
    missingTokenRequests,
    lastAuthFailure,
    lastContractViolation,
    setSession,
    clearSession,
  } = useAuthStore()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [authError, setAuthError] = useState('')
  const [authBusy, setAuthBusy] = useState(false)
  const [globalSearch, setGlobalSearch] = useState('')
  const [backendConnected, setBackendConnected] = useState(false)
  const [agentCount, setAgentCount] = useState<number | null>(null)
  const [lastRefreshAt, setLastRefreshAt] = useState<number>(Date.now())
  const [teachingFlowId, setTeachingFlowId] = useState<string | null>(null)
  const [nowMs, setNowMs] = useState<number>(Date.now())

  const currentNav = NAV_ITEMS.find((item) => item.path === location.pathname)
  const currentLabel = currentNav?.label || 'Unknown Page'
  const teachingFlow = useMemo(
    () => DEFAULT_FLOWS.find((flow) => flow.id === teachingFlowId) || null,
    [teachingFlowId],
  )

  useEffect(() => {
    clearRuntimeQueryCache()
  }, [token])

  useEffect(() => {
    const timer = window.setInterval(() => setNowMs(Date.now()), 30_000)
    return () => window.clearInterval(timer)
  }, [])

  useEffect(() => {
    if (!token || user) {
      return
    }
    void (async () => {
      try {
        const me = await apiRequest<MeResponse>(API_ROUTES.auth.me())
        setSession(token, { id: me.id, email: me.email, role: me.role })
      } catch {
        clearSession()
      }
    })()
  }, [token, user, setSession, clearSession])

  useEffect(() => {
    const firstVisitFlow = DEFAULT_FLOWS.find((flow) => flow.trigger === 'first_visit' && !isFlowCompleted(flow.id))
    if (firstVisitFlow) {
      setTeachingFlowId(firstVisitFlow.id)
    }
  }, [])

  useEffect(() => {
    let cancelled = false

    async function refreshConnectionAndCounts() {
      try {
        await apiRequest(API_ROUTES.health(), undefined, { includeAuth: false })
        if (!cancelled) {
          setBackendConnected(true)
        }
      } catch {
        if (!cancelled) {
          setBackendConnected(false)
        }
      }

      if (!token) {
        if (!cancelled) {
          setAgentCount(null)
          setLastRefreshAt(Date.now())
        }
        return
      }

      try {
        const running = await apiRequest<{ count: number }>(API_ROUTES.agents.running())
        if (!cancelled) {
          setAgentCount(running.count ?? 0)
        }
      } catch {
        if (!cancelled) {
          setAgentCount(null)
        }
      } finally {
        if (!cancelled) {
          setLastRefreshAt(Date.now())
        }
      }
    }

    void refreshConnectionAndCounts()
    const timer = window.setInterval(() => {
      void refreshConnectionAndCounts()
    }, 15_000)

    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [token])

  async function onLogin(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setAuthBusy(true)
    setAuthError('')
    try {
      const response = await apiRequest<{
        access_token: string
        user: { id: string; email: string; role: string; display_name?: string }
      }>(
        API_ROUTES.auth.login(),
        {
          method: 'POST',
          body: JSON.stringify({ email, password }),
        },
        { includeAuth: false },
      )
      setSession(response.access_token, response.user)
      setPassword('')
    } catch (error) {
      setAuthError(toErrorMessage(error))
    } finally {
      setAuthBusy(false)
    }
  }

  async function onLogout() {
    setAuthBusy(true)
    setAuthError('')
    try {
      await apiRequest(API_ROUTES.auth.logout(), { method: 'POST' })
    } catch {
      // Token may be expired; local cleanup still required.
    } finally {
      clearSession()
      setAuthBusy(false)
    }
  }

  function onGlobalSearchSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const query = globalSearch.trim()
    if (!query) {
      return
    }
    navigate(`/knowledge?q=${encodeURIComponent(query)}`)
  }

  function onOpenGuide() {
    const nextFlow =
      DEFAULT_FLOWS.find((flow) => !isFlowCompleted(flow.id)) ||
      DEFAULT_FLOWS.find((flow) => flow.trigger === 'manual') ||
      DEFAULT_FLOWS[0]
    setTeachingFlowId(nextFlow?.id || null)
  }

  function onCompleteGuide(flowId: string) {
    markFlowCompleted(flowId)
    setTeachingFlowId(null)
  }

  const tokenExpiresAt = tokenExpiryEpoch ? tokenExpiryEpoch * 1000 : 0
  const tokenExpired = tokenExpiresAt ? nowMs >= tokenExpiresAt : false

  return (
    <div style={{ display: 'flex', minHeight: '100vh', background: '#f1f5f9' }}>
      <nav
        data-testid="sidebar"
        style={{
          width: '260px',
          background: '#111827',
          color: '#fff',
          padding: '1rem 0.75rem',
          position: 'fixed',
          height: '100vh',
          overflowY: 'auto',
          borderRight: '1px solid #1f2937',
        }}
      >
        <div style={{ padding: '0 0.75rem 1rem', borderBottom: '1px solid #334155' }}>
          <h1 data-testid="dashboard-title" style={{ fontSize: '1.3rem', margin: 0 }}>
            AURA Dashboard
          </h1>
          <p style={{ fontSize: '0.75rem', color: '#94a3b8', margin: '0.3rem 0 0' }}>
            Audio Upstream Refactor Agent
          </p>
        </div>

        <ul style={{ listStyle: 'none', padding: '0.75rem 0 0', margin: 0 }}>
          {NAV_ITEMS.map((item) => {
            const active = location.pathname === item.path
            return (
              <li key={item.path}>
                <Link
                  to={item.path}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.55rem',
                    padding: '0.58rem 0.72rem',
                    color: active ? '#fff' : '#cbd5e1',
                    background: active ? '#1e293b' : 'transparent',
                    textDecoration: 'none',
                    fontSize: '0.83rem',
                    borderRadius: '6px',
                    border: active ? '1px solid #475569' : '1px solid transparent',
                  }}
                >
                  <span style={iconStyle}>{item.icon}</span>
                  {item.label}
                </Link>
              </li>
            )
          })}
        </ul>

        <div style={{ fontSize: '0.72rem', color: '#64748b', marginTop: '1rem', padding: '0 0.72rem' }}>
          v0.1.0
        </div>
      </nav>

      <main
        style={{
          flex: 1,
          marginLeft: '260px',
          minHeight: '100vh',
          background: '#f1f5f9',
        }}
      >
        <header
          style={{
            position: 'sticky',
            top: 0,
            zIndex: 5,
            borderBottom: '1px solid #cbd5e1',
            background: '#ffffff',
            padding: '0.7rem 1.5rem',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            gap: '1rem',
          }}
        >
          <div style={{ fontSize: '0.86rem', color: '#334155' }}>
            {token ? 'Authenticated session active' : 'Read-only health available; login required for protected APIs'}
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '0.7rem' }}>
            <form onSubmit={onGlobalSearchSubmit} style={{ display: 'flex', gap: '0.4rem', alignItems: 'center' }}>
              <input
                type="search"
                value={globalSearch}
                onChange={(e) => setGlobalSearch(e.target.value)}
                placeholder="Global search"
                style={headerInputStyle}
              />
              <button type="submit" style={smallButtonStyle}>
                Search
              </button>
            </form>
            <button type="button" style={smallButtonStyle} onClick={onOpenGuide}>
              Guide
            </button>
            <span style={notificationPillStyle}>Notifications: 0</span>
            {token ? (
              <div style={{ display: 'flex', gap: '0.6rem', alignItems: 'center' }}>
                <span style={{ fontSize: '0.8rem', color: '#334155' }}>
                  {user?.email || 'unknown'} ({user?.role || 'role?'})
                </span>
                <button style={smallButtonStyle} disabled={authBusy} onClick={() => void onLogout()}>
                  {authBusy ? '...' : 'Logout'}
                </button>
              </div>
            ) : (
              <form onSubmit={onLogin} style={{ display: 'flex', gap: '0.45rem', alignItems: 'center' }}>
                <input
                  type="email"
                  placeholder="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  style={headerInputStyle}
                />
                <input
                  type="password"
                  placeholder="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  style={headerInputStyle}
                />
                <button type="submit" style={smallButtonStyle} disabled={authBusy || !email || !password}>
                  {authBusy ? '...' : 'Login'}
                </button>
              </form>
            )}
          </div>
        </header>

        <div
          style={{
            padding: '0.5rem 1.5rem',
            borderBottom: '1px solid #dbe3ec',
            fontSize: '0.8rem',
            color: '#475569',
            background: '#f8fafc',
          }}
        >
          AURA / {currentLabel}
        </div>

        {authError ? (
          <div style={{ padding: '0.4rem 1.5rem', color: '#b91c1c', fontSize: '0.85rem' }}>{authError}</div>
        ) : null}

        <div
          style={{
            padding: '0.4rem 1.5rem',
            borderBottom: '1px solid #e2e8f0',
            background: '#f8fafc',
            fontSize: '0.78rem',
            color: '#334155',
            display: 'flex',
            gap: '1rem',
            flexWrap: 'wrap',
          }}
        >
          <span>auth_debug.user={user?.email || 'anonymous'}</span>
          <span>auth_debug.role={user?.role || 'none'}</span>
          <span>auth_debug.token_present={token ? 'true' : 'false'}</span>
          <span>auth_debug.token_expired={tokenExpired ? 'true' : 'false'}</span>
          <span>
            auth_debug.token_expires_at=
            {tokenExpiresAt ? new Date(tokenExpiresAt).toLocaleString() : 'unknown'}
          </span>
          <span>auth_debug.refresh_status={refreshSupported ? 'supported' : 'not_configured'}</span>
          <span>auth_debug.missing_token_requests={missingTokenRequests}</span>
          <span>
            auth_debug.last_failed_auth=
            {lastAuthFailure
              ? `${lastAuthFailure.status} ${lastAuthFailure.url} @ ${new Date(lastAuthFailure.at).toLocaleTimeString()}`
              : 'none'}
          </span>
          <span>
            auth_debug.last_contract_violation=
            {lastContractViolation
              ? `${lastContractViolation.reason} ${lastContractViolation.url} -> ${lastContractViolation.normalized_to}`
              : 'none'}
          </span>
        </div>

        <Outlet />

        <footer
          style={{
            marginTop: '1rem',
            borderTop: '1px solid #dbe3ec',
            padding: '0.6rem 1.5rem',
            background: '#ffffff',
            fontSize: '0.8rem',
            color: '#475569',
            display: 'flex',
            justifyContent: 'space-between',
            gap: '1rem',
            flexWrap: 'wrap',
          }}
        >
          <span>Status: {backendConnected ? 'Connected' : 'Disconnected'}</span>
          <span>
            {agentCount === null ? 'Agent count unavailable' : `${agentCount} agents active`}
          </span>
          <span>Last refresh: {new Date(lastRefreshAt).toLocaleTimeString()}</span>
        </footer>
      </main>
      <ChatPanel currentPath={location.pathname} currentPageLabel={currentLabel} />
      <TeachingOverlay
        open={Boolean(teachingFlow)}
        flow={teachingFlow}
        onClose={() => setTeachingFlowId(null)}
        onComplete={onCompleteGuide}
      />
    </div>
  )
}

const iconStyle: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  minWidth: '2.05rem',
  fontSize: '0.66rem',
  fontWeight: 700,
  borderRadius: '4px',
  background: '#334155',
  color: '#e2e8f0',
  padding: '0.18rem 0.3rem',
}

const headerInputStyle: React.CSSProperties = {
  border: '1px solid #cbd5e1',
  borderRadius: '6px',
  padding: '0.35rem 0.5rem',
  fontSize: '0.8rem',
}

const smallButtonStyle: React.CSSProperties = {
  border: '1px solid #0f172a',
  borderRadius: '6px',
  padding: '0.34rem 0.6rem',
  background: '#0f172a',
  color: '#fff',
  fontSize: '0.8rem',
  cursor: 'pointer',
}

const notificationPillStyle: React.CSSProperties = {
  border: '1px solid #cbd5e1',
  borderRadius: '999px',
  padding: '0.28rem 0.55rem',
  background: '#f8fafc',
  color: '#334155',
  fontSize: '0.78rem',
}

export default Layout
