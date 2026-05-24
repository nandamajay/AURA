import { useCallback, useEffect, useState } from 'react'
import { apiRequest, toErrorMessage } from '../api/client'

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

  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState<boolean>(enabled)
  const [error, setError] = useState<string>('')
  const [lastUpdated, setLastUpdated] = useState<number>(0)

  const load = useCallback(async () => {
    if (!enabled) {
      return
    }

    const cacheKey = `${key}:${endpoint}:${includeAuth ? 'auth' : 'anon'}`
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
  }, [enabled, endpoint, includeAuth, init, key, ttlMs])

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
