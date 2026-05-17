import { useCallback, useEffect, useState } from 'react'
import { apiRequest, toErrorMessage } from '../api/client'

interface UseApiDataOptions {
  intervalMs?: number
  enabled?: boolean
  init?: RequestInit
  includeAuth?: boolean
}

interface ApiState<T> {
  data: T | null
  loading: boolean
  error: string
  lastUpdated: number
  reload: () => Promise<void>
}

export function useApiData<T = unknown>(
  endpoint: string,
  options: UseApiDataOptions = {},
): ApiState<T> {
  const {
    intervalMs = 0,
    enabled = true,
    init,
    includeAuth = true,
  } = options

  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState<boolean>(enabled)
  const [error, setError] = useState<string>('')
  const [lastUpdated, setLastUpdated] = useState<number>(0)

  const reload = useCallback(async () => {
    if (!enabled) {
      return
    }
    try {
      setLoading(true)
      const result = await apiRequest<T>(endpoint, init, { includeAuth })
      setData(result)
      setError('')
      setLastUpdated(Date.now())
    } catch (err) {
      setError(toErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }, [enabled, endpoint, includeAuth, init])

  useEffect(() => {
    reload()
  }, [reload])

  useEffect(() => {
    if (!enabled || intervalMs <= 0) {
      return
    }
    const timer = setInterval(() => {
      void reload()
    }, intervalMs)
    return () => clearInterval(timer)
  }, [enabled, intervalMs, reload])

  return {
    data,
    loading,
    error,
    lastUpdated,
    reload,
  }
}
