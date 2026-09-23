import React, { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getCurrentUserApi, loginApi, LoginIdentityRequired } from '../services/auth'
import { setAuthSession } from '../utils/auth'
import { ErrorDisplay } from '../components/ErrorDisplay'
import { useMutation } from '@tanstack/react-query'
import './Login.css'

export function Login() {
  const showTestAccounts = !import.meta.env.PROD
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const submittingRef = useRef(false)
  const navigate = useNavigate()
  const login = useMutation({
    mutationFn: async (identityId?: string) => {
      const response = await loginApi({ username: username.trim(), password, identity_id: identityId })
      const user = await getCurrentUserApi(response.access_token)
      return { response, user }
    },
    onSuccess: ({ response, user }) => {
      setAuthSession(response.access_token, response.refresh_token, user)
      navigate(user.must_change_password ? '/change-password' : '/')
    },
    onSettled: () => { submittingRef.current = false },
  })
  const loading = login.isPending
  const identities = login.error instanceof LoginIdentityRequired ? login.error.identities : []
  const identityNames = { teacher: '教师', student: '学生', parent: '家长', general: '管理账号' }
  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault()
    if (submittingRef.current || loading || !username.trim() || !password) return
    submittingRef.current = true
    login.mutate()
  }

  return (
    <div className="login-container">
      <div className="login-box">
        <div className="login-header">
          <h1>智能问答助手</h1>
          <p>学生成绩智能分析系统</p>
        </div>

        <form onSubmit={handleSubmit} className="login-form">
          <ErrorDisplay error={identities.length ? null : login.error} title="登录失败" />

          <div className="form-group">
            <label htmlFor="username">用户名</label>
            <input
              id="username"
              type="text"
              value={username}
              onChange={(e) => { setUsername(e.target.value); login.reset() }}
              autoComplete="username"
              placeholder="请输入账号"
              disabled={loading}
              required
            />
          </div>

          <div className="form-group">
            <label htmlFor="password">密码</label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => { setPassword(e.target.value); login.reset() }}
              autoComplete="current-password"
              placeholder="请输入密码"
              disabled={loading}
              required
            />
          </div>

          <p className="login-hint">输入账号和密码，系统将自动识别身份并进入对应工作台。</p>
          {identities.length > 0 && <section className="login-identities" aria-label="确认登录身份">
            <p role="status">账号和密码对应以下身份，请确认本次登录身份。</p>
            {identities.map(identity => <button type="button" key={identity.id} disabled={loading} onClick={() => {
              if (submittingRef.current) return
              submittingRef.current = true
              login.mutate(identity.id)
            }}><strong>{identityNames[identity.account_type]} · {identity.display_name}</strong><span>{identity.school_name}</span></button>)}
          </section>}

          <button
            type="submit"
            className="login-button"
            disabled={loading}
          >
            {loading ? '登录中...' : '登录'}
          </button>

          {showTestAccounts && <div className="test-accounts">
            <p className="test-title">测试账号</p>
            <div className="test-account-list">
              <button type="button" className="test-account" onClick={() => { setUsername('student_basic'); setPassword('password123') }}>
                <strong>BASIC学生:</strong>
                <span>student_basic / password123</span>
              </button>
              <button type="button" className="test-account" onClick={() => { setUsername('student_diagnosis'); setPassword('password123') }}>
                <strong>DIAGNOSIS学生:</strong>
                <span>student_diagnosis / password123</span>
              </button>
              <button type="button" className="test-account" onClick={() => { setUsername('teacher_demo'); setPassword('password123') }}>
                <strong>教师工作台:</strong>
                <span>teacher_demo / password123</span>
              </button>
              <button type="button" className="test-account" onClick={() => { setUsername('school_admin_demo'); setPassword('password123') }}>
                <strong>学校管理台:</strong>
                <span>school_admin_demo / password123</span>
              </button>
              <button type="button" className="test-account" onClick={() => { setUsername('city_operator_demo'); setPassword('password123') }}>
                <strong>市级运营中心:</strong>
                <span>city_operator_demo / password123</span>
              </button>
            </div>
          </div>}
        </form>
      </div>
    </div>
  )
}
