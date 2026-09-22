import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { bindQueryClientToAuth, createQueryClient } from './queryClient'
import { apiFetch } from './api'
import { safeFetch } from './http'
import { clearAuth, getAuthScope, getAuthSignal, getToken, setAuthSession, setToken, type UserInfo } from '../utils/auth'

function storage() {
  const values = new Map<string, string>()
  return {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => { values.set(key, value) },
    removeItem: (key: string) => { values.delete(key) },
    key: (index: number) => [...values.keys()][index] ?? null,
    get length() { return values.size },
  }
}
const user = (id: string): UserInfo => ({ user_id: id, username: id, display_name: id, roles: ['STUDENT'], school_id: 'school' })
function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(done => { resolve = done })
  return { promise, resolve }
}

beforeEach(() => {
  vi.stubGlobal('window', { sessionStorage: storage(), localStorage: storage(), dispatchEvent: () => true })
  clearAuth()
})
afterEach(() => { clearAuth(); vi.unstubAllGlobals() })

describe('账号切换和请求生命周期', () => {
  it('退出时终止请求并清缓存，迟到响应不能重新填入上一账号数据', async () => {
    const client = createQueryClient()
    const unbind = bindQueryClientToAuth(client)
    setAuthSession('first-access', 'first-refresh', user('first'))
    const firstSignal = getAuthSignal()
    const key = ['dashboard', getAuthScope()]
    const late = deferred<string>()
    const request = client.fetchQuery({ queryKey: key, queryFn: () => late.promise }).catch(error => error)
    clearAuth()
    setAuthSession('second-access', 'second-refresh', user('second'))
    late.resolve('first-student-score')
    await request
    expect(firstSignal.aborted).toBe(true)
    expect(client.getQueryData(key)).toBeUndefined()
    expect(client.getQueryCache().getAll()).toHaveLength(0)
    unbind(); client.clear()
  })

  it('同账号刷新 token 保留缓存，同账号重新登录建立新会话', () => {
    const client = createQueryClient()
    const unbind = bindQueryClientToAuth(client)
    setAuthSession('access', 'refresh', user('first'))
    const scope = getAuthScope()
    const signal = getAuthSignal()
    client.setQueryData(['dashboard', scope], 603)
    setToken('renewed-access', 'renewed-refresh')
    expect(getAuthScope()).toBe(scope)
    expect(signal.aborted).toBe(false)
    expect(client.getQueryData(['dashboard', scope])).toBe(603)
    setAuthSession('new-access', 'new-refresh', user('first'))
    expect(getAuthScope()).not.toBe(scope)
    expect(client.getQueryCache().getAll()).toHaveLength(0)
    unbind(); client.clear()
  })

  it('切换账号后旧刷新响应不能覆盖新账号凭据', async () => {
    setAuthSession('first-access', 'first-refresh', user('first'))
    const refresh = deferred<Response>()
    let started = false
    vi.stubGlobal('fetch', vi.fn((input: string) => {
      if (input.endsWith('/auth/refresh')) { started = true; return refresh.promise }
      return Promise.resolve(new Response('{}', { status: 401 }))
    }))
    const request = apiFetch('/platform/student/dashboard').catch(error => error)
    await vi.waitFor(() => expect(started).toBe(true))
    setAuthSession('second-access', 'second-refresh', user('second'))
    refresh.resolve(new Response(JSON.stringify({ access_token: 'stale-access', refresh_token: 'stale-refresh' })))
    expect((await request).name).toBe('AbortError')
    expect(getToken()).toBe('second-access')
  })

  it('网络错误显示中文，主动取消保留 AbortError', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    await expect(safeFetch('/api/v1/example')).rejects.toThrow('网络连接失败')
    const controller = new AbortController(); controller.abort()
    await expect(safeFetch('/api/v1/example', { signal: controller.signal })).rejects.toMatchObject({ name: 'AbortError' })
  })
})
