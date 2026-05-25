import { create } from 'zustand'

interface SessionUser {
  id?: string
  email: string
  role: string
  display_name?: string
}

interface AuthFailureRecord {
  url: string
  status: number
  detail: string
  at: number
}

interface ContractViolationRecord {
  url: string
  reason: string
  normalized_to: string
  at: number
}

interface AuthState {
  token: string
  user: SessionUser | null
  tokenExpiryEpoch: number
  refreshSupported: boolean
  missingTokenRequests: number
  lastAuthFailure: AuthFailureRecord | null
  lastContractViolation: ContractViolationRecord | null
  setSession: (token: string, user: SessionUser | null) => void
  clearSession: () => void
  recordMissingToken: (url: string) => void
  recordAuthFailure: (failure: AuthFailureRecord) => void
  recordContractViolation: (violation: ContractViolationRecord) => void
  clearAuthFailure: () => void
}

const STORAGE_KEY = 'aura.dashboard.session'

function readSession(): { token: string; user: SessionUser | null } {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) {
      return { token: '', user: null }
    }
    const parsed = JSON.parse(raw) as { token?: string; user?: SessionUser | null }
    return {
      token: parsed.token || '',
      user: parsed.user || null,
    }
  } catch {
    return { token: '', user: null }
  }
}

function decodeJwtExpiryEpoch(token: string): number {
  if (!token || token.split('.').length < 2) {
    return 0
  }
  try {
    const payload = token.split('.')[1]
    const normalized = payload.replace(/-/g, '+').replace(/_/g, '/')
    const decoded = atob(normalized)
    const parsed = JSON.parse(decoded) as { exp?: number }
    return typeof parsed.exp === 'number' ? parsed.exp : 0
  } catch {
    return 0
  }
}

function persistSession(token: string, user: SessionUser | null): void {
  if (!token) {
    localStorage.removeItem(STORAGE_KEY)
    return
  }
  localStorage.setItem(STORAGE_KEY, JSON.stringify({ token, user }))
}

const initial = readSession()
const initialExpiry = decodeJwtExpiryEpoch(initial.token)

export const useAuthStore = create<AuthState>((set) => ({
  token: initial.token,
  user: initial.user,
  tokenExpiryEpoch: initialExpiry,
  refreshSupported: false,
  missingTokenRequests: 0,
  lastAuthFailure: null,
  lastContractViolation: null,
  setSession: (token, user) => {
    const tokenExpiryEpoch = decodeJwtExpiryEpoch(token)
    persistSession(token, user)
    set({
      token,
      user,
      tokenExpiryEpoch,
      lastAuthFailure: null,
    })
  },
  clearSession: () => {
    persistSession('', null)
    set({
      token: '',
      user: null,
      tokenExpiryEpoch: 0,
    })
  },
  recordMissingToken: (url) => {
    set((state) => ({
      missingTokenRequests: state.missingTokenRequests + 1,
      lastAuthFailure: {
        url,
        status: 401,
        detail: 'Authentication required: missing bearer token',
        at: Date.now(),
      },
    }))
  },
  recordAuthFailure: (failure) => {
    set(() => ({ lastAuthFailure: failure }))
  },
  recordContractViolation: (violation) => {
    set(() => ({ lastContractViolation: violation }))
  },
  clearAuthFailure: () => {
    set(() => ({ lastAuthFailure: null }))
  },
}))
