import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { apiFetch, apiError } from '../services/api'
import { getCurrentUserApi } from '../services/auth'
import { isAuthenticated, setAuthSession } from '../utils/auth'
import { ErrorDisplay } from '../components/ErrorDisplay'
import './Login.css'

export function ChangePassword() {
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const navigate = useNavigate()
  const action = useMutation({
    mutationFn: async () => {
      if (newPassword !== confirmation) throw new Error('两次输入的新密码不一致。')
      const response = await apiFetch('/auth/change-password', { method: 'POST', body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }) })
      if (!response.ok) throw await apiError(response, '密码修改失败')
      const tokens = await response.json()
      const user = await getCurrentUserApi(tokens.access_token)
      return { tokens, user }
    },
    onSuccess: ({ tokens, user }) => {
      setAuthSession(tokens.access_token, tokens.refresh_token, user)
      navigate('/', { replace: true })
    },
  })
  if (!isAuthenticated()) return <Navigate to="/login" replace />
  return <div className="login-container"><div className="login-box">
    <div className="login-header"><h1>修改初始密码</h1><p>首次登录须修改密码后进入系统。初始密码与导入账号一致。</p></div>
    <form className="login-form" onSubmit={e => { e.preventDefault(); if (!action.isPending) action.mutate() }}>
      <ErrorDisplay error={action.error} />
      <div className="form-group"><label htmlFor="current-password">当前密码</label><input id="current-password" type="password" autoComplete="current-password" required value={currentPassword} onChange={e => setCurrentPassword(e.target.value)} disabled={action.isPending} /></div>
      <div className="form-group"><label htmlFor="new-password">新密码（至少 8 位）</label><input id="new-password" type="password" autoComplete="new-password" minLength={8} maxLength={72} required value={newPassword} onChange={e => setNewPassword(e.target.value)} disabled={action.isPending} /></div>
      <div className="form-group"><label htmlFor="confirm-password">再次输入新密码</label><input id="confirm-password" type="password" autoComplete="new-password" required value={confirmation} onChange={e => setConfirmation(e.target.value)} disabled={action.isPending} /></div>
      <button className="login-button" disabled={action.isPending}>{action.isPending ? '正在修改…' : '修改密码并进入系统'}</button>
      <Link to="/login">返回登录</Link>
    </form>
  </div></div>
}
