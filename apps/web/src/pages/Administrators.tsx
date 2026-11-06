import { useRef, useState, type FormEvent } from 'react'
import { AppShell } from '../layouts/AppShell'
import { useApiMutation, useJsonQuery } from '../hooks/useApi'
import { DetailDialog } from '../components/DetailDialog'
import { ErrorDisplay } from '../components/ErrorDisplay'
import './ManagementPages.css'
import './Administrators.css'

const ROOT = '/platform/administrators'
type School = { id: string; name: string; code: string; status: string }
type Administrator = { id: string; username: string; display_name: string; phone: string | null; school_id: string | null; school_name: string | null; school_code?: string | null; roles: string[]; status: string; is_administrator: boolean; revision: number; account_type: string; platform_id: string | null; must_change_password: boolean; created_at: string; updated_at: string; last_login_at: string | null }
type History = { id: string; action: string; actor_name: string; actor_username: string; school_name: string; allowed: boolean; reason: string | null; details: Record<string, unknown>; created_at: string; resource_type: string; resource_id: string | null; ip_address: string | null; request_id: string | null }
type Page<T> = { total: number; items: T[] }
type Tab = 'accounts' | 'history'
const time = (value: string | null) => value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '—'
const labels: Record<string, string> = { pending: '待授权', active: '正常', disabled: '已禁用', deleted: '已删除', used: '已使用', revoked: '已撤销', expired: '已过期', SUPER_ADMIN: '超级管理员', SCHOOL_ADMIN: '学校管理', CITY_OPERATOR: '市级运营', EXAM_ADMIN: '考务管理', QA: '质量管理', SCHOOL_VIEWER: '全校只读', STUDENT: '学生', TEACHER: '教师', PARENT: '家长' }
const actions: Record<string, string> = { 'administrator.create': '新增学校管理员', 'administrator.register': '历史注册管理员', 'administrator.bootstrap': '升级现有 admin 权限', 'administrator.platform_account.create': '建立独立超管', 'administrator.platform_access.remove': '分离超管权限', 'administrator.school_identity.update': '对齐学校名称及编码', 'administrator.update': '分配权限 / 变更资料', 'administrator.password.reset': '重置密码', 'administrator.login': '登录', 'administrator.logout': '退出登录', 'administrator.request': '访问 / 操作', 'administrator.invitation.create': '创建注册密钥', 'administrator.invitation.revoke': '撤销注册密钥', 'education.account.password_change': '修改密码' }
const fieldLabels: Record<string, string> = { username: '登录账号', display_name: '姓名', phone: '联系电话', status: '状态', school_id: '学校标识', school_name: '学校名称', school_code: '学校编码', roles: '权限方案' }
const permissionHelp: Record<string, string> = { SCHOOL_ADMIN: '管理所选学校的档案、考务、报告及问答配置。', EXAM_ADMIN: '仅管理所选学校的考务、成绩导入和考试查询授权。', SCHOOL_VIEWER: '仅查看所选学校数据，不能修改业务资料。', QA: '在所选学校范围内处理质量检查、反馈与风险事项。' }

function Pager({ page, total, onChange }: { page: number; total: number; onChange: (page: number) => void }) {
  return <div className="admin-pager"><span>共 {total} 条 · 第 {page} / {Math.max(1, Math.ceil(total / 20))} 页</span><button className="secondary-button" disabled={page <= 1} onClick={() => onChange(page - 1)}>上一页</button><button className="secondary-button" disabled={page * 20 >= total} onClick={() => onChange(page + 1)}>下一页</button></div>
}

export function AdministratorsPage() {
  const [tab, setTab] = useState<Tab>('accounts')
  const [school, setSchool] = useState('')
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [query, setQuery] = useState('')
  const [accountStatus, setAccountStatus] = useState('')
  const [administrator, setAdministrator] = useState<{ id: string; name: string } | null>(null)
  const [action, setAction] = useState('')
  const [result, setResult] = useState('')
  const [since, setSince] = useState('')
  const [until, setUntil] = useState('')
  const [edit, setEdit] = useState<Administrator | null>(null)
  const [reset, setReset] = useState<Administrator | null>(null)
  const [accountDetail, setAccountDetail] = useState<Administrator | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [detail, setDetail] = useState<History | null>(null)
  const schools = useJsonQuery<School[]>(`${ROOT}/schools`)
  const params = new URLSearchParams({ page: String(page) })
  if (school) params.set('school_id', school)
  const accountParams = new URLSearchParams(params)
  if (accountStatus) accountParams.set('status', accountStatus)
  if (query) accountParams.set('q', query)
  const historyParams = new URLSearchParams(params)
  if (administrator) historyParams.set('administrator_id', administrator.id)
  if (action) historyParams.set('action', action)
  if (result) historyParams.set('allowed', result)
  if (since) historyParams.set('since', new Date(`${since}T00:00:00`).toISOString())
  if (until) historyParams.set('until', new Date(`${until}T23:59:59.999`).toISOString())
  const accounts = useJsonQuery<Page<Administrator>>(`${ROOT}?${accountParams}`, tab === 'accounts')
  const history = useJsonQuery<Page<History>>(`${ROOT}/history?${historyParams}`, tab === 'history')
  const active = tab === 'accounts' ? accounts : history
  function switchTab(next: Tab) { setTab(next); setPage(1) }
  function viewHistory(item: Administrator) { setAdministrator({ id: item.id, name: item.display_name || item.username }); setAction(''); setResult(''); setSince(''); setUntil(''); setSchool(''); switchTab('history') }

  return <AppShell title="管理员与操作历史" eyebrow="超级管理员 / 账号治理">
    <p className="management-intro">管理学校管理员账号、所属学校和权限，办理密码重置并查看管理员操作历史。</p>
    <div className="admin-tabs" role="tablist" aria-label="管理员管理视图">{([['accounts', '管理员账号'], ['history', '操作历史']] as const).map(([key, label]) => <button key={key} role="tab" aria-selected={tab === key} onClick={() => switchTab(key)}>{label}</button>)}</div>
    <div className="page-toolbar admin-toolbar">
      <label>学校名称<select aria-label="学校名称" className="filter-select" value={school} onChange={e => { setSchool(e.target.value); setPage(1) }}><option value="">全部学校</option>{schools.data?.map(item => <option key={item.id} value={item.id}>{item.name} · {item.code}</option>)}</select></label>
      <label>学校编码<select className="filter-select" aria-label="学校编码" value={school} onChange={e => { setSchool(e.target.value); setPage(1) }}><option value="">全部学校编码</option>{[...(schools.data || [])].sort((a,b) => a.code.localeCompare(b.code)).map(item => <option key={item.id} value={item.id}>{item.code}</option>)}</select></label>
      {tab === 'accounts' && <label>账号状态<select className="filter-select" value={accountStatus} onChange={e => { setAccountStatus(e.target.value); setPage(1); if (e.target.value === 'pending') setSchool('') }}><option value="">全部状态</option><option value="pending">待授权</option><option value="active">正常</option><option value="disabled">已禁用</option></select></label>}
      {tab === 'accounts' && <form className="admin-search" onSubmit={e => { e.preventDefault(); setQuery(search.trim()); setPage(1) }}><input className="filter-input" aria-label="搜索管理员" placeholder="搜索账号或姓名" value={search} onChange={e => setSearch(e.target.value)} /><button className="secondary-button">搜索</button></form>}
      <button className="secondary-button" onClick={() => { void active.refetch() }}>刷新</button>
      {tab === 'accounts' && <button className="primary-button" onClick={() => setShowCreate(true)}>+ 新增学校管理员</button>}
    </div>
    {tab === 'history' && <div className="admin-history-filters">
      {administrator && <span className="admin-scope">{administrator.name} 的操作与账号变更 <button className="action-link" onClick={() => { setAdministrator(null); setPage(1) }}>查看全部管理员</button></span>}
      <label>操作类别<select value={action} onChange={e => { setAction(e.target.value); setPage(1) }}><option value="">全部操作</option>{Object.entries(actions).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
      <label>操作结果<select value={result} onChange={e => { setResult(e.target.value); setPage(1) }}><option value="">全部结果</option><option value="true">成功 / 允许</option><option value="false">失败 / 拒绝</option></select></label>
      <label>开始日期<input type="date" value={since} max={until || undefined} onChange={e => { setSince(e.target.value); setPage(1) }} /></label>
      <label>结束日期<input type="date" value={until} min={since || undefined} onChange={e => { setUntil(e.target.value); setPage(1) }} /></label>
    </div>}
    <ErrorDisplay error={schools.error || active.error} title="加载失败" onRetry={() => { void active.refetch(); void schools.refetch() }} />
    {active.isLoading ? <div className="loading-state">正在加载…</div> : !active.error && <>
      {tab === 'accounts' && <div className="data-table-wrap"><table className="data-table"><thead><tr><th>账号资料</th><th>学校名称 / 权限</th><th>联系电话</th><th>状态</th><th>创建 / 最近登录</th><th>操作</th></tr></thead><tbody>{accounts.data?.items.map(item => <tr key={item.id}><td><strong>{item.display_name || item.username}</strong><div className="subtle">{item.username}</div></td><td>{item.roles.includes('SUPER_ADMIN') ? '平台账号' : item.school_name || '待分配学校'}{item.school_code && <div className="subtle">{item.school_code}</div>}<div className="subtle">{item.roles.map(role => labels[role] || role).join('、') || '未分配权限'}</div></td><td>{item.phone || '未填写'}</td><td><span className={`status-pill status-pill--${item.status === 'active' ? 'green' : item.status === 'pending' ? 'amber' : 'gray'}`}>{labels[item.status] || item.status}</span></td><td>{time(item.created_at)}<div className="subtle">最近登录：{time(item.last_login_at)}</div></td><td><div className="admin-row-actions"><button className="action-link" onClick={() => setAccountDetail(item)}>资料</button>{!item.roles.includes('SUPER_ADMIN') && item.status !== 'deleted' && <>{item.is_administrator && <button className="action-link" onClick={() => setEdit(item)}>{item.status === 'pending' ? '分配学校与权限' : '编辑权限 / 资料'}</button>}<button className="action-link" onClick={() => setReset(item)}>重置密码</button></>}<button className="action-link" onClick={() => viewHistory(item)}>查看历史</button></div></td></tr>)}</tbody></table></div>}
      {tab === 'history' && <><p className="subtle">可查询已有业务审计记录；统一访问记录从此功能上线后开始保存。账号资料变更可查看修改前后内容。</p><div className="data-table-wrap"><table className="data-table"><thead><tr><th>时间</th><th>操作人</th><th>学校名称</th><th>操作</th><th>结果</th><th>详情</th></tr></thead><tbody>{history.data?.items.map(item => <tr key={item.id}><td>{time(item.created_at)}</td><td>{item.actor_name}<div className="subtle">{item.actor_username}</div></td><td>{item.school_name || '—'}</td><td>{actions[item.action] || item.action}{item.details.method != null && <div className="subtle admin-route">{String(item.details.method)} {String(item.details.route)}</div>}</td><td><span className={`status-pill status-pill--${item.allowed ? 'green' : 'red'}`}>{item.allowed ? '成功 / 允许' : '失败 / 拒绝'}</span></td><td><button className="action-link" onClick={() => setDetail(item)}>查看详情</button></td></tr>)}</tbody></table></div></>}
      {!active.data?.items.length && <div className="inline-empty">当前条件下没有记录。</div>}
      <Pager page={page} total={active.data?.total || 0} onChange={setPage} />
    </>}
    {showCreate && <CreateAdministrator schools={schools.data || []} initialSchool={school} onClose={() => setShowCreate(false)} />}
    {edit && <EditAdministrator item={edit} schools={schools.data || []} onClose={() => setEdit(null)} />}
    {reset && <ResetPassword item={reset} onClose={() => setReset(null)} />}
    {accountDetail && <DetailDialog title="账号资料" onClose={() => setAccountDetail(null)}><dl className="admin-detail"><dt>登录账号</dt><dd>{accountDetail.username}</dd><dt>姓名</dt><dd>{accountDetail.display_name || '未填写'}</dd><dt>学校</dt><dd>{accountDetail.roles.includes('SUPER_ADMIN') ? '平台账号' : accountDetail.school_name || '待分配'}</dd><dt>权限</dt><dd>{accountDetail.roles.map(role => labels[role] || role).join('、') || '待分配'}</dd><dt>联系电话</dt><dd>{accountDetail.phone || '未填写'}</dd><dt>账号状态</dt><dd>{labels[accountDetail.status] || accountDetail.status}</dd><dt>平台人员编号</dt><dd>{accountDetail.platform_id || '无'}</dd><dt>下次登录改密</dt><dd>{accountDetail.must_change_password ? '需要' : '不需要'}</dd><dt>创建时间</dt><dd>{time(accountDetail.created_at)}</dd><dt>更新时间</dt><dd>{time(accountDetail.updated_at)}</dd><dt>最近登录</dt><dd>{time(accountDetail.last_login_at)}</dd></dl><p className="subtle">系统不保存可读取的原密码，忘记密码可通过重置处理。</p></DetailDialog>}
    {detail && <HistoryDialog item={detail} onClose={() => setDetail(null)} />}
  </AppShell>
}

function CreateAdministrator({ schools, initialSchool, onClose }: { schools: School[]; initialSchool: string; onClose: () => void }) {
  const [username, setUsername] = useState('')
  const [name, setName] = useState('')
  const [phone, setPhone] = useState('')
  const [school, setSchool] = useState(initialSchool)
  const [role, setRole] = useState('SCHOOL_ADMIN')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [mustChange, setMustChange] = useState(true)
  const [created, setCreated] = useState<Administrator | null>(null)
  const lock = useRef(false)
  const create = useApiMutation<Administrator>(ROOT)
  async function submit(e: FormEvent) {
    e.preventDefault()
    if (lock.current || password !== confirmPassword) return
    lock.current = true
    try {
      const account = await create.mutateAsync({ username: username.trim(), display_name: name.trim(), phone: phone.trim(), school_id: school, roles: [role], password, must_change_password: mustChange })
      setPassword(''); setConfirmPassword(''); setCreated(account)
    } catch { /* Shown by ErrorDisplay. */ } finally { lock.current = false }
  }
  return <DetailDialog title="新增学校管理员" onClose={onClose} busy={create.isPending}>
    {created ? <div className="admin-created" role="status"><h3>学校管理员已创建</h3><label>登录账号<input readOnly value={created.username} onFocus={e => e.target.select()} /></label><dl className="admin-detail"><dt>姓名</dt><dd>{created.display_name}</dd><dt>管理学校</dt><dd>{created.school_name} · {created.school_code}</dd><dt>权限方案</dt><dd>{created.roles.map(value => labels[value] || value).join('、')}</dd></dl><p>请将登录账号和你设置的初始密码交给指定管理员。{created.must_change_password ? '首次登录需修改密码。' : '账号已启用，可直接登录。'}</p><button className="primary-button" onClick={onClose}>完成</button></div>
      : <form className="admin-form" onSubmit={submit}><ErrorDisplay error={create.error} />
        <label>登录账号（可选）<input inputMode="numeric" pattern="[0-9]{8}" maxLength={8} placeholder="八位数字，留空自动生成" autoComplete="off" value={username} onChange={e => setUsername(e.target.value)} disabled={create.isPending} /></label>
        <label>管理员姓名<input required maxLength={100} value={name} onChange={e => setName(e.target.value)} disabled={create.isPending} /></label>
        <label>联系电话（可选）<input type="tel" maxLength={30} value={phone} onChange={e => setPhone(e.target.value)} disabled={create.isPending} /></label>
        <label>管理学校<select required value={school} onChange={e => setSchool(e.target.value)} disabled={create.isPending}><option value="">请选择学校</option>{schools.filter(value => value.status === 'active').map(value => <option key={value.id} value={value.id}>{value.name} · {value.code}</option>)}</select></label>
        <label>权限方案<select required value={role} onChange={e => setRole(e.target.value)} disabled={create.isPending}>{Object.keys(permissionHelp).map(value => <option key={value} value={value}>{labels[value]}</option>)}</select><span className="subtle">{permissionHelp[role]}</span></label>
        <label>初始密码<input type="password" required maxLength={4096} autoComplete="new-password" value={password} onChange={e => setPassword(e.target.value)} disabled={create.isPending} /></label>
        <label>确认初始密码<input type="password" required maxLength={4096} autoComplete="new-password" value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)} disabled={create.isPending} /></label>
        {confirmPassword && password !== confirmPassword && <p className="admin-form-error" role="alert">两次输入的初始密码不一致。</p>}
        <label className="admin-checkbox"><input type="checkbox" checked={mustChange} onChange={e => setMustChange(e.target.checked)} disabled={create.isPending} />首次登录必须修改密码</label>
        <button className="primary-button" disabled={create.isPending || !name.trim() || !school || !password || password !== confirmPassword}>{create.isPending ? '正在创建…' : '创建管理员'}</button>
      </form>}
  </DetailDialog>
}

function EditAdministrator({ item, schools, onClose }: { item: Administrator; schools: School[]; onClose: () => void }) {
  const [name, setName] = useState(item.display_name || '')
  const [phone, setPhone] = useState(item.phone || '')
  const [status, setStatus] = useState(item.status === 'pending' ? 'active' : item.status)
  const [school, setSchool] = useState(item.school_id || '')
  const [role, setRole] = useState(item.roles.find(value => Boolean(permissionHelp[value])) || '')
  const lock = useRef(false)
  const save = useApiMutation(`${ROOT}/${item.id}`, 'PATCH', { onSuccess: onClose })
  async function submit(e: FormEvent) {
    e.preventDefault()
    if (lock.current) return
    lock.current = true
    try { await save.mutateAsync({ display_name: name.trim(), phone: phone.trim(), status, school_id: school, roles: [role], expected_revision: item.revision }) } catch { /* Shown by ErrorDisplay. */ } finally { lock.current = false }
  }
  return <DetailDialog title="分配学校与权限" onClose={onClose} busy={save.isPending}><form className="admin-form" onSubmit={submit}><p>账号：{item.username}</p><ErrorDisplay error={save.error} /><label>管理员姓名<input required maxLength={100} value={name} onChange={e => setName(e.target.value)} disabled={save.isPending} /></label><label>联系电话（可选）<input type="tel" maxLength={30} value={phone} onChange={e => setPhone(e.target.value)} disabled={save.isPending} /></label><label>管理学校<select required value={school} onChange={e => setSchool(e.target.value)} disabled={save.isPending}><option value="">请选择学校</option>{schools.filter(value => value.status === 'active').map(value => <option key={value.id} value={value.id}>{value.name} · {value.code}</option>)}</select></label><label>权限方案<select required value={role} onChange={e => setRole(e.target.value)} disabled={save.isPending}><option value="">请选择权限</option>{Object.keys(permissionHelp).map(value => <option key={value} value={value}>{labels[value]}</option>)}</select></label>{role && <p className="subtle">{permissionHelp[role]}</p>}<label>账号状态<select value={status} onChange={e => setStatus(e.target.value)} disabled={save.isPending}><option value="active">启用</option><option value="disabled">禁用</option></select></label>{status === 'disabled' && <p className="subtle">禁用后该管理员无法继续访问，恢复后需重新登录。历史记录保留。</p>}<button className="primary-button" disabled={save.isPending || !name.trim()}>{save.isPending ? '正在保存…' : '保存授权并记录变更'}</button></form></DetailDialog>
}

function ResetPassword({ item, onClose }: { item: Administrator; onClose: () => void }) {
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [mustChange, setMustChange] = useState(true)
  const [error, setError] = useState<Error | null>(null)
  const lock = useRef(false)
  const reset = useApiMutation(`${ROOT}/${item.id}/reset-password`)
  async function submit(e: FormEvent) {
    e.preventDefault()
    if (lock.current) return
    if (password !== confirm) { setError(new Error('两次输入的密码不一致。')); return }
    setError(null)
    lock.current = true
    try { await reset.mutateAsync({ new_password: password, must_change_password: mustChange, expected_revision: item.revision }); setPassword(''); setConfirm('') } catch { /* Shown below. */ } finally { lock.current = false }
  }
  return <DetailDialog title="重置密码" busy={reset.isPending} onClose={onClose}>{reset.isSuccess ? <p role="status">密码已重置，原登录凭据已失效。请将新密码告知账号使用者。</p> : <form className="admin-form" onSubmit={submit}><p>{item.display_name} · {item.username}</p><p className="subtle">设置新密码后立即生效，操作历史会记录本次重置。</p><ErrorDisplay error={error || reset.error} /><label>新密码<input type="password" autoComplete="new-password" required maxLength={4096} value={password} onChange={e => setPassword(e.target.value)} disabled={reset.isPending} /></label><label>确认新密码<input type="password" autoComplete="new-password" required maxLength={4096} value={confirm} onChange={e => setConfirm(e.target.value)} disabled={reset.isPending} /></label><label><span><input type="checkbox" checked={mustChange} onChange={e => setMustChange(e.target.checked)} disabled={reset.isPending} /> 下次登录要求修改密码</span></label><button className="primary-button" disabled={reset.isPending}>{reset.isPending ? '正在重置…' : '确认重置密码'}</button></form>}</DetailDialog>
}

function HistoryDialog({ item, onClose }: { item: History; onClose: () => void }) {
  const before = item.details.before as Record<string, unknown> | undefined
  const after = item.details.after as Record<string, unknown> | undefined
  const display = (key: string, value: unknown) => Array.isArray(value) ? value.map(role => labels[String(role)] || String(role)).join('、') || '无' : key === 'status' ? labels[String(value)] || String(value ?? '—') : String(value ?? '—')
  return <DetailDialog title={actions[item.action] || item.action} onClose={onClose}>
    <p>{item.actor_name} · {item.school_name || '—'} · {time(item.created_at)}</p>
    {(before || after) && <div className="data-table-wrap"><table className="data-table"><thead><tr><th>字段</th><th>修改前</th><th>修改后</th></tr></thead><tbody>{Object.keys({ ...before, ...after }).map(key => <tr key={key}><td>{fieldLabels[key] || key}</td><td>{display(key, before?.[key])}</td><td>{display(key, after?.[key])}</td></tr>)}</tbody></table></div>}
    <dl className="admin-detail"><dt>操作结果</dt><dd>{item.allowed ? '成功 / 允许' : '失败 / 拒绝'}</dd><dt>资源类型</dt><dd>{item.resource_type || '—'}</dd><dt>资源标识</dt><dd>{item.resource_id || '—'}</dd><dt>连接来源 IP</dt><dd>{item.ip_address || '—'}</dd><dt>请求编号</dt><dd>{item.request_id || '—'}</dd></dl>
    {item.reason && <p>{item.reason}</p>}
    <details><summary>查看完整记录</summary><pre className="admin-json">{JSON.stringify(item.details, null, 2)}</pre></details>
  </DetailDialog>
}
