import { useCallback, useEffect, useState } from 'react'
import { apiRequest, toErrorMessage } from '../api/client'
import { useAuthStore } from '../store/useAuthStore'

interface RuntimeQueryOptions {
  intervalMs?: number
  enabled?: boolean
  ttlMs?: number
  includeAuth?: boolean
  init?: RequestInit
}

interface CacheEntry {
  expiresAt: number
  value: unknown
}

const runtimeCache = new Map<string, CacheEntry>()

export function clearRuntimeQueryCache(keyPrefix = '') {
  if (!keyPrefix) {
    runtimeCache.clear()
    return
  }
  for (const key of runtimeCache.keys()) {
    if (key.startsWith(keyPrefix)) {
      runtimeCache.delete(key)
    }
  }
}

export function useRuntimeQuery<T = unknown>(
  key: string,
  endpoint: string,
  options: RuntimeQueryOptions = {},
) {
  const {
    intervalMs = 15_000,
    enabled = true,
    ttlMs = 5_000,
    includeAuth = true,
    init,
  } = options
  const token = useAuthStore((state) => state.token)

  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState<boolean>(enabled && (!includeAuth || Boolean(token)))
  const [error, setError] = useState<string>('')
  const [lastUpdated, setLastUpdated] = useState<number>(0)

  const load = useCallback(async () => {
    if (!enabled) {
      return
    }
    if (includeAuth && !token) {
      setLoading(false)
      setError('Authentication required')
      setData(null)
      return
    }

    const authCacheScope = includeAuth ? `auth:${token.slice(-16)}` : 'anon'
    const cacheKey = `${key}:${endpoint}:${authCacheScope}`
    const cached = runtimeCache.get(cacheKey)
    const now = Date.now()
    if (cached && cached.expiresAt > now) {
      setData(cached.value as T)
      setLoading(false)
      setError('')
      setLastUpdated(now)
      return
    }

    try {
      setLoading(true)
      const response = await apiRequest<T>(endpoint, init, { includeAuth })
      runtimeCache.set(cacheKey, {
        value: response,
        expiresAt: now + ttlMs,
      })
      setData(response)
      setError('')
      setLastUpdated(Date.now())
    } catch (err) {
      setError(toErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }, [enabled, endpoint, includeAuth, init, key, token, ttlMs])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    if (!enabled || intervalMs <= 0) {
      return
    }
    const timer = window.setInterval(() => {
      void load()
    }, intervalMs)
    return () => window.clearInterval(timer)
  }, [enabled, intervalMs, load])

  return {
    data,
    loading,
    error,
    lastUpdated,
    reload: load,
  }
}
