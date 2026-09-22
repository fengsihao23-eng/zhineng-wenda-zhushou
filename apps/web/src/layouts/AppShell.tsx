import React, { useEffect, useRef, useState } from 'react'
import { NavIcon } from '../components/NavIcon'
import { NavLink, useNavigate } from 'react-router-dom'
import { clearAuth, getUserInfo, getToken, UserInfo } from '../utils/auth'
import { logoutApi } from '../services/auth'
import { ErrorDisplay } from '../components/ErrorDisplay'
import { useJsonQuery } from '../hooks/useApi'
import './AppShell.css'

type NavItem = { path: string; label: string; icon: string; group?: string }

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
    { path: '/profile', label: '成绩概览', icon: '📊' },
    { path: '/trends', label: '成绩趋势', icon: '⌁' },
    { path: '/diagnosis', label: '诊断报告', icon: '◎' },
    { path: '/mistakes', label: '错题分析', icon: '◇' },
    { path: '/chat', label: '智能问答', icon: '✦' },
    { path: '/support', label: '家长与支持', icon: '♡' },
  ],
  teacher: [
    { path: '/teacher', label: '教师总览', icon: '◈' },
    { path: '/teacher/analysis', label: '班级学科分析', icon: 'chart', group: '教学分析' },
    { path: '/teacher/students', label: '学生学情', icon: 'users' },
    { path: '/teacher/handoffs', label: '人工转接', icon: '↗' },
    { path: '/teacher/risks', label: '风险事件', icon: '△' },
    { path: '/teacher/feedback', label: '反馈运营', icon: '♡' },
  ],
  school: [
    { path: '/admin', label: '学校总览', icon: '◈' },
    { path: '/admin/school', label: '师生班级与考试', icon: 'users', group: '业务生产' },
    { path: '/admin/imports', label: '成绩导入', icon: 'upload' },
    { path: '/admin/papers', label: '试卷与拆题', icon: 'file' },
    { path: '/admin/questions', label: '题库与知识点', icon: 'tree' },
    { path: '/admin/sources', label: '旧资料与来源', icon: 'file' },
    { path: '/admin/analysis', label: '班级分析', icon: 'chart', group: '教学分析' },
    { path: '/admin/students', label: '学生学情', icon: 'users' },
    { path: '/admin/reports', label: '正式报告原件', icon: 'file' },
    { path: '/admin/knowledge', label: '知识文档治理', icon: 'file', group: '运营治理' },
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

export function AppShell({ children, title, eyebrow, bleed = false }: { children: React.ReactNode; title?: string; eyebrow?: string; bleed?: boolean }) {
  const navigate = useNavigate()
  const user = getUserInfo()
  const role = roleOf(user)
  const navItems = role === 'city' && user?.roles.some(r => r.toUpperCase() === 'SUPER_ADMIN') ? [...navByRole.city, { path: '/admin/school', label: '本校教务工作台', icon: 'users', group: '业务生产' }] : navByRole[role]
  const health = useJsonQuery<{ model?: { real_model_ready?: boolean } }>('/health')
  const serviceState = health.isLoading ? 'loading' : health.error ? 'unavailable' : health.data?.model?.real_model_ready ? 'ready' : 'model_pending'
  const [collapsed, setCollapsed] = useState(() => {
    try { return localStorage.getItem('app_sidebar_collapsed') === '1' } catch { return false }
  })
  const [mobileOpen, setMobileOpen] = useState(false)
  const [narrow, setNarrow] = useState(() => window.matchMedia('(max-width: 850px)').matches)
  const toggleRef = useRef<HTMLButtonElement>(null)
  const sidebarRef = useRef<HTMLElement>(null)
  useEffect(() => {
    const media = window.matchMedia('(max-width: 850px)')
    const change = () => { setNarrow(media.matches); setMobileOpen(false) }
    media.addEventListener('change', change)
    return () => media.removeEventListener('change', change)
  }, [])
  useEffect(() => {
    if (!mobileOpen || !narrow) return
    const first = sidebarRef.current?.querySelector<HTMLElement>('button, a[href]')
    first?.focus()
    const keyboard = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { event.preventDefault(); setMobileOpen(false) }
      if (event.key === 'Tab') {
        const items = [...(sidebarRef.current?.querySelectorAll<HTMLElement>('button:not(:disabled), a[href]') || [])]
        const index = items.indexOf(document.activeElement as HTMLElement)
        if (event.shiftKey && index <= 0) { event.preventDefault(); items[items.length - 1]?.focus() }
        else if (!event.shiftKey && index === items.length - 1) { event.preventDefault(); items[0]?.focus() }
      }
    }
    window.addEventListener('keydown', keyboard)
    return () => { window.removeEventListener('keydown', keyboard); toggleRef.current?.focus() }
  }, [mobileOpen, narrow])
  const [loggingOut, setLoggingOut] = useState(false)
  const [logoutError, setLogoutError] = useState<Error | null>(null)

  const serviceLabel = serviceState === 'ready' ? '服务正常' : serviceState === 'model_pending' ? '模型待配置' : serviceState === 'unavailable' ? '服务连接异常' : '正在连接'

  const logout = async () => {
    if (loggingOut) return
    setLoggingOut(true)
    setLogoutError(null)
    try {
      await logoutApi(getToken())
      clearAuth()
      navigate('/login', { replace: true })
    } catch (error) {
      setLogoutError(error instanceof Error ? error : new Error('退出失败，请重试'))
    } finally { setLoggingOut(false) }
  }

  const toggleSidebar = () => {
    if (window.matchMedia('(max-width: 850px)').matches) { setMobileOpen(value => !value); return }
    setCollapsed(prev => {
      const next = !prev
      try { localStorage.setItem('app_sidebar_collapsed', next ? '1' : '0') } catch { /* ignore storage errors */ }
      return next
    })
  }

  return (
    <div className={`app-shell${collapsed ? ' is-collapsed' : ''}${bleed ? ' is-bleed' : ''}${mobileOpen ? ' is-mobile-open' : ''}`}>
      {mobileOpen && <button className="sidebar-backdrop" aria-label="关闭导航" onClick={() => setMobileOpen(false)} />}
      <aside ref={sidebarRef} className="app-sidebar" role={narrow && mobileOpen ? 'dialog' : undefined} aria-modal={narrow && mobileOpen ? true : undefined} aria-label="主导航">
        {narrow && mobileOpen && <button className="mobile-nav-close" aria-label="收起导航" onClick={() => setMobileOpen(false)}>关闭导航</button>}
        <button className="brand" onClick={() => navigate(navItems[0].path)} aria-label="返回首页">
          <span className="brand-mark">知</span>
          <span><strong>知行</strong><small>学习智能中枢</small></span>
        </button>
        <div className="workspace-label">{roleLabels[role]}</div>
        <nav className="side-nav">
          {navItems.map(item => (
            <React.Fragment key={item.path}>{item.group && <div className="side-nav__group">{item.group}</div>}
            <NavLink onClick={() => setMobileOpen(false)} to={item.path} end={['/', '/teacher', '/admin', '/ops'].includes(item.path)} title={item.label} className={({ isActive }) => `side-nav__item ${isActive ? 'is-active' : ''}`}>
              <span className="side-nav__icon"><NavIcon name={({ '◈':'home', '📊':'chart', '⌁':'chart', '◎':'file', '◇':'file', '✦':'chat', '♡':'chat', '↗':'chat', '△':'alert', '▣':'file' } as Record<string,string>)[item.icon] || item.icon} /></span><span>{item.label}</span>
            </NavLink></React.Fragment>
          ))}
        </nav>
        <div className="sidebar-footnote">
          <span className="status-dot" /> 当前范围内的学习服务
        </div>
      </aside>
      <section className="app-main">
        <header className={bleed ? 'app-topbar app-topbar--floating' : 'app-topbar'}>
          <div className="topbar-left">
            <button
              type="button"
              ref={toggleRef}
              className="sidebar-toggle"
              onClick={toggleSidebar}
              aria-expanded={narrow ? mobileOpen : !collapsed}
              aria-label="切换导航"
              title={collapsed ? '展开侧边栏' : '收起侧边栏'}
            >
              <NavIcon name="menu" />
            </button>
            <div className="breadcrumb"><span>知行</span><i>/</i><b>{eyebrow || roleLabels[role]}</b></div>
          </div>
          <div className="topbar-actions">
            <span className={`system-badge system-badge--${serviceState}`}><span className="status-dot" /> {serviceLabel}</span>
            <button className="user-menu" disabled={loggingOut} onClick={() => { void logout() }} title="退出登录" aria-label="退出登录">
              <span className="user-avatar">{(user?.display_name || '我').slice(0, 1)}</span>
              <span>{user?.display_name || '当前用户'}</span><span>{loggingOut ? '退出中…' : '退出'}</span>
            </button>
          </div>
        </header>
        <main className="workspace-main">
          <ErrorDisplay error={logoutError} title="未能完成安全退出" onRetry={() => { void logout() }} variant="banner" />
          {title && !bleed && <div className="page-heading"><div><div className="page-eyebrow">{eyebrow || roleLabels[role]}</div><h1>{title}</h1></div></div>}
          {children}
        </main>
      </section>
    </div>
  )
}

export function useCurrentRole() { return roleOf(getUserInfo()) }
