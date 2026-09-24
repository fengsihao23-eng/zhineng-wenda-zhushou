import { useState } from 'react'
import { Link } from 'react-router-dom'
import { KnowledgeForm, KnowledgeActions, type Knowledge } from '../components/KnowledgeEditor'
import { WorkflowControls, type WorkflowRecord } from '../components/WorkflowControls'
import { AppShell, useCurrentRole } from '../layouts/AppShell'
import { ErrorDisplay } from '../components/ErrorDisplay'
import { HumanConversation } from '../features/education/LearningPanels'
import { useJsonQuery } from '../hooks/useApi'
import { HelpTip } from '../components/HelpTip'
import { DetailDialog } from '../components/DetailDialog'
import { Pagination, useClientPagination } from '../components/ListControls'
import './ManagementPages.css'

type Role = 'teacher' | 'school' | 'city'
type Overview = { scope: string; schools: number; students: number; open_risks: number; open_feedback: number; open_handoffs: number }
type StudentRow = { score_scope?: string; subject_scores?: Array<{ subject: string; score: number; exam: string }>; id: string; name: string; student_no: string | null; school: string; school_id: string; latest_score: number | null; latest_exam: string | null; open_risks: number }
type SchoolRow = { id: string; name: string; code: string; status: string; students: number; open_risks: number }
type Feedback = WorkflowRecord & { id: string; rating: string; category: string; note: string | null; status: string; school_id: string; student_id: string | null; created_at: string | null; resolution: string | null }
type Risk = WorkflowRecord & { id: string; student_id: string | null; event_type: string; severity: string; title: string; detail: string; source: string; status: string; created_at: string | null; resolved_at: string | null }
type Handoff = WorkflowRecord & { id: string; student_id: string; reason: string; priority: string; summary: string; status: string; assigned_to: string | null; created_at: string | null; accepted_at: string | null; resolved_at: string | null }

function useData<T>(path: string, enabled = true) {
  // 统一走 TanStack Query（带身份隔离的查询键）。
  const query = useJsonQuery<T>(path, enabled)
  return {
    data: query.data ?? null,
    loading: query.isLoading,
    error: query.error ?? null,
    reload: () => query.refetch(),
  }
}

function ManagementState({ loading, error, empty, onRetry, children }: { loading: boolean; error: Error | null; empty?: boolean; onRetry?: () => void; children: React.ReactNode }) {
  if (loading) return <div className="loading-state">正在同步工作台数据…</div>
  if (error) return <ErrorDisplay error={error} title="数据加载失败" onRetry={onRetry} />
  if (empty) return <div className="empty-state"><div className="empty-state__icon">⌁</div><strong>当前没有记录</strong><p>新的系统事件会在产生后显示在这里。</p></div>
  return <>{children}</>
}

const roleCopy: Record<Role, { title: string; eyebrow: string; intro: string }> = {
  teacher: { title: '教师总览', eyebrow: '教师工作台 / 学情运营', intro: '聚焦需要教学跟进的学生与事件。' },
  school: { title: '学校总览', eyebrow: '学校管理台 / 运营总览', intro: '查看学校范围内的数据质量、反馈和风险处理进度。' },
  city: { title: '市级总览', eyebrow: '市级运营中心 / 跨校运营', intro: '从全市视角监控学校接入、服务质量与风险闭环。' },
}

export function ManagementOverviewPage() {
  const role = useCurrentRole() as Role
  const copy = roleCopy[role] || roleCopy.teacher
  const overview = useData<Overview>('/platform/management/overview')
  const students = useData<StudentRow[]>('/platform/management/students', role !== 'city')
  const schools = useData<SchoolRow[]>('/platform/management/schools', role === 'city')
  const roster = role === 'city' ? schools : students
  return <AppShell title={copy.title} eyebrow={copy.eyebrow}><ManagementState loading={overview.loading} error={overview.error} onRetry={overview.reload}><p className="management-intro">{copy.intro}</p><div className="stats-grid stats-grid--management"><ManagementStat label={role === 'city' ? '接入学校' : '学生总数'} value={role === 'city' ? overview.data?.schools : overview.data?.students} hint={role === 'city' ? '纳入运营范围' : '当前数据范围'} tone="mint" /><ManagementStat label="待处理风险" value={overview.data?.open_risks} hint="需要确认或跟进" tone="orange" /><ManagementStat label="待处理反馈" value={overview.data?.open_feedback} hint="运营队列" tone="purple" /><ManagementStat label="人工转接" value={overview.data?.open_handoffs} hint="待接单或处理中" tone="blue" /></div><div className="content-grid content-grid--management"><section className="panel"><div className="panel-heading"><div><h2>{role === 'city' ? '学校运行概览' : '学生学情队列'}</h2><p>{role === 'city' ? '按学校查看开放事件' : '优先关注有风险标记的学生'}</p></div><a className="text-link" href={role === 'city' ? '/ops/schools' : role === 'school' ? '/admin/students' : '/teacher/students'}>查看全部 ↗</a></div><ManagementState loading={roster.loading} error={roster.error} onRetry={() => { void roster.reload() }}>{role === 'city' ? <SchoolMiniTable rows={schools.data || []} /> : <StudentMiniTable rows={students.data || []} />}</ManagementState></section><section className="panel"><div className="panel-heading"><div><h2>待办队列</h2><p>按优先级进入处理页面</p></div></div><div className="queue-list"><QueueItem label="风险事件" count={overview.data?.open_risks || 0} tone="red" href={role === 'city' ? '/ops/risks' : role === 'school' ? '/admin/risks' : '/teacher/risks'} /><QueueItem label="人工转接" count={overview.data?.open_handoffs || 0} tone="amber" href={role === 'city' ? '/ops/handoffs' : role === 'school' ? '/admin/handoffs' : '/teacher/handoffs'} /><QueueItem label="运营反馈" count={overview.data?.open_feedback || 0} tone="purple" href={role === 'city' ? '/ops/feedback' : role === 'teacher' ? '/teacher/feedback' : '/admin/feedback'} /></div><div className="queue-note">{(overview.data?.open_risks || 0) + (overview.data?.open_handoffs || 0) ? '有新的待处理事项，请在承诺时限内完成闭环。' : '目前没有超时待办。'}</div></section></div></ManagementState></AppShell>
}

function ManagementStat({ label, value, hint, tone }: { label: string; value?: number; hint: string; tone: string }) { return <div className={`stat-card stat-card--${tone}`}><div className="stat-card__label">{label}</div><div className="stat-card__value">{value ?? '—'}</div><div className="stat-card__hint">{hint}</div></div> }
function QueueItem({ label, count, tone, href }: { label: string; count: number; tone: string; href: string }) { return <a className="queue-item" href={href}><span className={`queue-icon queue-icon--${tone}`}>{tone === 'red' ? '△' : tone === 'amber' ? '↗' : '♡'}</span><span><strong>{label}</strong><small>进入处理队列</small></span><b>{count}</b><span className="queue-arrow">›</span></a> }
function StudentMiniTable({ rows }: { rows: StudentRow[] }) { const display = rows.slice(0, 6); return display.length ? <div className="mini-table">{display.map(row => <div className="mini-table__row" key={row.id}><span className="mini-avatar">{row.name.slice(0, 1)}</span><span className="mini-main"><strong>{row.name}</strong><small>{row.student_no || '未填写学号'}</small></span><span>{row.score_scope === 'teaching_subjects' ? '任教学科详情' : row.latest_score != null ? `${row.latest_score} 分` : '暂无成绩'}</span><span className={`status-pill status-pill--${row.open_risks ? 'amber' : 'green'}`}>{row.open_risks ? `${row.open_risks} 个风险` : '正常'}</span></div>)}</div> : <div className="inline-empty">暂无学生数据。</div> }
function SchoolMiniTable({ rows }: { rows: SchoolRow[] }) { const display = rows.slice(0, 6); return display.length ? <div className="mini-table">{display.map(row => <div className="mini-table__row" key={row.id}><span className="mini-avatar mini-avatar--school">校</span><span className="mini-main"><strong>{row.name}</strong><small>{row.code}</small></span><span>{row.students} 名学生</span><span className={`status-pill status-pill--${row.open_risks ? 'amber' : 'green'}`}>{row.open_risks ? `${row.open_risks} 个风险` : '运行正常'}</span></div>)}</div> : <div className="inline-empty">暂无学校数据。</div> }


export function StudentRosterPage() {
  const role = useCurrentRole() as Role
  const { data, loading, error, reload } = useData<StudentRow[]>('/platform/management/students')
  const [query, setQuery] = useState('')
  const [onlyRisk, setOnlyRisk] = useState(false)
  const rows = (data || []).filter(row => (row.name + (row.student_no || '') + row.school).includes(query)).filter(row => !onlyRisk || row.open_risks > 0)
  const pagination = useClientPagination(rows, JSON.stringify([query, onlyRisk]))
  const base = role === 'teacher' ? '/teacher' : '/admin'
  return <AppShell title="学生与班级"><ManagementState loading={loading} error={error} onRetry={reload} empty={!data?.length}>
    <HelpTip label="数据范围">{role === 'teacher' ? '仅显示当前有效任教班级及学科。没有配置任教关系时不会展示全校数据。' : '当前授权范围内的学生数据。'}</HelpTip>
    <div className="filter-row"><input className="filter-input" placeholder="搜索姓名、学号或学校" value={query} onChange={event => setQuery(event.target.value)} /><label className="check-filter"><input type="checkbox" checked={onlyRisk} onChange={event => setOnlyRisk(event.target.checked)} /> 只看待跟进</label></div>
    <Pagination {...pagination} />
    {!rows.length ? <div className="inline-empty">没有符合筛选条件的学生。</div> : <div className="data-table-wrap"><table className="data-table"><thead><tr><th>学生</th><th>学校</th><th>{role === 'teacher' ? '任教学科成绩' : '最近考试 / 总分'}</th><th>风险</th><th>操作</th></tr></thead><tbody>{pagination.items.map(row => <tr key={row.id}><td><strong>{row.name}</strong><div className="subtle">{row.student_no || '未填写学号'}</div></td><td>{row.school}</td><td>{row.score_scope === 'teaching_subjects' ? row.subject_scores?.length ? row.subject_scores.map(score => <div key={score.subject}>{score.subject}：{score.score} 分 · {score.exam}</div>) : '任教学科暂无成绩' : <>{row.latest_exam || '暂无考试'} · {row.latest_score ?? '—'}</>}</td><td>{row.open_risks} 个待跟进</td><td><Link className="action-link" to={base + '/students/' + row.id}>查看学情</Link></td></tr>)}</tbody></table></div>}
  </ManagementState></AppShell>
}

function workflowTone(status: string) { if (['published', 'resolved', 'closed', 'active', 'accepted'].includes(status)) return 'green'; if (['rejected', 'offline', 'critical'].includes(status)) return 'red'; if (['pending_review', 'open', 'acknowledged', 'pending'].includes(status)) return 'amber'; return 'gray' }
function workflowLabel(status: string) { const labels: Record<string, string> = { draft: '草稿', pending_review: '待审核', published: '已发布', rejected: '已驳回', offline: '已下线', open: '待处理', acknowledged: '已确认', accepted: '处理中', resolved: '已解决', closed: '已关闭', pending: '待确认', active: '已授权' }; return labels[status] || status }

export function KnowledgePage() {
  const { data, loading, error, reload } = useData<Knowledge[]>('/platform/management/knowledge')
  const [filter, setFilter] = useState('all')
  const [editor, setEditor] = useState<Knowledge | 'new' | null>(null)
  const rows = (data || []).filter(item => filter === 'all' || item.status === filter)
  const pagination = useClientPagination(rows, filter)
  return <AppShell title="知识库治理"><ManagementState loading={loading} error={error} onRetry={reload}>
    <HelpTip label="发布说明">发布后的文档进入知识库；目前尚未用于智能问答检索。</HelpTip>
    <div className="page-toolbar"><select className="filter-select" aria-label="文档状态" value={filter} onChange={event => setFilter(event.target.value)}>{['all', 'draft', 'pending_review', 'rejected', 'published', 'offline'].map(status => <option key={status} value={status}>{status === 'all' ? '全部' : workflowLabel(status)}</option>)}</select><button className="primary-button" onClick={() => setEditor('new')}>+ 新建文档</button></div>
    {editor && <DetailDialog title={editor === 'new' ? '新建文档' : '编辑文档'} onClose={() => setEditor(null)}><KnowledgeForm key={editor === 'new' ? 'new' : editor.id} item={editor === 'new' ? undefined : editor} onClose={() => setEditor(null)} /></DetailDialog>}
    <Pagination {...pagination} />
    {!rows.length ? <div className="inline-empty">当前状态下没有知识文档。</div> : <div className="data-table-wrap"><table className="data-table"><thead><tr><th>文档</th><th>来源引用</th><th>状态 / 版本</th><th>操作</th></tr></thead><tbody>{pagination.items.map(item => <tr key={item.id}><td><strong>{item.title}</strong><div className="subtle">{item.subject} · {item.doc_type}</div>{item.rejection_reason && <p>驳回意见：{item.rejection_reason}</p>}</td><td>{item.source_name}<div className="subtle">{item.source_reference}</div></td><td><span className={'status-pill status-pill--' + workflowTone(item.status)}>{workflowLabel(item.status)}</span> {item.version}</td><td><KnowledgeActions item={item} onEdit={() => setEditor(item)} /></td></tr>)}</tbody></table></div>}
  </ManagementState></AppShell>
}

export function FeedbackPage() {
  const { data, loading, error, reload } = useData<Feedback[]>('/platform/management/feedback')
  const [filter, setFilter] = useState('all')
  const rows = (data || []).filter(item => filter === 'all' || item.status === filter)
  const pagination = useClientPagination(rows, filter)
  return <AppShell title="反馈运营"><ManagementState loading={loading} error={error} onRetry={reload}>
    <StatusFilter value={filter} onChange={setFilter} values={['all', 'open', 'acknowledged', 'resolved', 'closed']} />
    <Pagination {...pagination} />
    {!rows.length && <div className="inline-empty">当前没有符合条件的反馈。</div>}
    <div className="feedback-grid">{pagination.items.map(item => <article className="feedback-card" key={item.id}><div className="feedback-card__top"><strong>{item.category}</strong><span className={'status-pill status-pill--' + workflowTone(item.status)}>{workflowLabel(item.status)}</span></div><p>{item.note || '用户未填写补充说明。'}</p><p className="subtle">提交于 {item.created_at?.slice(0, 16).replace('T', ' ') || '—'}</p><WorkflowControls kind="feedback" item={item} /></article>)}</div>
  </ManagementState></AppShell>
}

function StatusFilter({ value, onChange, values }: { value: string; onChange: (value: string) => void; values: string[] }) {
  return <div className="page-toolbar"><select className="filter-select" aria-label="处理状态" value={value} onChange={event => onChange(event.target.value)}>{values.map(status => <option key={status} value={status}>{status === 'all' ? '全部' : workflowLabel(status)}</option>)}</select></div>
}

export function RiskPage() {
  const { data, loading, error, reload } = useData<Risk[]>('/platform/management/risks')
  const [filter, setFilter] = useState('all')
  const rows = (data || []).filter(item => filter === 'all' || item.status === filter)
  const pagination = useClientPagination(rows, filter)
  return <AppShell title="风险事件看板"><ManagementState loading={loading} error={error} onRetry={reload}>
    <StatusFilter value={filter} onChange={setFilter} values={['all', 'open', 'acknowledged', 'resolved', 'closed']} />
    <HelpTip label="处理说明">先确认事件，再填写实际处理结果。系统风险标记不等于最终判断。</HelpTip>
    <Pagination {...pagination} />
    {!rows.length && <div className="inline-empty">当前没有符合条件的风险事件。</div>}
    <div className="risk-list">{pagination.items.map(item => <article className={'risk-card risk-card--' + item.severity} key={item.id}><div className="risk-card__signal"><h3>{item.title}</h3><span>{({ low: '低风险', medium: '中风险', high: '高风险', critical: '严重' } as Record<string, string>)[item.severity]}</span><span className={'status-pill status-pill--' + workflowTone(item.status)}>{workflowLabel(item.status)}</span></div><p>{item.detail}</p><p className="subtle">来源：{item.source}</p><WorkflowControls kind="risk" item={item} /></article>)}</div>
  </ManagementState></AppShell>
}

export function HandoffPage() {
  const { data, loading, error, reload } = useData<Handoff[]>('/platform/management/handoffs')
  const [filter, setFilter] = useState('all')
  const rows = (data || []).filter(item => filter === 'all' || item.status === filter)
  const pagination = useClientPagination(rows, filter)
  return <AppShell title="人工转接"><ManagementState loading={loading} error={error} onRetry={reload}>
    <StatusFilter value={filter} onChange={setFilter} values={['all', 'open', 'accepted', 'resolved', 'closed']} />
    <HelpTip label="转接说明">接单后可回复学生；双方可刷新查看消息与处理记录。关闭或重新打开时须填写原因。</HelpTip>
    <Pagination {...pagination} />
    {!rows.length && <div className="inline-empty">当前没有符合条件的工单。</div>}
    <div className="handoff-list">{pagination.items.map(item => <article className="handoff-card" key={item.id}><div className="handoff-card__top"><h3>{item.reason}</h3><span className={'status-pill status-pill--' + workflowTone(item.status)}>{workflowLabel(item.status)}</span></div><p>{item.summary}</p><WorkflowControls kind="handoff" item={item} /><HumanConversation id={item.id} /></article>)}</div>
  </ManagementState></AppShell>
}

export function SchoolPage() {
  const { data, loading, error, reload } = useData<SchoolRow[]>('/platform/management/schools')
  const pagination = useClientPagination(data || [])
  return <AppShell title="学校运营" eyebrow="市级运营中心 / 学校运营"><ManagementState loading={loading} error={error} onRetry={reload} empty={!data?.length}><Pagination {...pagination} /><div className="school-cards">{pagination.items.map(school => <article className="school-card" key={school.id}><div className="school-card__top"><div><h3>{school.name}</h3><p>{school.code}</p></div><span>{school.status === 'active' ? '接入正常' : school.status}</span></div><div className="school-metrics"><div><strong>{school.students}</strong><span>学生</span></div><div><strong>{school.open_risks}</strong><span>待处理风险</span></div></div><div className="school-card__footer"><span>数据范围：本校汇总</span><Link className="action-link" to={'/ops/schools/' + school.id}>查看运营详情 ↗</Link></div></article>)}</div></ManagementState></AppShell>
}
