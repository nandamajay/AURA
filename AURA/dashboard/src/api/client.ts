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

function withAuthHeaders(init: RequestInit = {}, includeAuth: boolean): RequestInit {
  const headers = new Headers(init.headers || {})
  const body = init.body

  if (body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  if (includeAuth) {
    const token = useAuthStore.getState().token
    if (token) {
      headers.set('Authorization', `Bearer ${token}`)
    }
  }

  return {
    ...init,
    headers,
  }
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
  const response = await fetch(url, withAuthHeaders(init, includeAuth))
  const payload = await parseResponse(response)

  if (!response.ok) {
    const detail = typeof payload === 'object' && payload !== null && 'detail' in payload
      ? (payload as { detail: unknown }).detail
      : payload
    throw new ApiRequestError(response.status, detail)
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
