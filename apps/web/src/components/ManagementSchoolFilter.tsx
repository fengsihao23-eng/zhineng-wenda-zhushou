import { useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { getManagementSchool, isSuperAdmin, setManagementSchool, type ManagementSchool } from '../utils/auth'
import { useJsonQuery } from '../hooks/useApi'
import { ErrorDisplay } from './ErrorDisplay'
import './ManagementSchoolFilter.css'

export function ManagementSchoolFilter() {
  const current = getManagementSchool()
  const schools = useJsonQuery<ManagementSchool[]>('/platform/administrators/schools', isSuperAdmin())
  const [name, setName] = useState(''), [code, setCode] = useState('')
  const location = useLocation(), navigate = useNavigate()
  if (!isSuperAdmin()) return null
  const matching = (schools.data || []).filter(s => s.name.toLocaleLowerCase().includes(name.trim().toLocaleLowerCase()) && s.code.toLocaleLowerCase().includes(code.trim().toLocaleLowerCase()))
  const change = (id: string) => {
    const school = schools.data?.find(s => s.id === id) || null
    const params = new URLSearchParams(location.search)
    // Close school-specific tasks when changing the working school.
    const tab = params.get('tab')
    const path = location.pathname.startsWith('/admin/school') ? '/admin/school' : /^\/ops\/schools\//.test(location.pathname) ? '/ops/schools' : /^\/admin\/students\//.test(location.pathname) ? '/admin/students' : location.pathname
    navigate(path + (path === '/admin/school' && tab ? `?tab=${encodeURIComponent(tab)}` : ''), { replace: true })
    setManagementSchool(school)
  }
  return <section className="management-school-filter" aria-label="学校筛选">
    <div className="management-school-filter__fields">
      <label>搜索学校名称<input aria-label="搜索学校名称" value={name} maxLength={200} placeholder="输入学校名称查找" onChange={e => setName(e.target.value)} /></label>
      <label>搜索学校编码<input aria-label="搜索学校编码" value={code} maxLength={50} placeholder="输入学校编码查找" onChange={e => setCode(e.target.value)} /></label>
      <label>学校名称<select aria-label="学校名称" value={current?.id || ''} disabled={schools.isLoading} onChange={e => change(e.target.value)}><option value="">请选择学校</option>{matching.map(s => <option key={s.id} value={s.id}>{s.name}{s.status !== 'active' ? '（已停用）' : ''}</option>)}{current && !matching.some(s => s.id === current.id) && <option value={current.id}>{current.name}（当前学校）</option>}</select></label>
      <label>学校编码<select aria-label="学校编码" value={current?.id || ''} disabled={schools.isLoading} onChange={e => change(e.target.value)}><option value="">请选择学校编码</option>{[...matching].sort((a,b) => a.code.localeCompare(b.code)).map(s => <option key={s.id} value={s.id}>{s.code}</option>)}{current && !matching.some(s => s.id === current.id) && <option value={current.id}>{current.code}（当前学校）</option>}</select></label>
      <button className="secondary-button" type="button" onClick={() => { setName(''); setCode(''); change('') }}>重置学校</button>
    </div>
    <ErrorDisplay error={schools.error} onRetry={() => { void schools.refetch() }} />
    {!schools.isLoading && !schools.error && !matching.length && <p role="status">没有符合名称和编码的学校，请调整搜索。</p>}
    <p className="management-school-filter__context" role="status">{current ? `当前学校：${current.name} · ${current.code}${current.status !== 'active' ? ' · 已停用，仅可查看' : ''}` : '请先选择一所学校，再查看和管理该校数据。'}</p>
  </section>
}

export function SchoolNameHeader() { return isSuperAdmin() && getManagementSchool() ? <th>学校名称</th> : null }
export function SchoolNameCell({ name, code }: { name?: string; code?: string } = {}) {
  const school = getManagementSchool()
  return isSuperAdmin() && school ? <td className="school-name-cell">{name || school.name}<small>{code || school.code}</small></td> : null
}
export function SchoolNameLabel() {
  const school = getManagementSchool()
  return isSuperAdmin() && school ? <p className="subtle">学校名称：{school.name} · 学校编码：{school.code}</p> : null
}
