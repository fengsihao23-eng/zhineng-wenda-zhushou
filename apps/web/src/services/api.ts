import { clearAuth, getAuthScope, getAuthSignal, getRefreshToken, getToken, setToken } from '../utils/auth'
import { refreshTokenApi } from './auth'
import { ApiError, safeFetch } from './http'

export { apiError } from './http'
export const API_BASE_URL = import.meta.env.VITE_API_URL || '/api/v1'

let refreshInFlight: { scope: string; promise: Promise<string> } | null = null

async function refreshAccessToken(scope: string, signal: AbortSignal): Promise<string> {
  if (refreshInFlight?.scope === scope) return refreshInFlight.promise
  const refreshToken = getRefreshToken()
  if (!refreshToken) throw new ApiError('登录已过期，请重新登录', 401)

  const promise = refreshTokenApi(refreshToken, signal).then(refreshed => {
    if (signal.aborted || getAuthScope() !== scope) throw new DOMException('请求已取消', 'AbortError')
    setToken(refreshed.access_token, refreshed.refresh_token || refreshToken)
    return refreshed.access_token
  }).finally(() => {
    if (refreshInFlight?.promise === promise) refreshInFlight = null
  })
  refreshInFlight = { scope, promise }
  return promise
}

export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const scope = getAuthScope()
  const sessionSignal = getAuthSignal()
  const signal = init.signal ? AbortSignal.any([sessionSignal, init.signal]) : sessionSignal
  const headers = new Headers(init.headers)
  if (!headers.has('Content-Type') && init.body) headers.set('Content-Type', 'application/json')
  const token = getToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)

  const request = async () => {
    if (signal.aborted || scope !== getAuthScope()) throw new DOMException('请求已取消', 'AbortError')
    const response = await safeFetch(`${API_BASE_URL}${path}`, { ...init, signal, headers, credentials: 'include' })
    if (signal.aborted || scope !== getAuthScope()) throw new DOMException('请求已取消', 'AbortError')
    return response
  }
  let response = await request()
  if (response.status === 401 && !['/auth/login', '/auth/refresh', '/auth/logout'].includes(path)) {
    try {
      const accessToken = await refreshAccessToken(scope, sessionSignal)
      headers.set('Authorization', `Bearer ${accessToken}`)
    } catch (error) {
      if (scope !== getAuthScope() || signal.aborted) throw new DOMException('请求已取消', 'AbortError')
      if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
        clearAuth()
        throw new ApiError('登录已过期，请重新登录', 401)
      }
      throw error
    }
    response = await request()
    if (response.status === 401 && scope === getAuthScope()) clearAuth()
  }
  return response
}
