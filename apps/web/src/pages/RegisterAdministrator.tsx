import { useRef, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { ErrorDisplay } from '../components/ErrorDisplay'
import { apiError, safeFetch } from '../services/http'
import { API_BASE_URL } from '../services/api'
import './Login.css'

export function RegisterAdministrator() {
  const [busy, setBusy] = useState(false)
  const submitting = useRef(false)
  const [error, setError] = useState<Error | null>(null)
  const [result, setResult] = useState<{ username: string } | null>(null)
  const [form, setForm] = useState({ registration_key: '', username: '', display_name: '', phone: '', password: '', confirm: '' })
  const change = (key: keyof typeof form, value: string) => setForm(current => ({ ...current, [key]: value }))

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (submitting.current) return
    setError(null)
    if (form.password !== form.confirm) { setError(new Error('两次输入的密码不一致。')); return }
    submitting.current = true
    setBusy(true)
    try {
      const response = await safeFetch(`${API_BASE_URL}/auth/register-administrator`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ registration_key: form.registration_key.trim(), username: form.username.trim(),
          display_name: form.display_name.trim(), phone: form.phone.trim(), password: form.password }),
      })
      if (!response.ok) throw await apiError(response, '注册失败，请稍后重试')
      setResult(await response.json())
      setForm({ registration_key: '', username: '', display_name: '', phone: '', password: '', confirm: '' })
    } catch (err) {
      setError(err instanceof Error ? err : new Error('注册失败，请稍后重试'))
    } finally { submitting.current = false; setBusy(false) }
  }

  return <div className="login-container"><div className="login-box">
    <div className="login-header"><h1>学校管理员注册</h1><p>使用超级管理员提供的注册密钥创建账号</p></div>
    {result ? <div className="login-form" role="status"><h2>注册成功，等待授权</h2><p>登录账号：<strong>{result.username}</strong></p><p className="login-hint">请保存账号。资料已提交，超级管理员分配学校和权限并启用后，即可登录。</p><Link className="login-button registration-link" to="/login">返回登录</Link></div>
      : <form className="login-form" onSubmit={submit}>
        <ErrorDisplay error={error} title="注册未完成" />
        <div className="form-group"><label htmlFor="registration-key">注册密钥</label><input id="registration-key" type="password" autoComplete="off" required maxLength={200} value={form.registration_key} onChange={e => change('registration_key', e.target.value)} disabled={busy} /><span className="login-hint">每串密钥仅可注册一次，学校和权限由超级管理员分配。</span></div>
        <div className="form-group"><label htmlFor="register-username">8 位数字账号（可选）</label><input id="register-username" autoComplete="username" inputMode="numeric" maxLength={8} pattern="[0-9]{8}" placeholder="自己填写 8 位数字，或留空自动生成" value={form.username} onChange={e => change('username', e.target.value)} disabled={busy} /><span className="login-hint">账号不是手机号，支持以 0 开头。</span></div>
        <div className="form-group"><label htmlFor="register-name">管理员姓名</label><input id="register-name" autoComplete="name" required maxLength={100} value={form.display_name} onChange={e => change('display_name', e.target.value)} disabled={busy} /></div>
        <div className="form-group"><label htmlFor="register-phone">联系电话（可选）</label><input id="register-phone" type="tel" autoComplete="tel" maxLength={30} value={form.phone} onChange={e => change('phone', e.target.value)} disabled={busy} /></div>
        <div className="form-group"><label htmlFor="register-password">登录密码</label><input id="register-password" type="password" autoComplete="new-password" required maxLength={4096} value={form.password} onChange={e => change('password', e.target.value)} disabled={busy} /><span className="login-hint">密码自由设置，忘记密码请联系超级管理员重置。</span></div>
        <div className="form-group"><label htmlFor="register-confirm">确认密码</label><input id="register-confirm" type="password" autoComplete="new-password" required maxLength={4096} value={form.confirm} onChange={e => change('confirm', e.target.value)} disabled={busy} /></div>
        <button className="login-button" disabled={busy}>{busy ? '正在注册…' : '验证密钥并注册'}</button>
        <Link className="registration-link" to="/login">返回登录</Link>
      </form>}
  </div></div>
}
