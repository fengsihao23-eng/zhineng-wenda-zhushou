import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getCurrentUserApi, loginApi } from '../services/auth'
import { setToken, setUserInfo } from '../utils/auth'
import './Login.css'

export function Login() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)

    try {
      const response = await loginApi({ username, password })

      // 保存token
      setToken(response.access_token, response.refresh_token)

      // 从服务端获取完整的学校、角色和学生绑定信息
      const currentUser = await getCurrentUserApi(response.access_token)
      setUserInfo(currentUser)

      // 跳转到聊天页面
      navigate('/')
    } catch (err) {
      setError(err instanceof Error ? err.message : '登录失败，请重试')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-container">
      <div className="login-box">
        <div className="login-header">
          <h1>智能问答助手</h1>
          <p>学生成绩智能分析系统</p>
        </div>

        <form onSubmit={handleSubmit} className="login-form">
          {error && (
            <div className="error-message">
              {error}
            </div>
          )}

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

          <div className="test-accounts">
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
          </div>
        </form>
      </div>
    </div>
  )
}
