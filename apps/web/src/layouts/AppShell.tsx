import React, { useEffect, useState } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { clearAuth, getUserInfo, UserInfo } from '../utils/auth'
import { apiFetch } from '../services/api'
import './AppShell.css'

type NavItem = { path: string; label: string; icon: string }

export function roleOf(user: UserInfo | null): 'student' | 'teacher' | 'school' | 'city' {
  const roles = user?.roles || []
  if (roles.some(role => role.toUpperCase() === 'CITY_OPERATOR' || role.toUpperCase() === 'SUPER_ADMIN')) return 'city'
  if (roles.some(role => role.toUpperCase() === 'SCHOOL_ADMIN' || role.toUpperCase() === 'QA')) return 'school'
  if (roles.some(role => role.toUpperCase() === 'TEACHER')) return 'teacher'
  return 'student'
}

const navByRole: Record<ReturnType<typeof roleOf>, NavItem[]> = {
  student: [
    { path: '/', label: '学习总览', icon: '◈' },
    { path: '/trends', label: '成绩趋势', icon: '⌁' },
    { path: '/diagnosis', label: '诊断报告', icon: '◎' },
    { path: '/mistakes', label: '错题分析', icon: '◇' },
    { path: '/chat', label: '智能问答', icon: '✦' },
    { path: '/support', label: '家长与支持', icon: '♡' },
  ],
  teacher: [
    { path: '/teacher', label: '教师总览', icon: '◈' },
    { path: '/teacher/students', label: '学生学情', icon: '⌁' },
    { path: '/teacher/handoffs', label: '人工转接', icon: '↗' },
    { path: '/teacher/risks', label: '风险事件', icon: '△' },
  ],
  school: [
    { path: '/admin', label: '学校总览', icon: '◈' },
    { path: '/admin/students', label: '学生与班级', icon: '⌁' },
    { path: '/admin/knowledge', label: '知识库治理', icon: '▣' },
    { path: '/admin/feedback', label: '反馈运营', icon: '♡' },
    { path: '/admin/risks', label: '风险看板', icon: '△' },
    { path: '/admin/handoffs', label: '转接队列', icon: '↗' },
  ],
  city: [
    { path: '/ops', label: '市级总览', icon: '◈' },
    { path: '/ops/schools', label: '学校运营', icon: '⌁' },
    { path: '/ops/knowledge', label: '知识库治理', icon: '▣' },
    { path: '/ops/feedback', label: '反馈运营', icon: '♡' },
    { path: '/ops/risks', label: '风险事件', icon: '△' },
    { path: '/ops/handoffs', label: '人工转接', icon: '↗' },
  ],
}

const roleLabels = { student: '学生空间', teacher: '教师工作台', school: '学校管理台', city: '市级运营中心' }

export function AppShell({ children, title, eyebrow }: { children: React.ReactNode; title?: string; eyebrow?: string }) {
  const navigate = useNavigate()
  const user = getUserInfo()
  const role = roleOf(user)
  const navItems = navByRole[role]
  const [serviceState, setServiceState] = useState<'loading' | 'ready' | 'model_pending' | 'unavailable'>('loading')

  useEffect(() => {
    let cancelled = false
    void apiFetch('/health').then(async response => {
      if (!response.ok) throw new Error('health unavailable')
      const health = await response.json() as { model?: { real_model_ready?: boolean; test_model_enabled?: boolean } }
      if (!cancelled) setServiceState(health.model?.real_model_ready ? 'ready' : 'model_pending')
    }).catch(() => { if (!cancelled) setServiceState('unavailable') })
    return () => { cancelled = true }
  }, [])
  const serviceLabel = serviceState === 'ready' ? '服务正常' : serviceState === 'model_pending' ? '模型待配置' : serviceState === 'unavailable' ? '服务连接异常' : '正在连接'

  const logout = () => {
    clearAuth()
    navigate('/login', { replace: true })
  }

  return (
    <div className="app-shell">
      <aside className="app-sidebar">
        <button className="brand" onClick={() => navigate(navItems[0].path)} aria-label="返回首页">
          <span className="brand-mark">知</span>
          <span><strong>知行</strong><small>学习智能中枢</small></span>
        </button>
        <div className="workspace-label">{roleLabels[role]}</div>
        <nav className="side-nav">
          {navItems.map(item => (
            <NavLink key={item.path} to={item.path} end={item.path === '/'} className={({ isActive }) => `side-nav__item ${isActive ? 'is-active' : ''}`}>
              <span className="side-nav__icon">{item.icon}</span><span>{item.label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-footnote">
          <span className="status-dot" /> 数据与回答均可追溯
        </div>
      </aside>
      <section className="app-main">
        <header className="app-topbar">
          <div className="breadcrumb"><span>知行</span><i>/</i><b>{eyebrow || roleLabels[role]}</b></div>
          <div className="topbar-actions">
            <span className={`system-badge system-badge--${serviceState}`}><span className="status-dot" /> {serviceLabel}</span>
            <button className="user-menu" onClick={logout} title="退出登录">
              <span className="user-avatar">{(user?.display_name || '我').slice(0, 1)}</span>
              <span>{user?.display_name || '当前用户'}</span><span className="user-menu__arrow">⌄</span>
            </button>
          </div>
        </header>
        <main className="workspace-main">
          {title && <div className="page-heading"><div><div className="page-eyebrow">{eyebrow || roleLabels[role]}</div><h1>{title}</h1></div></div>}
          {children}
        </main>
      </section>
    </div>
  )
}

export function useCurrentRole() { return roleOf(getUserInfo()) }
