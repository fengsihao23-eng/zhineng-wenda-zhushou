import React, { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getCurrentUserApi, loginApi } from '../services/auth'
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
    mutationFn: async () => {
      const response = await loginApi({ username, password })
      const user = await getCurrentUserApi(response.access_token)
      return { response, user }
    },
    onSuccess: ({ response, user }) => {
      setAuthSession(response.access_token, response.refresh_token, user)
      navigate('/')
    },
    onSettled: () => { submittingRef.current = false },
  })
  const loading = login.isPending
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
          <ErrorDisplay error={login.error} title="登录失败" />

          <div className="form-group">
            <label htmlFor="username">用户名</label>
            <input
              id="username"
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="请输入用户名"
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
              onChange={(e) => setPassword(e.target.value)}
              placeholder="请输入密码"
              disabled={loading}
              required
            />
          </div>

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
