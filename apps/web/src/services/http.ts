/** 用户可见的 HTTP 错误在登录、普通请求和流式请求间保持一致。 */
export class ApiError extends Error {
  constructor(message: string, public readonly status?: number, public readonly code?: string) {
    super(message)
    this.name = 'ApiError'
  }
}

export function isAbortError(error: unknown): boolean {
  return error instanceof Error && error.name === 'AbortError'
}

export function errorMessage(error: unknown, fallback = '操作失败，请稍后重试'): string {
  const message = error instanceof Error ? error.message : typeof error === 'string' ? error : ''
  if (/failed to fetch|networkerror|network request failed|load failed|fetch failed/i.test(message)) {
    return '网络连接失败，请检查网络后重试'
  }
  return message || fallback
}

export async function safeFetch(input: string, init: RequestInit = {}): Promise<Response> {
  try {
    return await fetch(input, init)
  } catch (error) {
    if (isAbortError(error) || init.signal?.aborted) throw new DOMException('请求已取消', 'AbortError')
    throw new ApiError('网络连接失败，请检查网络后重试', undefined, 'NETWORK_ERROR')
  }
}

export async function apiError(response: Response, fallback: string): Promise<ApiError> {
  const payload = await response.json().catch(() => null)
  const candidates: unknown[] = [payload?.error?.user_message, payload?.error?.message, payload?.user_message, payload?.detail]
  const message = candidates.find(value => typeof value === 'string' && value.trim()) as string | undefined
  const defaults: Record<number, string> = {
    401: '登录已过期，请重新登录',
    403: '你没有权限执行此操作',
    404: '请求的内容不存在',
    405: '不支持此操作',
    422: '提交内容不正确，请检查后重试',
    429: '请求过于频繁，请稍后重试',
  }
  // Framework defaults and structured validation arrays are not useful UI text.
  const readable = message && !['Not Found', 'Method Not Allowed', 'Unauthorized', 'Forbidden', 'Internal Server Error'].includes(message)
    ? message : defaults[response.status] || fallback
  return new ApiError(errorMessage(readable, fallback), response.status, payload?.error?.code)
}
