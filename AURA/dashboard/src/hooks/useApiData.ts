import { useRuntimeQuery } from '../runtime/useRuntimeQuery'

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
  const key = `${includeAuth ? 'auth' : 'anon'}:${endpoint}`
  const ttlMs = intervalMs > 0 ? Math.min(5_000, intervalMs) : 0
  return useRuntimeQuery<T>(key, endpoint, {
    intervalMs,
    enabled,
    ttlMs,
    includeAuth,
    init,
  })
}
