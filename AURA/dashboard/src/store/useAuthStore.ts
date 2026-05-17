import { create } from 'zustand'

interface SessionUser {
  id?: string
  email: string
  role: string
  display_name?: string
}

interface AuthState {
  token: string
  user: SessionUser | null
  setSession: (token: string, user: SessionUser | null) => void
  clearSession: () => void
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

function persistSession(token: string, user: SessionUser | null): void {
  if (!token) {
    localStorage.removeItem(STORAGE_KEY)
    return
  }
  localStorage.setItem(STORAGE_KEY, JSON.stringify({ token, user }))
}

const initial = readSession()

export const useAuthStore = create<AuthState>((set) => ({
  token: initial.token,
  user: initial.user,
  setSession: (token, user) => {
    persistSession(token, user)
    set({ token, user })
  },
  clearSession: () => {
    persistSession('', null)
    set({ token: '', user: null })
  },
}))
