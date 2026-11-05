import React, { useEffect } from 'react'
import { Link, Navigate, useLocation } from 'react-router-dom'
import { AppShell } from '../layouts/AppShell'
import { getManagementSchool, isSuperAdmin, schoolScopedPage } from '../utils/auth'
import { useApiQuery } from '../hooks/useApi'
import { getUserInfo, isAuthenticated, setUserInfo, type UserInfo } from '../utils/auth'
import { ALL_ROLES, hasAnyRole } from '../utils/permissions'
import { ErrorDisplay } from './ErrorDisplay'

export function RoleGate({ allowed = ALL_ROLES, children }: { allowed?: readonly string[]; children: React.ReactNode }) {
  const location = useLocation()
  const authenticated = isAuthenticated()
  // A recent server-verified identity can be reused across routes. Refresh it
  // in the background; API guards remain the final authority for each request.
  const identity = useApiQuery<UserInfo>('/auth/me', ['route-identity'], {
    enabled: authenticated, staleTime: 60_000, gcTime: 30 * 60_000, retry: false, refetchOnMount: true, refetchOnWindowFocus: true,
  })
  useEffect(() => {
    if (identity.data && JSON.stringify(getUserInfo()) !== JSON.stringify(identity.data)) setUserInfo(identity.data)
  }, [identity.data])
  if (!authenticated) return <Navigate to="/login" replace />
  if (identity.isPending) return <div className="loading-screen">正在核验访问权限…</div>
  if (identity.error) return <div className="chat-error-screen"><ErrorDisplay error={identity.error} title="身份核验失败" onRetry={() => { void identity.refetch() }} /><Link to="/login">返回登录</Link></div>
  if (JSON.stringify(getUserInfo()) !== JSON.stringify(identity.data)) return <div className="loading-screen">正在更新角色权限…</div>
  if (identity.data?.must_change_password) return <Navigate to="/change-password" replace />
  if (!hasAnyRole(identity.data || null, allowed)) return <section className="empty-state" role="alert"><h1>无权访问此页面</h1><p>当前账号没有该角色权限，页面数据未加载。</p><Link to="/">返回我的工作台</Link></section>
  if (isSuperAdmin() && schoolScopedPage(location.pathname) && !getManagementSchool()) return <AppShell title="选择管理学校" eyebrow="超级管理员 / 学校范围"><div className="empty-state"><h2>尚未选择学校</h2><p>可按学校名称或编码查找，选择后加载该校的列表和管理功能。</p></div></AppShell>
  return <>{children}</>
}
