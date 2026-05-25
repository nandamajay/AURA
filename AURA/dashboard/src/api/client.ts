import { useAuthStore } from '../store/useAuthStore'

export class ApiRequestError extends Error {
  status: number
  detail: unknown

  constructor(status: number, detail: unknown) {
    super(typeof detail === 'string' ? detail : `HTTP ${status}`)
    this.status = status
    this.detail = detail
  }
}

function withAuthHeaders(
  url: string,
  init: RequestInit = {},
  includeAuth: boolean,
  token: string,
): RequestInit {
  const headers = new Headers(init.headers || {})
  const body = init.body

  if (body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  if (includeAuth) {
    if (token) {
      headers.set('Authorization', `Bearer ${token}`)
    } else {
      useAuthStore.getState().recordMissingToken(url)
    }
  }

  return {
    ...init,
    headers,
  }
}

function normalizeRequestUrl(rawUrl: string): string {
  const normalized = rawUrl.replace(/\/api\/api\/v1(\/|$)/g, '/api/v1$1')
  if (normalized !== rawUrl) {
    useAuthStore.getState().recordContractViolation({
      url: rawUrl,
      reason: 'duplicate_api_prefix_normalized',
      normalized_to: normalized,
      at: Date.now(),
    })
    console.warn('[contract] normalized endpoint', { from: rawUrl, to: normalized })
  }
  return normalized
}

async function parseResponse(response: Response): Promise<unknown> {
  const contentType = response.headers.get('content-type') || ''
  if (contentType.includes('application/json')) {
    return response.json()
  }
  return response.text()
}

export async function apiRequest<T = unknown>(
  url: string,
  init: RequestInit = {},
  options: { includeAuth?: boolean } = {},
): Promise<T> {
  const includeAuth = options.includeAuth !== false
  const authState = useAuthStore.getState()
  const token = authState.token
  const tokenExpiryEpoch = authState.tokenExpiryEpoch
  if (includeAuth && token && tokenExpiryEpoch && Math.floor(Date.now() / 1000) >= tokenExpiryEpoch) {
    useAuthStore.getState().clearSession()
    throw new ApiRequestError(401, 'Authentication token expired. Please login again.')
  }
  if (includeAuth && !token) {
    throw new ApiRequestError(401, 'Authentication required: login session missing')
  }

  const normalizedUrl = normalizeRequestUrl(url)
  const response = await fetch(normalizedUrl, withAuthHeaders(normalizedUrl, init, includeAuth, token))
  const payload = await parseResponse(response)

  if (!response.ok) {
    const detail = typeof payload === 'object' && payload !== null && 'detail' in payload
      ? (payload as { detail: unknown }).detail
      : payload
    if (includeAuth && (response.status === 401 || response.status === 403)) {
      let detailString = ''
      if (typeof detail === 'string') {
        detailString = detail
      } else {
        try {
          detailString = JSON.stringify(detail)
        } catch {
          detailString = `HTTP ${response.status}`
        }
      }
      useAuthStore.getState().recordAuthFailure({
        url: normalizedUrl,
        status: response.status,
        detail: detailString,
        at: Date.now(),
      })

      if (response.status === 401 && /token|authentication required|expired/i.test(detailString)) {
        useAuthStore.getState().clearSession()
      }
      console.warn('[auth] request rejected', {
        url: normalizedUrl,
        status: response.status,
        detail: detailString,
      })
    }
    throw new ApiRequestError(response.status, detail)
  }

  if (includeAuth) {
    useAuthStore.getState().clearAuthFailure()
  }

  return payload as T
}

export function toErrorMessage(error: unknown): string {
  if (error instanceof ApiRequestError) {
    if (typeof error.detail === 'string' && error.detail) {
      return error.detail
    }
    if (typeof error.detail === 'object' && error.detail !== null) {
      try {
        return JSON.stringify(error.detail)
      } catch {
        return `Request failed (${error.status})`
      }
    }
    return `Request failed (${error.status})`
  }
  if (error instanceof Error) {
    return error.message
  }
  return 'Unknown error'
}
