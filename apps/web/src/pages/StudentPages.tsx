import React, { useEffect, useMemo, useState } from 'react'
import { AppShell } from '../layouts/AppShell'
import { apiError, apiFetch } from '../services/api'
import './PlatformPages.css'

type Dashboard = {
  student: { id: string; name: string }
  latest_exam: { id: string; name: string; date: string | null; total_score: number; full_score: number; class_rank: number | null; grade_rank: number | null; score_delta: number | null } | null
  subjects: Array<{ name: string; score: number; full_score: number; percentage: number; class_rank: number | null; grade_rank: number | null }>
  exam_count: number; diagnosis_count: number; open_risks: number; open_handoffs: number
  parent_authorization: Authorization | null
}
type Authorization = { id: string; parent_name: string; parent_phone: string; share_code: string; scopes: string[]; status: string; expires_at: string | null; granted_at: string | null }
type TrendData = { exams: Array<{ id: string; name: string; date: string | null; score: number; full_score: number; class_rank: number | null; grade_rank: number | null }>; subjects: Array<{ subject: string; exam: string; date: string | null; score: number; full_score: number }>; subject_names: string[] }
type Diagnosis = { id: string; type: string; status: string; version: string | null; generated_at: string | null; exam_name: string | null; content: Record<string, unknown>; source: string }
type Mistake = { id: string; exam: string; subject: string; question_no: string; score: number; full_score: number; lost_score: number; answer_status: string | null; date: string | null }

function useJson<T>(path: string) {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const reload = async () => {
    setLoading(true); setError(null)
    try {
      const response = await apiFetch(path)
      if (!response.ok) throw await apiError(response, '加载数据失败')
      setData(await response.json() as T)
    } catch (err) { setError(err instanceof Error ? err.message : '加载数据失败') } finally { setLoading(false) }
  }
  useEffect(() => { void reload() }, [path])
  return { data, loading, error, reload }
}

function ContentState({ loading, error, empty, children }: { loading: boolean; error: string | null; empty?: boolean; children: React.ReactNode }) {
  if (loading) return <div className="loading-state">正在读取你的学习数据…</div>
  if (error) return <div className="error-state">{error}</div>
  if (empty) return <div className="empty-state"><div className="empty-state__icon">⌁</div><strong>还没有可展示的数据</strong><p>完成一次考试或导入成绩后，这里会自动生成分析。</p></div>
  return <>{children}</>
}

function StatCard({ label, value, hint, tone = 'mint' }: { label: string; value: string | number; hint: string; tone?: string }) {
  return <div className={`stat-card stat-card--${tone}`}><div className="stat-card__label">{label}</div><div className="stat-card__value">{value}</div><div className="stat-card__hint">{hint}</div></div>
}

export function StudentDashboardPage() {
  const { data, loading, error } = useJson<Dashboard>('/platform/student/dashboard')
  const exam = data?.latest_exam
  return <AppShell title={`你好，${data?.student.name || '同学'}`} eyebrow="学生空间 / 学习总览">
    <ContentState loading={loading} error={error}>
      <div className="welcome-row"><div><p className="welcome-caption">这是你最近的学习状态</p><div className="data-freshness"><span className="status-dot" /> {data?.exam_count ? '成绩数据已同步 · 可追溯' : '等待成绩数据接入'}</div></div><div className="quick-actions"><a href="/chat" className="primary-button">问问学习助手 <span>↗</span></a></div></div>
      <div className="stats-grid">
        <StatCard label="最近一次总分" value={exam ? `${exam.total_score} 分` : '—'} hint={exam?.score_delta == null ? '等待更多考试数据' : `${exam.score_delta >= 0 ? '较上次 +' : '较上次 '}${exam.score_delta} 分`} />
        <StatCard label="班级排名" value={exam?.class_rank ? `第 ${exam.class_rank} 名` : '—'} hint={exam?.name || '暂无考试记录'} tone="blue" />
        <StatCard label="诊断报告" value={data?.diagnosis_count || 0} hint="份正式报告" tone="purple" />
        <StatCard label="需要关注" value={(data?.open_risks || 0) + (data?.open_handoffs || 0)} hint="风险与老师跟进" tone="orange" />
      </div>
      <div className="content-grid content-grid--wide">
        <section className="panel panel--large"><div className="panel-heading"><div><h2>最近一次考试</h2><p>{exam?.name || '尚未同步考试成绩'}</p></div><span className="panel-heading__date">{exam?.date || '—'}</span></div>{exam ? <div className="score-hero"><div className="score-hero__number">{exam.total_score}<small> / {exam.full_score}</small></div><div className="score-hero__meta"><div>班级排名 <strong>第 {exam.class_rank || '—'} 名</strong></div><div>年级排名 <strong>第 {exam.grade_rank || '—'} 名</strong></div></div></div> : <div className="inline-empty">完成考试后会在这里看到总分与排名。</div>}</section>
        <section className="panel"><div className="panel-heading"><div><h2>学习状态</h2><p>系统工作流</p></div></div><div className="status-list"><StatusRow label="成绩同步" value={data?.exam_count ? '正常' : '待接入'} tone={data?.exam_count ? 'green' : 'gray'} /><StatusRow label="家长授权" value={data?.parent_authorization?.status === 'active' ? '已授权' : '待授权'} tone={data?.parent_authorization?.status === 'active' ? 'green' : 'amber'} /><StatusRow label="老师跟进" value={data?.open_handoffs ? `${data.open_handoffs} 条待处理` : '暂无'} tone={data?.open_handoffs ? 'amber' : 'gray'} /></div></section>
      </div>
      <section className="panel"><div className="panel-heading"><div><h2>科目表现</h2><p>按最近一次考试的得分率排序</p></div><a className="text-link" href="/trends">查看趋势 ↗</a></div><div className="subject-grid">{data?.subjects.length ? data.subjects.map(subject => <div className="subject-card" key={subject.name}><div className="subject-card__top"><strong>{subject.name}</strong><span>{subject.score} / {subject.full_score}</span></div><div className="progress-bar"><span style={{ width: `${subject.percentage}%` }} /></div><div className="subject-card__bottom"><span>得分率 {subject.percentage}%</span><span>年级 {subject.grade_rank ? `第 ${subject.grade_rank} 名` : '—'}</span></div></div>) : <div className="inline-empty">暂无科目成绩。</div>}</div></section>
    </ContentState>
  </AppShell>
}

function StatusRow({ label, value, tone }: { label: string; value: string; tone: string }) { return <div className="status-row"><span>{label}</span><span className={`status-pill status-pill--${tone}`}>{value}</span></div> }

export function StudentTrendsPage() {
  const { data, loading, error } = useJson<TrendData>('/platform/student/trends')
  const exams = data?.exams || []
  const max = Math.max(...exams.map(item => item.full_score || item.score), 1)
  const points = exams.map((item, index) => `${exams.length === 1 ? 50 : 50 + (index / (exams.length - 1)) * 670},${226 - (item.score / max) * 175}`).join(' ')
  return <AppShell title="成绩趋势" eyebrow="学生空间 / 成绩趋势"><ContentState loading={loading} error={error} empty={!exams.length}><section className="panel chart-panel"><div className="panel-heading"><div><h2>总分变化</h2><p>按考试时间排序，帮助你看见真实变化</p></div><span className="chart-legend"><i /> 我的总分</span></div><div className="line-chart"><svg viewBox="0 0 720 270" role="img" aria-label="总分趋势图"><line x1="50" y1="226" x2="720" y2="226" /><line x1="50" y1="138" x2="720" y2="138" /><line x1="50" y1="50" x2="720" y2="50" /><polyline points={points} fill="none" stroke="#63d2b0" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />{exams.map((item, index) => <circle key={item.id} cx={exams.length === 1 ? 50 : 50 + (index / (exams.length - 1)) * 670} cy={226 - (item.score / max) * 175} r="6" fill="#fff" stroke="#63d2b0" strokeWidth="3" />)}</svg><div className="chart-labels">{exams.map(item => <span key={item.id}>{item.name}</span>)}</div></div><div className="trend-table">{exams.map((item, index) => <div className="trend-row" key={item.id}><span className="trend-index">{String(index + 1).padStart(2, '0')}</span><strong>{item.name}</strong><span>{item.date || '—'}</span><b>{item.score} 分</b><span className={index > 0 && item.score >= exams[index - 1].score ? 'trend-up' : 'trend-down'}>{index === 0 ? '基准' : `${item.score - exams[index - 1].score >= 0 ? '+' : ''}${(item.score - exams[index - 1].score).toFixed(1)}`}</span></div>)}</div></section><section className="panel"><div className="panel-heading"><div><h2>科目趋势</h2><p>展开每个科目的连续变化</p></div></div><div className="subject-trend-list">{data?.subject_names.map(name => <SubjectTrend key={name} name={name} rows={(data?.subjects || []).filter(item => item.subject === name)} />)}</div></section></ContentState></AppShell>
}

function SubjectTrend({ name, rows }: { name: string; rows: TrendData['subjects'] }) { const first = rows[0]?.score || 0; const last = rows[rows.length - 1]?.score || 0; return <div className="subject-trend"><div><strong>{name}</strong><span>{rows.length} 次考试</span></div><div className="subject-trend__bar"><div className="mini-bars">{rows.map(row => <i key={`${row.exam}-${row.date}`} style={{ height: `${Math.max(12, row.score / row.full_score * 100)}%` }} title={`${row.exam} ${row.score}分`} />)}</div></div><b className={last >= first ? 'trend-up' : 'trend-down'}>{last >= first ? '+' : ''}{(last - first).toFixed(1)}</b></div> }

export function StudentDiagnosisPage() {
  const { data, loading, error } = useJson<Diagnosis[]>('/platform/student/diagnosis')
  return <AppShell title="诊断报告" eyebrow="学生空间 / 诊断报告"><ContentState loading={loading} error={error} empty={!data?.length}><div className="notice-banner"><span className="notice-banner__icon">◎</span><div><strong>诊断结论来自正式报告</strong><p>报告会标注考试来源与生成时间，智能助手只负责解释已确认的内容。</p></div></div><div className="report-grid">{data?.map(report => <ReportCard key={report.id} report={report} />)}</div></ContentState></AppShell>
}

function ReportCard({ report }: { report: Diagnosis }) { const c = report.content; const list = (key: string) => Array.isArray(c[key]) ? c[key] as string[] : []; return <article className="report-card"><div className="report-card__header"><div><span className="status-pill status-pill--green">已生成</span><h2>{report.exam_name || '综合学情诊断'}</h2></div><div className="report-card__meta">{report.generated_at?.slice(0, 10) || '—'}<br /><span>来源：{report.source}</span></div></div><p className="report-summary">{String(c.summary || '暂无摘要')}</p><div className="report-columns"><ReportList title="优势表现" items={list('strengths')} tone="mint" /><ReportList title="优先提升" items={list('areas_for_improvement')} tone="orange" /><ReportList title="知识薄弱点" items={list('knowledge_gaps')} tone="purple" /><ReportList title="行动建议" items={list('recommendations')} tone="blue" /></div><div className="citation-row">引用报告 {report.version || 'v1'} · {report.id.slice(0, 8)} <span>查看原始依据 ↗</span></div></article> }
function ReportList({ title, items, tone }: { title: string; items: string[]; tone: string }) { return <div className={`report-list report-list--${tone}`}><strong>{title}</strong>{items.length ? <ul>{items.map(item => <li key={item}>{item}</li>)}</ul> : <span className="subtle">报告未提供</span>}</div> }

export function StudentMistakesPage() {
  const { data, loading, error } = useJson<Mistake[]>('/platform/student/mistakes')
  const [subject, setSubject] = useState('全部科目')
  const subjects = useMemo(() => ['全部科目', ...Array.from(new Set((data || []).map(item => item.subject)))], [data])
  const rows = (data || []).filter(item => subject === '全部科目' || item.subject === subject)
  const loss = rows.reduce((sum, item) => sum + item.lost_score, 0)
  return <AppShell title="错题分析" eyebrow="学生空间 / 错题分析"><ContentState loading={loading} error={error} empty={!data?.length}><div className="stats-grid stats-grid--three"><StatCard label="累计丢分" value={`${loss.toFixed(1)} 分`} hint="来自已同步的小题记录" tone="orange" /><StatCard label="错题数量" value={rows.length} hint="按筛选条件统计" tone="purple" /><StatCard label="最高单题丢分" value={`${Math.max(...rows.map(item => item.lost_score), 0)} 分`} hint="建议优先复盘" tone="blue" /></div><div className="filter-row"><select className="filter-select" value={subject} onChange={event => setSubject(event.target.value)}>{subjects.map(item => <option key={item}>{item}</option>)}</select><span className="subtle">共 {rows.length} 条小题记录</span></div><div className="data-table-wrap"><table className="data-table"><thead><tr><th>考试</th><th>科目 / 题号</th><th>得分</th><th>丢分</th><th>答题状态</th><th>建议动作</th></tr></thead><tbody>{rows.map(item => <tr key={item.id}><td><strong>{item.exam}</strong><div className="subtle">{item.date || '—'}</div></td><td>{item.subject} · 第 {item.question_no} 题</td><td>{item.score} / {item.full_score}</td><td><span className="loss-number">-{item.lost_score}</span></td><td><span className="status-pill status-pill--amber">{item.answer_status === 'partial' ? '部分得分' : item.answer_status || '待复盘'}</span></td><td><button className="action-link">加入复盘</button></td></tr>)}</tbody></table></div></ContentState></AppShell>
}

export function StudentSupportPage() {
  const auth = useJson<Authorization[]>('/platform/student/authorization')
  const [parentName, setParentName] = useState(''); const [parentPhone, setParentPhone] = useState(''); const [message, setMessage] = useState(''); const [feedback, setFeedback] = useState('not_helpful'); const [supportMessage, setSupportMessage] = useState(''); const [saving, setSaving] = useState(false)
  const createAuthorization = async (event: React.FormEvent) => { event.preventDefault(); setSaving(true); try { const response = await apiFetch('/platform/student/authorization', { method: 'POST', body: JSON.stringify({ parent_name: parentName, parent_phone: parentPhone }) }); if (!response.ok) throw await apiError(response, '授权申请提交失败'); setMessage('授权申请已生成，请把授权码交给家长确认。'); setParentName(''); setParentPhone(''); await auth.reload() } catch (err) { setMessage(err instanceof Error ? err.message : '提交失败') } finally { setSaving(false) } }
  const submitFeedback = async (event: React.FormEvent) => { event.preventDefault(); setSaving(true); try { const response = await apiFetch('/platform/student/feedback', { method: 'POST', body: JSON.stringify({ rating: feedback, note: supportMessage, category: '产品反馈' }) }); if (!response.ok) throw await apiError(response, '反馈提交失败'); setMessage('感谢反馈，运营团队会在工作台跟进。'); setSupportMessage('') } catch (err) { setMessage(err instanceof Error ? err.message : '提交失败') } finally { setSaving(false) } }
  const requestHandoff = async () => { setSaving(true); try { const response = await apiFetch('/platform/student/handoffs', { method: 'POST', body: JSON.stringify({ reason: '学生主动请求人工协助', priority: 'normal', summary: '学生在支持中心请求老师跟进。' }) }); if (!response.ok) throw await apiError(response, '人工转接提交失败'); setMessage('已提交人工转接，老师会在工作时间内联系你。') } catch (err) { setMessage(err instanceof Error ? err.message : '提交失败') } finally { setSaving(false) } }
  return <AppShell title="家长与支持" eyebrow="学生空间 / 家长与支持"><div className="support-grid"><section className="panel"><div className="panel-heading"><div><h2>家长授权</h2><p>由你发起，家长确认后才能查看指定内容</p></div></div><div className="authorization-list">{auth.data?.map(item => <div className="authorization-row" key={item.id}><div><strong>{item.parent_name}</strong><span>{item.parent_phone}</span></div><div><span className={`status-pill status-pill--${item.status === 'active' ? 'green' : 'amber'}`}>{item.status === 'active' ? '已授权' : '待确认'}</span>{item.status === 'pending' && <b className="share-code">{item.share_code}</b>}</div></div>)}</div><form className="compact-form" onSubmit={createAuthorization}><label className="form-field"><span>家长称呼</span><input className="form-input" value={parentName} onChange={event => setParentName(event.target.value)} placeholder="例如：张女士" required /></label><label className="form-field"><span>手机号</span><input className="form-input" value={parentPhone} onChange={event => setParentPhone(event.target.value)} placeholder="用于确认身份" required /></label><button className="primary-button" disabled={saving}>生成授权申请</button></form></section><section className="panel"><div className="panel-heading"><div><h2>告诉我们</h2><p>问题、建议或需要人工帮助，都可以在这里提交</p></div></div>{message && <div className="success-message">{message}</div>}<form className="compact-form" onSubmit={submitFeedback}><label className="form-field"><span>这次体验如何</span><select className="form-select" value={feedback} onChange={event => setFeedback(event.target.value)}><option value="helpful">很有帮助</option><option value="not_helpful">需要改进</option><option value="data_wrong">数据有误</option><option value="inappropriate">内容不合适</option></select></label><label className="form-field"><span>补充说明</span><textarea className="form-textarea" value={supportMessage} onChange={event => setSupportMessage(event.target.value)} placeholder="写下你遇到的问题…" /></label><div className="support-buttons"><button className="secondary-button" type="submit" disabled={saving}>提交反馈</button><button className="primary-button" type="button" onClick={requestHandoff} disabled={saving}>联系老师 ↗</button></div></form></section></div></AppShell>
}
