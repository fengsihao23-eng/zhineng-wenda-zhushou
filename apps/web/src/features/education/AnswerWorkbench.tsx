import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useNavigate } from 'react-router-dom'
import axios from 'axios'
import api from '../../services/axios'
import { getAuthSignal, getAuthScope, getRefreshToken, getToken, getUserInfo, setAuthSession, clearAuth } from '../../utils/auth'
import { getCurrentUserApi, loginApi, logoutApi } from '../../services/auth'
import { AppShell } from '../../layouts/AppShell'
import AnswerText from '../../components/AnswerText'
import appTheme from '../../index.css?inline'
import chatTheme from '../../components/ChatContainer.css?inline'
import listTheme from '../../components/MessageList.css?inline'
import bubbleTheme from '../../components/MessageBubble.css?inline'
import inputTheme from '../../components/InputBox.css?inline'
import mathTheme from 'katex/dist/katex.min.css?inline'

const desktopTheme = [appTheme, chatTheme, listTheme, bubbleTheme, inputTheme, mathTheme].join('\n')

/** Isolate the supplied prototype's styles while retaining the application's auth lifecycle. */
export function AnswerWorkbenchPage({ mode = 'web' }: { mode?: 'admin' | 'mini' | 'web' }) {
  const navigate = useNavigate()
  const frame = useRef<HTMLIFrameElement>(null)
  const [answers, setAnswers] = useState<Array<{ node: HTMLElement; text: string; id: string }>>([])
  useEffect(() => {
    const receive = async (event: MessageEvent) => {
      if (event.origin !== location.origin || event.source !== frame.current?.contentWindow) return
      if (mode === 'web' && event.data?.type === 'answer-web-render') {
        const nodes = frame.current?.contentDocument?.querySelectorAll<HTMLElement>('[data-web-message]')
        setAnswers(Array.from(nodes || []).map(node => {
          if (!node.dataset.richRendered) { node.replaceChildren(); node.dataset.richRendered = 'true' }
          return { node, text: node.dataset.webText || '', id: node.dataset.webMessage || '' }
        }))
        return
      }
      if (event.data?.type !== 'answer-request') return
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
        const status = axios.isAxiosError(error) ? error.response?.status : undefined
        const code = payload?.error?.code || payload?.code || (axios.isAxiosError(error) ? error.response?.headers['x-error-code'] : undefined)
        if (status === 403 && code === 'PASSWORD_CHANGE_REQUIRED') {
          navigate('/change-password', { replace: true })
          return
        }
        const message = payload?.error?.user_message || payload?.error?.message || payload?.detail || (error instanceof Error ? error.message : '请求失败，请重试')
        target?.postMessage({ type: 'answer-result', id, error: { message: typeof message === 'string' ? message : '提交内容不正确，请检查后重试', status, code, details: payload?.error?.details } }, location.origin)
      }
    }
    window.addEventListener('message', receive)
    return () => window.removeEventListener('message', receive)
  }, [mode, navigate])
  const onLoad = () => {
    if (mode !== 'web') return
    const document = frame.current?.contentDocument
    if (!document) return
    // The iframe owns its complete theme in both development and production.
    // It must not depend on which style/link tags happen to exist in the host.
    const theme = document.createElement('style')
    theme.id = 'answer-desktop-theme'
    theme.textContent = desktopTheme
    document.getElementById(theme.id)?.remove()
    document.head.insertBefore(theme, document.head.firstChild)
  }
  const content = <><iframe ref={frame} onLoad={onLoad} title={mode === 'admin' ? '提示词及人工' : mode === 'web' ? '智能问答助手' : '学科智能问答小程序'} src={`/answer-workbench/${mode}.html?v=role-access-20261020`} style={{ width: '100%', height: mode === 'mini' ? '100dvh' : '100%', minHeight: 0, flex: '1 1 0', border: 0, display: 'block' }} />{mode === 'web' && answers.map(answer => createPortal(<AnswerText content={answer.text} />, answer.node, answer.id))}</>
  if (mode === 'admin') return <AppShell>{content}</AppShell>
  if (mode === 'web') return <AppShell bleed title="智能问答" eyebrow={`${getUserInfo()?.roles.includes('STUDENT') ? '学生空间' : '教师工作台'} / 智能问答`}><div className="chat-page-frame">{content}</div></AppShell>
  return content
}
