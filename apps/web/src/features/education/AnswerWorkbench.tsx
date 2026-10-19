import { useEffect, useRef } from 'react'
import axios from 'axios'
import api from '../../services/axios'
import { getAuthSignal, getAuthScope, getRefreshToken, getToken, getUserInfo, setAuthSession, clearAuth } from '../../utils/auth'
import { getCurrentUserApi, loginApi, logoutApi } from '../../services/auth'
import { AppShell } from '../../layouts/AppShell'

/** Isolate the supplied prototype's styles while retaining the application's auth lifecycle. */
export function AnswerWorkbenchPage({ mode = 'mini' }: { mode?: 'admin' | 'mini' }) {
  const frame = useRef<HTMLIFrameElement>(null)
  useEffect(() => {
    const receive = async (event: MessageEvent) => {
      if (event.origin !== location.origin || event.source !== frame.current?.contentWindow || event.data?.type !== 'answer-request') return
      const { id, path, body, method, binary, requestKey } = event.data
      if (typeof id !== 'string' || typeof path !== 'string' || !['GET', 'POST'].includes(method)) return
      const target = frame.current?.contentWindow
      const scope = getAuthScope(), signal = getAuthSignal()
      try {
        let value: unknown
        if (path === '@session') {
          value = getRefreshToken() ? { authenticated: true, user: getUserInfo() } : { authenticated: false }
        } else if (path === '@login') {
          const result = await loginApi(body)
          const user = await getCurrentUserApi(result.access_token)
          setAuthSession(result.access_token, result.refresh_token, user)
          value = user
        } else if (path === '@logout') {
          await logoutApi(getToken())
          clearAuth()
          value = { ok: true }
        } else {
          // Only this feature's API is exposed. The child cannot issue arbitrary authenticated requests.
          if (!path.startsWith('/') || path.includes('..') || path.includes('\\') || path.startsWith('//') || !/^\/(admin\/|mini\/|tickets(?:\/|\?|$)|sources\/|reports\/)/.test(path)) throw new Error('不支持的请求')
          const response = await api.request({ url: '/answer-workbench' + path, method, data: body,
            headers: requestKey ? { 'Idempotency-Key': requestKey } : undefined,
            responseType: binary ? 'arraybuffer' : 'json', timeout: 55000, signal })
          if (getAuthScope() !== scope) throw new Error('登录身份已变化，请重新打开页面')
          value = response.data
        }
        target?.postMessage({ type: 'answer-result', id, value }, location.origin)
      } catch (error) {
        let payload = axios.isAxiosError(error) ? error.response?.data : undefined
        if (payload instanceof ArrayBuffer) {
          try { payload = JSON.parse(new TextDecoder().decode(payload)) } catch { payload = undefined }
        }
        const message = payload?.error?.user_message || payload?.error?.message || payload?.detail || (error instanceof Error ? error.message : '请求失败，请重试')
        target?.postMessage({ type: 'answer-result', id, error: { message: typeof message === 'string' ? message : '提交内容不正确，请检查后重试', status: axios.isAxiosError(error) ? error.response?.status : undefined } }, location.origin)
      }
    }
    window.addEventListener('message', receive)
    return () => window.removeEventListener('message', receive)
  }, [])
  const content = <iframe ref={frame} title={mode === 'admin' ? '提示词及人工' : '学科智能问答小程序'} src={`/answer-workbench/${mode}.html?v=r92-20261019`} style={{ width: '100%', height: mode === 'admin' ? '100%' : '100dvh', minHeight: 0, flex: '1 1 0', border: 0, display: 'block' }} />
  return mode === 'admin' ? <AppShell>{content}</AppShell> : content
}
