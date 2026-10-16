import { useEffect, useRef, useState, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { DetailDialog } from '../../components/DetailDialog'
import { ErrorDisplay } from '../../components/ErrorDisplay'
import { useJsonQuery } from '../../hooks/useApi'
import { apiFetch, apiError } from '../../services/api'
import { randomKey } from '../../utils/id'
import { QueryState, Table, Pager, usePagination, type Row } from './shared'
import './exam-workbench.css'

export const EXAM_ROOT = '/platform/education/exam-management'
const SCORE_TYPES: Record<string, string> = { student: '个人单科成绩', classSubject: '班级单科成绩', gradeSubject: '年级单科成绩', classAll: '班级综合成绩', gradeAll: '年级综合成绩', school: '全校综合成绩' }
const DIAG_TYPES: Record<string, string> = { student: '个人学情诊断', classAll: '班级综合诊断', classSubject: '班级单科诊断', gradeAll: '年级综合诊断', gradeSubject: '年级单科诊断', school: '全校学情诊断' }
const ESSAY_TYPES: Record<string, string> = { chinese: '语文', english: '英语' }
const DEFAULT_SUBJECTS = [['语文', 150], ['数学', 150], ['英语', 150], ['物理', 100], ['化学', 100], ['生物', 100]] as const
type Person = { id: string; platform_id: string; name: string; account: string; grade: string; class_number: string; class_id?: string | null; academic_year?: string }
type ExamSubject = { key: string; subject_id?: string; name: string; full_score: number | string; student_ids: string[] }
type ExamData = { id: string; exam_id: string; revision: number; name: string; academic_year: string; exam_date: string; participant_count: number; subjects: ExamSubject[]; snapshots: Record<string, Person>; score_files: Record<string, { id: string; filename: string; row_count: number }>; teacher_permissions: Record<string, any>; student_permissions: Record<string, { subjects: string[] }>; open_state_label: string; open_state: string }
type ScopeOptions = { current_year: string; academic_year: string; years: string[]; students: Person[]; school: string }
type Preview = { configuration: any; preview_hash: string; participant_count: number; duplicates: Array<{ id: string; name: string }>; summary: Record<string, Record<string, number>>; changes: Array<{ subject: string; before: ExamSubject | null; after: ExamSubject | null; added: string[]; removed: string[] }>; linked_data: { score_records?: number; reports?: number }; permission_note: string }
type View = 'create' | 'config' | 'adjust' | 'import' | 'scores' | 'permissions' | 'logs' | null

export async function examRequest<T>(path: string, body?: unknown, method = 'POST', key?: string): Promise<T> {
  const response = await apiFetch(EXAM_ROOT + path, { method, body: body === undefined ? undefined : JSON.stringify(body), headers: key ? { 'Idempotency-Key': key } : undefined })
  if (!response.ok) throw await apiError(response, '考务操作失败，请重试')
  return response.json() as Promise<T>
}

export async function examDownload(path: string, filename: string, body?: unknown): Promise<string> {
  const response = await apiFetch(EXAM_ROOT + path, { method: body === undefined ? 'GET' : 'POST', body: body === undefined ? undefined : JSON.stringify(body) })
  if (!response.ok) throw await apiError(response, '文件下载失败')
  const blob = await response.blob(), url = URL.createObjectURL(blob)
  const anchor = document.createElement('a'); anchor.href = url; anchor.download = filename; document.body.append(anchor); anchor.click(); anchor.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
  return response.headers.get('X-Exam-Preview-Hash') || ''
}

async function uploadBody(file: File) {
  if (file.size > 10_000_000) throw new Error('Excel 文件不能超过 10 MB')
  const bytes = new Uint8Array(await file.arrayBuffer())
  let binary = ''
  for (let i = 0; i < bytes.length; i += 8192) binary += String.fromCharCode(...bytes.subarray(i, i+8192))
  return { filename: file.name, content_base64: btoa(binary) }
}

function useJob() {
  const [busy, setBusy] = useState(false), [error, setError] = useState<Error | null>(null)
  const locked = useRef(false)
  async function run<T>(job: () => Promise<T>): Promise<T | undefined> {
    if (locked.current) return
    locked.current = true; setBusy(true); setError(null)
    try { return await job() } catch (error) { setError(error as Error) } finally { locked.current = false; setBusy(false) }
  }
  return { busy, error, setError, run }
}
type Job = ReturnType<typeof useJob>
const JobError = ({ job }: { job: Job }) => <ErrorDisplay error={job.error} variant="banner" title="操作未完成" onDismiss={() => job.setError(null)} />
const groupKey = (p: Person) => `${p.grade} / ${p.class_number}`
const unique = (ids: string[]) => [...new Set(ids)]
const toggle = (ids: string[], id: string, checked: boolean) => checked ? unique([...ids, id]) : ids.filter(value => value !== id)
const gradeLabel = (grade: string) => ({ '1': '小学一年级', '2': '小学二年级', '3': '小学三年级', '4': '小学四年级', '5': '小学五年级', '6': '小学六年级', '7': '初中一年级', '8': '初中二年级', '9': '初中三年级', '10': '高中一年级', '11': '高中二年级', '12': '高中三年级' }[grade] || grade)
const classLabel = (key: string) => { const [grade, number = ''] = key.split(' / '); return `${gradeLabel(grade)} ${number}${number.endsWith('班') ? '' : '班'}` }
const dateLabel = (value: string) => new Date(value).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false })

function MixedCheck({ checked, mixed = false, onChange, children, disabled = false, label }: { checked: boolean; mixed?: boolean; onChange: (checked: boolean) => void; children: ReactNode; disabled?: boolean; label?: string }) {
  const ref = useRef<HTMLInputElement>(null)
  useEffect(() => { if (ref.current) ref.current.indeterminate = mixed }, [mixed])
  return <label className="exam-check"><input ref={ref} type="checkbox" checked={checked} aria-label={label} aria-checked={mixed ? 'mixed' : checked} disabled={disabled} onChange={event => onChange(event.target.checked)} />{children}</label>
}

export function ExamWorkbench({ writable }: { writable: boolean }) {
  const [filters, setFilters] = useState({ search: '', academic_year: '', state: '', grade: '', subject: '' })
  const pagination = usePagination(JSON.stringify(filters)), { page, pageSize } = pagination
  const list = useJsonQuery<{ items: ExamData[]; total: number; grades: string[]; subjects: string[] }>(`${EXAM_ROOT}?${new URLSearchParams({ ...filters, page: String(page), page_size: String(pageSize) })}`)
  const scope = useJsonQuery<ScopeOptions>(`${EXAM_ROOT}/options`)
  const [view, setView] = useState<View>(null), [selectedId, setSelectedId] = useState(''), [notice, setNotice] = useState('')
  const detail = useJsonQuery<ExamData>(`${EXAM_ROOT}/${selectedId}`, !!selectedId && !!view && !['create', 'logs'].includes(view))
  const client = useQueryClient()
  const open = (next: View, id = '') => { setSelectedId(id); setView(next) }
  const changed = async () => { await client.invalidateQueries({ predicate: query => !['chat', 'route-identity'].includes(String(query.queryKey[0])) }) }
  const titles = { create: '创建考试 · 科目与参试范围', config: '考试配置', adjust: '调整科目与参试范围', import: '导入成绩 Excel', scores: '已导入成绩查看', permissions: '考试成绩开放设置', logs: '操作记录' }
  return <section className="exam-workbench" aria-label="考务管理">
    <div className="exam-heading"><div><h2>考试列表</h2><p>创建考试、导入成绩，并为教师和学生配置查询权限。</p></div><div className="exam-actions">{writable && <button className="primary-button" onClick={() => open('create')}>＋ 创建考试</button>}<button onClick={() => open('logs')}>操作记录</button></div></div>
    {notice && <p className="exam-success" role="status">{notice}</p>}
    <div className="exam-filters"><input aria-label="搜索考试" placeholder="搜索考试名称 / 考试ID" value={filters.search} onChange={e => setFilters({ ...filters, search: e.target.value })} />
      <select aria-label="考试学年筛选" value={filters.academic_year} onChange={e => setFilters({ ...filters, academic_year: e.target.value })}><option value="">全部学年</option>{scope.data?.years.map(y => <option key={y}>{y}</option>)}</select>
      <select aria-label="成绩开放状态筛选" value={filters.state} onChange={e => setFilters({ ...filters, state: e.target.value })}><option value="">全部开放状态</option><option value="none">未开放</option><option value="part">部分开放</option><option value="open">已开放</option></select>
      <select aria-label="年级筛选" value={filters.grade} onChange={e => setFilters({ ...filters, grade: e.target.value })}><option value="">全部年级</option>{list.data?.grades.map(g => <option key={g} value={g}>{gradeLabel(g)}</option>)}</select>
      <select aria-label="科目筛选" value={filters.subject} onChange={e => setFilters({ ...filters, subject: e.target.value })}><option value="">全部科目</option>{list.data?.subjects.map(s => <option key={s}>{s}</option>)}</select>
    </div>
    <QueryState query={list}><Table headers={['考试名称', '考试ID', '考试学年', '考试日期', '科目', '参试人数', '成绩开放', '操作']}>
      {list.data?.items.map(exam => <tr key={exam.id}><td><strong>{exam.name}</strong><div className="exam-muted">{Object.keys(exam.score_files).length ? `已导入 ${Object.keys(exam.score_files).length}/${exam.subjects.length} 科` : '待导入成绩'}</div></td><td className="exam-code">{exam.exam_id}</td><td>{exam.academic_year}</td><td>{exam.exam_date}</td><td>{exam.subjects.length} 科</td><td>{exam.participant_count} 人</td><td><span className={`exam-tag ${exam.open_state}`}>{exam.open_state_label}</span><div className="exam-muted">教师已授权 {Object.keys(exam.teacher_permissions).length} 人<br />学生已授权 {Object.keys(exam.student_permissions).length}/{exam.participant_count} 人</div></td><td><div className="exam-row-actions">{writable && <><button onClick={() => open('adjust', exam.id)}>调整考试范围</button><button onClick={() => open('import', exam.id)}>导入成绩</button></>}<button disabled={!Object.keys(exam.score_files).length} onClick={() => open('scores', exam.id)}>查看已导入成绩</button>{writable && <button disabled={!Object.keys(exam.score_files).length} onClick={() => open('permissions', exam.id)}>成绩开放设置</button>}<button onClick={() => open('config', exam.id)}>查看配置</button></div></td></tr>)}
    </Table>{!list.data?.items.length && <p className="inline-empty">没有匹配的考试。{writable ? '可点击“创建考试”开始配置。' : '请调整筛选条件。'}</p>}</QueryState>
    {list.data && <Pager {...pagination} total={list.data.total} />}
    {view && <DetailDialog title={titles[view]} onClose={() => setView(null)}><div className="exam-dialog">
      {view === 'create' ? <ExamEditor onSaved={async exam => { await changed(); setSelectedId(exam.id); setView('import'); setNotice(`考试 ${exam.exam_id} 创建成功，查询默认未开放。`) }} onCancel={() => setView(null)} /> : view === 'logs' ? <ExamLogs /> : <QueryState query={detail}>{detail.data && <>
        <div className="exam-context"><strong>{detail.data.name}</strong><span>{detail.data.exam_id} · {detail.data.academic_year}</span></div>
        {view === 'config' && <ExamConfiguration exam={detail.data} />}
        {view === 'adjust' && <ExamEditor key={detail.data.id} exam={detail.data} onSaved={async () => { await changed(); setView('config'); setNotice('考试范围已调整，已有查询权限未扩大。') }} onCancel={() => setView(null)} />}
        {view === 'import' && <ScoreImport key={`${detail.data.id}:${detail.data.revision}`} exam={detail.data} onChanged={changed} onScores={() => setView('scores')} />}
        {view === 'scores' && <ScoreFiles exam={detail.data} writable={writable} onChanged={changed} onImport={() => setView('import')} />}
        {view === 'permissions' && <ExamPermissions exam={detail.data} onChanged={changed} />}
      </>}</QueryState>}
    </div></DetailDialog>}
  </section>
}

function StudentPicker({ people, selected, onChange, disabled = false }: { people: Person[]; selected: string[]; onChange: (ids: string[]) => void; disabled?: boolean }) {
  const [search, setSearch] = useState(''), [expanded, setExpanded] = useState<string[]>([])
  const visible = people.filter(p => `${p.name} ${p.platform_id} ${p.account}`.includes(search))
  const groups = [...new Set(visible.map(groupKey))].sort()
  const setGroup = (ids: string[], checked: boolean) => onChange(checked ? unique([...selected, ...ids]) : selected.filter(id => !ids.includes(id)))
  return <div className="exam-picker"><div className="exam-actions"><input aria-label="搜索参试学生" placeholder="搜索姓名 / 学生ID / 账号" value={search} onChange={e => setSearch(e.target.value)} /><button disabled={disabled} onClick={() => setGroup(visible.map(p => p.id), true)}>全选筛选结果</button><button disabled={disabled} onClick={() => setGroup(visible.map(p => p.id), false)}>清除筛选结果</button><span>已选 {selected.length} 人</span></div>
    {!groups.length && <p className="inline-empty">当前学年、年级及班级下没有可选学生。</p>}
    {groups.map(group => { const rows = visible.filter(p => groupKey(p) === group), count = rows.filter(p => selected.includes(p.id)).length, open = expanded.includes(group) || !!search
      return <div className="exam-class" key={group}><div className="exam-class-heading"><MixedCheck label={`全选${classLabel(group)}`} disabled={disabled} checked={count === rows.length} mixed={count > 0 && count < rows.length} onChange={checked => setGroup(rows.map(p => p.id), checked)}>{classLabel(group)}</MixedCheck><span className="exam-muted">已选 {count} / {rows.length} 人</span><button aria-expanded={open} onClick={() => setExpanded(toggle(expanded, group, !open))}>{open ? '收起' : '展开'}</button></div>{open && <div className="exam-student-rows">{rows.map(p => <label key={p.id} className="exam-student-row"><input type="checkbox" aria-label={`选择${p.name} ${p.platform_id}`} disabled={disabled} checked={selected.includes(p.id)} onChange={e => onChange(toggle(selected, p.id, e.target.checked))} /><strong>{p.name}</strong><span>{p.account}</span><span className="exam-code">{p.platform_id}</span></label>)}</div>}</div> })}
  </div>
}

function ExamEditor({ exam, onSaved, onCancel }: { exam?: ExamData; onSaved: (exam: ExamData) => Promise<void>; onCancel: () => void }) {
  const [step, setStep] = useState(1), [name, setName] = useState(exam?.name || ''), [year, setYear] = useState(exam?.academic_year || ''), [date, setDate] = useState(exam?.exam_date || new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' }))
  const defaults = () => DEFAULT_SUBJECTS.map(([name, full_score], i) => ({ key: `s${i}`, name, full_score, student_ids: [] as string[] }))
  const [subjects, setSubjects] = useState<ExamSubject[]>(exam?.subjects || defaults()), [grades, setGrades] = useState<string[]>([]), [classes, setClasses] = useState<string[]>([]), [base, setBase] = useState<string[]>([]), [active, setActive] = useState(exam?.subjects[0]?.key || 's0')
  const [preview, setPreview] = useState<Preview | null>(null), [confirmed, setConfirmed] = useState(false)
  const scope = useJsonQuery<ScopeOptions>(`${EXAM_ROOT}/options${year ? '?academic_year='+encodeURIComponent(year) : ''}`)
  const job = useJob(), key = useRef(randomKey())
  const selectedYear = year || scope.data?.current_year || ''
  const currentPeople = scope.data?.students || []
  const sameYear = !!exam && selectedYear === exam.academic_year
  const people = sameYear ? [...currentPeople, ...Object.values(exam.snapshots).filter(p => !currentPeople.some(c => c.id === p.id))] : currentPeople
  const allGrades = unique(people.map(p => p.grade)).sort(), allClasses = unique(people.filter(p => grades.includes(p.grade)).map(groupKey)).sort()
  const filteredPeople = sameYear ? people : people.filter(p => grades.includes(p.grade) && classes.includes(groupKey(p)))
  const body = () => ({ name: name.trim(), academic_year: selectedYear, exam_date: date, subjects: subjects.map(s => ({ ...s, full_score: Number(s.full_score) })), ...(exam ? { expected_revision: exam.revision } : {}) })
  const updateSubject = (key: string, values: Partial<ExamSubject>) => { setSubjects(subjects.map(s => s.key === key ? { ...s, ...values } : s)); setPreview(null); setConfirmed(false) }
  const nextBasic = () => {
    if (!name.trim() || !selectedYear || !date || !subjects.length || subjects.some(s => !s.name.trim() || !Number.isFinite(Number(s.full_score)) || Number(s.full_score) <= 0) || unique(subjects.map(s => s.name.trim().toLowerCase())).length !== subjects.length) { job.setError(new Error('请填写考试名称、学年、有效日期，至少保留一个不重复的科目且满分大于 0。')); return }
    job.setError(null); setStep(sameYear ? 3 : 2)
  }
  const nextClasses = () => {
    const ids = currentPeople.filter(p => classes.includes(groupKey(p))).map(p => p.id)
    if (!ids.length) { job.setError(new Error('请选择有正常在读学生的年级和班级。')); return }
    setBase(ids); setSubjects(subjects.map(s => ({ ...s, student_ids: s.student_ids.length ? s.student_ids.filter(id => ids.includes(id)) : ids }))); setStep(3); job.setError(null)
  }
  const nextPreview = () => job.run(async () => { const checked = await examRequest<Preview>(exam ? `/${exam.id}/preview` : '/preview', body()); setPreview(checked); setConfirmed(false); setStep(4) })
  const current = subjects.find(s => s.key === active) || subjects[0]
  return <div className="exam-editor"><ol className="exam-steps">{['基本信息与科目', '年级与班级', '参试学生', exam ? '差异预览与保存' : '预览与创建'].map((label, i) => <li key={label} className={step === i+1 ? 'active' : step > i+1 ? 'done' : ''}>{i+1}. {label}</li>)}</ol>
    <JobError job={job} />
    {step === 1 && <><h3>考试基本信息</h3><div className="exam-fields"><label>考试名称 <span>*</span><input aria-label="考试名称" required maxLength={200} value={name} onChange={e => setName(e.target.value)} /></label><label>考试学年 <span>*</span><select aria-label="考试学年" value={selectedYear} onChange={e => { setYear(e.target.value); setGrades([]); setClasses([]); setBase([]); setSubjects(subjects.map(s => ({ ...s, student_ids: [] }))) }}><option value="">请选择学年</option>{scope.data?.years.map(y => <option key={y}>{y}</option>)}</select></label><label>考试日期 <span>*</span><input aria-label="考试日期" type="date" required value={date} onChange={e => setDate(e.target.value)} /></label></div><p className="exam-muted">考试学年决定读取哪一届的年级、班级与学生。</p>{exam && !sameYear && <p className="exam-warning">修改学年后，请按新学年重新选择参试年级、班级与学生。已有成绩和报告保留，原有查询权限不会自动扩大。</p>}
      <h3>考试科目与满分</h3><div className="exam-subject-edit">{subjects.map((s, i) => <div key={s.key}><input aria-label={`科目名称${i+1}`} maxLength={100} placeholder="科目名称" value={s.name} onChange={e => updateSubject(s.key, { name: e.target.value })} /><input aria-label={`科目满分${i+1}`} type="number" min="0.01" max="10000" step="0.01" value={s.full_score} onChange={e => updateSubject(s.key, { full_score: e.target.value })} /><button onClick={() => setSubjects(subjects.filter(item => item.key !== s.key))}>删除</button></div>)}</div><div className="exam-actions"><button onClick={() => setSubjects([...subjects, { key: randomKey(), name: '', full_score: 100, student_ids: exam ? unique(exam.subjects.flatMap(s => s.student_ids)) : [] }])}>＋ 添加科目</button>{!exam && <button onClick={() => setSubjects(defaults())}>恢复默认科目</button>}</div>
    </>}
    {step === 2 && <QueryState query={scope}><h3>选择参试年级与班级</h3><div className="exam-option-grid">{allGrades.map(g => <MixedCheck key={g} checked={grades.includes(g)} onChange={checked => { setGrades(toggle(grades, g, checked)); const keys = unique(currentPeople.filter(p => p.grade === g).map(groupKey)); setClasses(checked ? unique([...classes, ...keys]) : classes.filter(c => !keys.includes(c))) }}>{gradeLabel(g)}</MixedCheck>)}</div><div className="exam-option-grid">{allClasses.map(c => <MixedCheck key={c} checked={classes.includes(c)} onChange={checked => setClasses(toggle(classes, c, checked))}>{classLabel(c)}（{currentPeople.filter(p => groupKey(p) === c).length} 人）</MixedCheck>)}</div>{!currentPeople.length && <p className="inline-empty">本学年没有状态为“正常”且有年级班级记录的学生。请先在学生档案中导入或建档。</p>}</QueryState>}
    {step === 3 && <><h3>选择并核对参试学生</h3><p className="exam-muted">各科分别核对名单，同一科目按学生ID去重；创建时只可选择本校正常在读学生。</p><div className="exam-tabs">{subjects.map(s => <button key={s.key} className={current?.key === s.key ? 'active' : ''} onClick={() => setActive(s.key)}>{s.name || '未命名科目'} · {s.student_ids.length} 人</button>)}</div>{current && <StudentPicker key={current.key} people={filteredPeople} selected={current.student_ids} onChange={ids => updateSubject(current.key, { student_ids: ids })} />}{!exam && <button onClick={() => setSubjects(subjects.map(s => ({ ...s, student_ids: base })))}>各科恢复所选班级完整名单</button>}</>}
    {step === 4 && preview && <><div className="exam-summary"><strong>{name}</strong><span>{selectedYear} · {date}</span><span>共 {subjects.length} 科 · 去重后 {preview.participant_count} 人</span></div>{preview.duplicates.length > 0 && <div className="exam-warning">同学年已有同名考试，请核对是否重复创建：{preview.duplicates.map(e => e.id).join('、')}。确认后仍可创建，系统会生成不同考试ID。</div>}<Table headers={['科目', '满分', '参试人数']} >{subjects.map(s => <tr key={s.key}><td>{s.name}</td><td>{s.full_score}</td><td>{s.student_ids.length} 人</td></tr>)}</Table><h3>年级、班级与科目汇总</h3><Table headers={['年级 / 班级', ...subjects.map(s => s.name)]}>{Object.entries(preview.summary).map(([group, counts]) => <tr key={group}><td>{classLabel(group)}</td>{subjects.map(s => <td key={s.key}>{counts[s.name] || 0} 人</td>)}</tr>)}</Table>
      {exam && <><h3>基本信息变更</h3><Table headers={['项目', '调整前', '调整后']}>{[['考试名称', exam.name, name.trim()], ['考试学年', exam.academic_year, selectedYear], ['考试日期', exam.exam_date, date]].map(([label, before, after]) => <tr key={label}><td>{label}</td><td>{before}</td><td>{after}</td></tr>)}</Table><h3>前后差异与关联数据</h3><p>已有成绩 {preview.linked_data.score_records || 0} 条 · 已有报告 {preview.linked_data.reports || 0} 份</p><Table headers={['科目', '调整前', '调整后', '名单差异']}>{preview.changes.map((change, i) => <tr key={i}><td>{change.subject}</td><td>{change.before ? `${change.before.name} · 满分 ${change.before.full_score} · ${change.before.student_ids.length} 人` : '未配置'}</td><td>{change.after ? `${change.after.name} · 满分 ${change.after.full_score} · ${change.after.student_ids.length} 人` : '移除（保留历史关联数据）'}</td><td>新增 {change.added.length} 人 / 移除 {change.removed.length} 人</td></tr>)}</Table><p className="exam-warning">{preview.permission_note}</p></>}
      <div className="exam-actions"><button disabled={job.busy} onClick={() => job.run(() => examDownload(exam ? `/${exam.id}/roster-preview` : '/preview/roster', '参试名单.xlsx', body()))}>下载参试名单（Excel）</button></div><MixedCheck checked={confirmed} onChange={setConfirmed}>我已核对考试配置、各科名单{exam ? '及前后差异，确认保存调整（不自动扩大原授权）' : '，确认创建本次考试'}</MixedCheck>
    </>}
    <div className="exam-footer">{step > 1 && <button disabled={job.busy} onClick={() => { setStep(step === 3 && sameYear ? 1 : step-1); setPreview(null); setConfirmed(false) }}>上一步</button>}<button disabled={job.busy} onClick={onCancel}>{exam ? '取消本次调整' : '取消本次创建'}</button>{step === 1 && <button className="primary-button" disabled={scope.isFetching} onClick={nextBasic}>校验并下一步</button>}{step === 2 && <button className="primary-button" onClick={nextClasses}>下一步：选择参试学生</button>}{step === 3 && <button className="primary-button" disabled={job.busy || subjects.some(s => !s.student_ids.length)} onClick={nextPreview}>下一步：{exam ? '差异预览' : '预览'}</button>}{step === 4 && <button className="primary-button" disabled={job.busy || !confirmed} onClick={() => job.run(async () => { const result = await examRequest<ExamData>(exam ? `/${exam.id}` : '', { ...body(), preview_hash: preview?.preview_hash }, exam ? 'PUT' : 'POST', key.current); await onSaved(result) })}>{job.busy ? '正在保存…' : exam ? '确认保存调整' : '确认创建'}</button>}</div>
  </div>
}

function ExamConfiguration({ exam }: { exam: ExamData }) {
  const [subject, setSubject] = useState(exam.subjects[0]?.key)
  const current = exam.subjects.find(s => s.key === subject) || exam.subjects[0]
  return <><div className="exam-summary"><span>考试日期 {exam.exam_date}</span><span>参试 {exam.participant_count} 人</span><span>教师已授权 {Object.keys(exam.teacher_permissions).length} 人 · 学生已授权 {Object.keys(exam.student_permissions).length} 人</span></div><Table headers={['科目', '满分', '参试人数', '成绩文件']}>{exam.subjects.map(s => <tr key={s.key}><td>{s.name}</td><td>{s.full_score}</td><td>{s.student_ids.length}</td><td>{exam.score_files[s.subject_id || '']?.filename || '未导入'}</td></tr>)}</Table><h3>参试名单（考试学年快照）</h3><div className="exam-tabs">{exam.subjects.map(s => <button key={s.key} className={current?.key === s.key ? 'active' : ''} onClick={() => setSubject(s.key)}>{s.name}</button>)}</div><Table paginate headers={['学生ID', '姓名', '账号', '考试学年', '年级 / 班级']}>{current?.student_ids.map(id => { const s = exam.snapshots[id]; return <tr key={id}><td>{s.platform_id}</td><td>{s.name}</td><td>{s.account}</td><td>{exam.academic_year}</td><td>{classLabel(groupKey(s))}</td></tr> })}</Table></>
}

function ScoreImport({ exam, onChanged, onScores }: { exam: ExamData; onChanged: () => Promise<void>; onScores: () => void }) {
  const [subject, setSubject] = useState(exam.subjects[0]?.subject_id || ''), [file, setFile] = useState<File | null>(null), [batch, setBatch] = useState<Row | null>(null), [message, setMessage] = useState('')
  const job = useJob(), existing = exam.score_files[subject]
  return <><JobError job={job} />{message && <p className="exam-success" role="status">{message}</p>}<label className="exam-label">导入科目<select aria-label="导入科目" disabled={job.busy} value={subject} onChange={e => { setSubject(e.target.value); setFile(null); setBatch(null); setMessage('') }}>{exam.subjects.map(s => <option key={s.key} value={s.subject_id}>{s.name}（{exam.score_files[s.subject_id || ''] ? '已导入' : '未导入'}）</option>)}</select></label><div className="exam-actions"><button disabled={job.busy} onClick={() => job.run(() => examDownload(`/${exam.id}/score-template/${subject}`, `成绩模板_${exam.exam_id}_${exam.subjects.find(s => s.subject_id === subject)?.name}.xlsx`))}>下载成绩模板（Excel）</button></div><p className="exam-note">模板固定 9 列：序号 / 考生号 / 姓名 / 行政班 / 学校 / 准考证号 / 分数 / 客观分 / 主观分。已预填本次该科完整参试名单，填写“分数”即可；有小题时在“主观分”后添加题号列，小题数与题号以文件表头为准。准考证号使用学生ID。</p>
    {existing ? <div className="exam-warning">该科已有完整成绩文件：{existing.filename}。请先在“查看已导入成绩”中删除后重新导入。<button onClick={onScores}>查看已导入成绩</button></div> : <><label className="exam-upload">选择成绩 Excel<input key={subject} aria-label="选择成绩 Excel" type="file" accept=".xlsx,.xls" disabled={job.busy} onChange={e => { setFile(e.target.files?.[0] || null); setBatch(null); setMessage('') }} /></label><p className="exam-muted">{file?.name || '未选择文件'}</p><button disabled={!file || job.busy} onClick={() => job.run(async () => { const result = await examRequest<Row>(`/${exam.id}/score-files`, { ...await uploadBody(file!), subject_id: subject, expected_revision: exam.revision }); setBatch(result) })}>校验文件</button>
      {batch && <div className={batch.status === 'validated' ? 'exam-success' : 'exam-warning'} role="status">{batch.status === 'validated' ? `完整名单校验通过：${batch.row_count} 人。尚未写入成绩。` : <><strong>校验未通过，未写入成绩。</strong><ul>{batch.errors.map((error: string, i: number) => <li key={i}>{error}</li>)}</ul></>}</div>}
      <div className="exam-footer"><button className="primary-button" disabled={job.busy || batch?.status !== 'validated'} onClick={() => job.run(async () => { await examRequest(`/${exam.id}/score-files/${batch!.id}/confirm`); setMessage('成绩导入成功，教师和学生查询仍须由运营管理员另行开放。'); await onChanged(); onScores() })}>{job.busy ? '正在导入…' : '确认导入'}</button></div></>}
  </>
}

function ScoreFiles({ exam, writable, onChanged, onImport }: { exam: ExamData; writable: boolean; onChanged: () => Promise<void>; onImport: () => void }) {
  const [deleting, setDeleting] = useState(''), job = useJob()
  return <><JobError job={job} />{exam.subjects.map(subject => { const file = exam.score_files[subject.subject_id || '']; return <article className="exam-card" key={subject.key}><h3>{subject.name} <span className={`exam-tag ${file ? 'open' : 'none'}`}>{file ? '已导入' : '未导入'}</span></h3><p>{file?.row_count || 0} / {subject.student_ids.length} 人</p>{file ? <><p className="exam-filename">{file.filename}</p><div className="exam-actions"><button disabled={job.busy} onClick={() => job.run(() => examDownload(`/${exam.id}/score-files/${file.id}/original`, file.filename))}>下载查看</button>{writable && <button disabled={job.busy} onClick={() => setDeleting(subject.subject_id!)}>删除成绩文件</button>}</div>{deleting === subject.subject_id && <div className="exam-warning">删除后该科成绩、小题明细及成绩查询授权将清除，报告原件保留。重新导入后须重新授权。<div className="exam-actions"><button disabled={job.busy} onClick={() => setDeleting('')}>取消</button><button disabled={job.busy} onClick={() => job.run(async () => { await examRequest(`/${exam.id}/score-files/${subject.subject_id}/delete`, { expected_revision: exam.revision }); setDeleting(''); await onChanged() })}>确认删除</button></div></div>}</> : writable && <button onClick={onImport}>导入该科成绩</button>}</article> })}</>
}

function ExamPermissions({ exam, onChanged }: { exam: ExamData; onChanged: () => Promise<void> }) {
  const [tab, setTab] = useState('teacher')
  return <><div className="exam-tabs"><button className={tab === 'teacher' ? 'active' : ''} onClick={() => setTab('teacher')}>1. 教师查询控制</button><button className={tab === 'student' ? 'active' : ''} onClick={() => setTab('student')}>2. 学生查询控制</button></div>{tab === 'teacher' ? <TeacherPermissions key={exam.revision} exam={exam} onChanged={onChanged} /> : <StudentPermissions key={exam.revision} exam={exam} onChanged={onChanged} />}</>
}

function Checks({ title, catalog, selected, onChange, disabled }: { title: string; catalog: Record<string, string>; selected: string[]; onChange: (values: string[]) => void; disabled?: (key: string) => boolean }) {
  return <fieldset className="exam-permission-group"><legend>{title}</legend><div className="exam-option-grid">{Object.entries(catalog).map(([key, label]) => <MixedCheck key={key} label={title+'：'+label} checked={selected.includes(key)} disabled={disabled?.(key)} onChange={checked => onChange(toggle(selected, key, checked))}>{label}</MixedCheck>)}</div></fieldset>
}

function TeacherPermissions({ exam, onChanged }: { exam: ExamData; onChanged: () => Promise<void> }) {
  const teachers = useJsonQuery<{ items: Row[]; default_rules: Array<{ role: string; label: string; types: string[]; subjects: string; scope: string }> }>(`${EXAM_ROOT}/teachers?exam_id=${exam.id}`)
  const [selected, setSelected] = useState<string[]>([]), [active, setActive] = useState(''), [drafts, setDrafts] = useState<Record<string, any>>({})
  const [filters, setFilters] = useState({ search: '', grade: '', classroom: '', subject: '', duty: '' }), [notice, setNotice] = useState(''), job = useJob()
  const errorRef = useRef<HTMLDivElement>(null)
  useEffect(() => { if (job.error) errorRef.current?.scrollIntoView({ block: 'start', behavior: 'smooth' }) }, [job.error])
  const teacherRows = teachers.data?.items || []
  const snapshots = Object.values(exam.snapshots).filter(p => exam.subjects.some(s => s.student_ids.includes(p.id)))
  const grades = unique(snapshots.map(p => p.grade)), classes = unique(snapshots.map(groupKey)), filterClasses = classes.filter(value => !filters.grade || value.startsWith(filters.grade + ' / '))
  const subjectCatalog = Object.fromEntries(exam.subjects.map(s => [s.subject_id!, s.name]))
  const ready = Object.keys(exam.score_files)
  const matchesFilters = (teacher: Row, values: typeof filters) => {
    if (!`${teacher.name} ${teacher.platform_id} ${teacher.account}`.toLowerCase().includes(values.search.trim().toLowerCase()) || (values.duty && !teacher.duties.includes(values.duty))) return false
    const [classGrade = '', classNumber = ''] = values.classroom.split(' / ')
    const number = classNumber.replace(/班$/, '').trim()
    return !(values.grade || values.classroom || values.subject) || teacher.filter_scopes.some((scope: Row) =>
      (!values.grade || scope.grade === gradeLabel(values.grade))
      && (!values.classroom || (scope.grade === gradeLabel(classGrade) && scope.class_number === (/^\d+$/.test(number) ? String(Number(number)) : number)))
      && (!values.subject || scope.subject === subjectCatalog[values.subject]))
  }
  const visible = teacherRows.filter(teacher => matchesFilters(teacher, filters))
  const teacher = visible.find(teacher => teacher.id === active), form = drafts[active]
  const changeFilters = (values: typeof filters) => {
    const visibleIds = new Set(teacherRows.filter(teacher => matchesFilters(teacher, values)).map(teacher => teacher.id))
    const remaining = selected.filter(id => visibleIds.has(id))
    setFilters(values); setSelected(remaining); setActive(remaining.includes(active) ? active : remaining[0] || ''); setNotice(''); job.setError(null)
  }
  const defaultForm = (teacher: Row) => teacher.recommendation
  const incomplete = selected.flatMap(id => {
    const draft = drafts[id]
    const missing = []
    if (!draft || !(draft.score_types.length || draft.diagnosis_types.length || draft.essay_types.length)) missing.push('未选择查询内容')
    if (draft && !!draft.score_types.length !== !!draft.score_subjects.length) missing.push('成绩类型与成绩科目需要同时选择')
    if (draft && !!draft.diagnosis_types.length !== !!draft.diagnosis_subjects.length) missing.push('诊断类型与诊断科目需要同时选择')
    if (!draft || (draft.range_type === 'grade' && !draft.grades.length) || (draft.range_type === 'class' && !draft.classes.length)) missing.push('未选择授权年级或班级')
    return missing.length ? [{ id, missing, teacher: teacherRows.find(teacher => teacher.id === id) }] : []
  })
  const validate = () => {
    if (!incomplete.length) return
    setActive(incomplete[0].id)
    const details = incomplete.slice(0, 5).map(item => `${item.teacher?.name || item.id}（${item.teacher?.platform_id || item.id}）：${item.missing.join('、')}`).join('；')
    throw new Error(`有 ${incomplete.length} 位教师的配置尚未完整：${details}${incomplete.length > 5 ? `；另有 ${incomplete.length - 5} 位待补全` : ''}。已定位首位教师，请补全后重试。`)
  }
  const pick = (t: Row, checked: boolean) => {
    setSelected(toggle(selected, t.id, checked)); setNotice(''); job.setError(null)
    if (checked) { setDrafts({ ...drafts, [t.id]: drafts[t.id] || exam.teacher_permissions[t.id] || defaultForm(t) }); setActive(t.id) }
    else if (active === t.id) setActive(selected.find(id => id !== t.id) || '')
  }
  const change = (values: Record<string, unknown>) => { setDrafts({ ...drafts, [active]: { ...form, ...values } }); setNotice(''); job.setError(null) }
  const body = () => ({ expected_revision: exam.revision, teachers: selected.map(id => Object.fromEntries(Object.entries(drafts[id]).filter(([key]) => key !== 'frozen_student_ids'))) })
  const batch = (mode: string) => {
    const next = { ...drafts }
    for (const id of selected) {
      const teacher = teacherRows.find(teacher => teacher.id === id)!, f = { ...next[id] }
      if (mode === 'content') for (const field of ['score_types', 'score_subjects', 'diagnosis_types', 'diagnosis_subjects', 'essay_types']) f[field] = [...form[field]]
      if (mode === 'current') for (const field of ['range_type', 'grades', 'classes']) f[field] = form[field]
      if (mode === 'all') Object.assign(f, { range_type: 'all', grades: [], classes: [] })
      if (mode === 'class') Object.assign(f, { range_type: 'class', grades: [], classes: teacher.scope_classes })
      if (mode === 'grade') Object.assign(f, { range_type: 'grade', classes: [], grades: teacher.scope_grades })
      next[id] = f
    }
    setDrafts(next); setNotice('已更新所选教师的待保存配置。'); job.setError(null)
  }
  const upload = (file: File) => job.run(async () => { const data = await examRequest<{ items: any[] }>(`/${exam.id}/permissions/teacher/upload`, await uploadBody(file)); const next = { ...drafts }; data.items.forEach(p => { next[p.teacher_id] = p }); setDrafts(next); setSelected(unique([...selected, ...data.items.map(p => p.teacher_id)])); setFilters({ search: '', grade: '', classroom: '', subject: '', duty: '' }); setActive(data.items[0].teacher_id); setNotice('授权信息已载入，教师筛选已重置，核对后可直接确认保存。') })
  return <QueryState query={teachers}><div ref={errorRef}><JobError job={job} /></div><div className="exam-filters exam-teacher-filters"><input aria-label="搜索授权教师" placeholder="搜索姓名 / 教师ID / 账号" value={filters.search} onChange={e => changeFilters({ ...filters, search: e.target.value })} /><select aria-label="授权教师年级筛选" value={filters.grade} onChange={e => changeFilters({ ...filters, grade: e.target.value, classroom: '' })}><option value="">全部年级</option>{grades.map(g => <option key={g} value={g}>{gradeLabel(g)}</option>)}</select><select aria-label="授权教师班级筛选" value={filters.classroom} onChange={e => changeFilters({ ...filters, classroom: e.target.value })}><option value="">全部班级</option>{filterClasses.map(c => <option key={c} value={c}>{classLabel(c)}</option>)}</select><select aria-label="授权教师学科筛选" value={filters.subject} onChange={e => changeFilters({ ...filters, subject: e.target.value })}><option value="">全部学科</option>{Object.entries(subjectCatalog).map(([id, name]) => <option key={id} value={id}>{name}</option>)}</select><select aria-label="授权教师职务筛选" value={filters.duty} onChange={e => changeFilters({ ...filters, duty: e.target.value })}><option value="">全部职务</option>{teachers.data?.default_rules.map(rule => <option key={rule.role} value={rule.role}>{rule.label}</option>)}</select><button onClick={() => { const next = { ...drafts }; visible.forEach(t => { next[t.id] ||= exam.teacher_permissions[t.id] || defaultForm(t) }); setDrafts(next); setSelected(unique([...selected, ...visible.map(t => t.id)])); setActive(active || visible[0]?.id || ''); setNotice('') }}>勾选筛选结果</button></div><div className="exam-permission-layout"><aside className="exam-teachers"><h3>教师列表</h3>
      {!visible.length && <p className="inline-empty">暂无匹配的有效教师。</p>}{visible.map(t => <div key={t.id} className={`exam-teacher-row ${active === t.id ? 'active' : ''}`}><input type="checkbox" aria-label={`选择教师 ${t.name} ${t.platform_id}`} checked={selected.includes(t.id)} onChange={e => pick(t, e.target.checked)} /><button className="exam-teacher-name" onClick={() => selected.includes(t.id) ? setActive(t.id) : pick(t, true)}><strong>{t.name}</strong><span>{t.platform_id} · {t.account}</span><span>{t.role_labels.join('、')}</span>{['任课年级班级', '班主任年级班级', '教研组长负责年级科目', '年级长负责年级'].filter(key => t.fields?.[key]).map(key => <span key={key}>{key}：{t.fields[key]}</span>)}<span>{exam.teacher_permissions[t.id] ? '已授权' : '未授权'}</span></button>{exam.teacher_permissions[t.id] && <button disabled={job.busy} onClick={() => job.run(async () => { await examRequest(`/${exam.id}/permissions/teacher/${t.id}/revoke`, { expected_revision: exam.revision }); await onChanged() })}>撤销</button>}</div>)}</aside>
      <div className="exam-permission-editor"><div className="exam-permission-heading"><div className="exam-tabs">{selected.map(id => <button key={id} className={active === id ? 'active' : ''} onClick={() => setActive(id)}>{teacherRows.find(teacher => teacher.id === id)?.name}</button>)}</div><button disabled={job.busy} onClick={() => job.run(() => examDownload('/teacher-default-rules', '教师默认选项规则.xlsx'))}>下载默认选项规则（Excel）</button></div>{!teacher || !form ? <p className="inline-empty">请选择需配置权限的教师。</p> : <><h3>当前编辑：{teacher.name}（{teacher.platform_id}）</h3>{teacher.default_warnings.map((warning: string) => <p key={warning} className="exam-warning">{warning}</p>)}<section className="exam-permission-section"><MixedCheck checked={!!form.score_types.length} onChange={checked => change({ score_types: checked ? (defaultForm(teacher).score_types.length ? defaultForm(teacher).score_types : ['student','classSubject']) : [], score_subjects: checked ? defaultForm(teacher).score_subjects : [] })}><strong>成绩数据</strong></MixedCheck>{!!form.score_types.length && <><Checks title="成绩类型" catalog={SCORE_TYPES} selected={form.score_types} onChange={score_types => change({ score_types, ...(!score_types.length ? { score_subjects: [] } : {}) })} /><Checks title="成绩科目" catalog={Object.fromEntries(Object.entries(subjectCatalog).map(([key, value]) => [key, value+(ready.includes(key) ? '' : '（未导入）')]))} selected={form.score_subjects} disabled={key => !ready.includes(key)} onChange={score_subjects => change({ score_subjects })} /></>}</section>
      <section className="exam-permission-section"><MixedCheck checked={!!form.diagnosis_types.length} onChange={checked => change({ diagnosis_types: checked ? (defaultForm(teacher).diagnosis_types.length ? defaultForm(teacher).diagnosis_types : ['student']) : [], diagnosis_subjects: checked ? defaultForm(teacher).diagnosis_subjects : [] })}><strong>诊断报告</strong></MixedCheck>{!!form.diagnosis_types.length && <><Checks title="报告类型" catalog={DIAG_TYPES} selected={form.diagnosis_types} onChange={diagnosis_types => change({ diagnosis_types, ...(!diagnosis_types.length ? { diagnosis_subjects: [] } : {}) })} /><Checks title="报告科目" catalog={subjectCatalog} selected={form.diagnosis_subjects} onChange={diagnosis_subjects => change({ diagnosis_subjects })} /></>}</section>
      <section className="exam-permission-section"><MixedCheck label="全选作文报告语种" checked={form.essay_types.length === 2} mixed={form.essay_types.length === 1} onChange={checked => change({ essay_types: checked ? Object.keys(ESSAY_TYPES) : [] })}><strong>作文批改报告</strong></MixedCheck><Checks title="语种 · 个人报告" catalog={ESSAY_TYPES} selected={form.essay_types} onChange={essay_types => change({ essay_types })} /></section><h3>学生范围（仅当前教师）</h3><div className="exam-option-grid">{[['all','全部参试学生'],['grade','按年级'],['class','按班级']].map(([value,label]) => <label key={value} className="exam-check"><input type="radio" name="teacher-range" checked={form.range_type === value} onChange={() => change({ range_type: value })} />{label}</label>)}</div>{form.range_type === 'grade' && <Checks title="授权年级" catalog={Object.fromEntries(grades.map(g => [g,gradeLabel(g)]))} selected={form.grades} onChange={grades => change({ grades })} />}{form.range_type === 'class' && <Checks title="授权班级" catalog={Object.fromEntries(classes.map(c => [c,classLabel(c)]))} selected={form.classes} onChange={classes => change({ classes })} />}
      {selected.length > 1 && <div className="exam-card"><h4>批量设置已选 {selected.length} 位教师</h4><div className="exam-actions">{[['class','各人任教班级'],['grade','各人负责年级'],['all','全部参试学生'],['current','应用当前学生范围'],['content','应用当前类型和科目']].map(([mode,label]) => <button key={mode} onClick={() => batch(mode)}>{label}</button>)}</div></div>}
      <div className="exam-footer">{!!incomplete.length && <span className="exam-validation-summary" role="status">已选 {selected.length} 位教师，{incomplete.length} 位待补全</span>}<button disabled={job.busy || !selected.length} onClick={() => job.run(async () => { validate(); await examDownload(`/${exam.id}/permissions/teacher/preview`, `教师授权预览_${exam.exam_id}.xlsx`, body()); setNotice('授权预览已下载，核对后可确认保存。') })}>下载授权预览（Excel）</button><label className="exam-file-button">上传授权信息<input aria-label="上传教师授权信息" type="file" accept=".xlsx,.xls" disabled={job.busy} onChange={e => { const file = e.target.files?.[0]; if (file) void upload(file); e.target.value = '' }} /></label><button className="primary-button" disabled={job.busy || !selected.length} onClick={() => job.run(async () => { validate(); await examRequest(`/${exam.id}/permissions/teacher`, body()); await onChanged() })}>确认保存生效</button></div>
      </>}{notice && <p className="exam-success" role="status">{notice}</p>}</div></div></QueryState>
}

function StudentPermissions({ exam, onChanged }: { exam: ExamData; onChanged: () => Promise<void> }) {
  const [selected, setSelected] = useState<string[]>([]), [subjects, setSubjects] = useState<string[]>([]), [mode, setMode] = useState('open'), [filters, setFilters] = useState({ grade: '', classroom: '' }), [notice, setNotice] = useState(''), job = useJob()
  const ids = unique(exam.subjects.flatMap(s => s.student_ids)), people = ids.map(id => exam.snapshots[id]), grades = unique(people.map(p => p.grade)), classes = unique(people.filter(p => !filters.grade || p.grade === filters.grade).map(groupKey))
  const visible = people.filter(p => (!filters.grade || p.grade === filters.grade) && (!filters.classroom || groupKey(p) === filters.classroom))
  const change = () => { setNotice('') }
  const body = () => ({ expected_revision: exam.revision, student_ids: selected, subject_ids: subjects, mode })
  const subjectName = (id: string) => exam.subjects.find(s => s.subject_id === id)?.name || '历史科目'
  const upload = (file: File) => job.run(async () => { const data = await examRequest<{ items: any[] }>(`/${exam.id}/permissions/student/upload`, await uploadBody(file)); const first = data.items[0]; if (data.items.some(item => item.mode !== first.mode || JSON.stringify([...item.subject_ids].sort()) !== JSON.stringify([...first.subject_ids].sort()))) throw new Error('同一批次须使用相同操作和操作科目，请分批上传。'); setSelected(data.items.map(item => item.student_id)); setMode(first.mode); setSubjects(first.subject_ids); change(); setNotice('学生授权信息已载入，核对后可直接确认保存。') })
  return <><JobError job={job} /><p className="exam-note">由运营管理员从本次参试名单选择学生，按科目开放或关闭本人的成绩及报告查询。学生不能修改此设置。</p><div className="exam-actions"><label className="exam-check"><input type="radio" name="student-mode" checked={mode === 'open'} onChange={() => { setMode('open'); setSubjects(subjects.filter(s => !!exam.score_files[s])); change() }} />开放查询</label><label className="exam-check"><input type="radio" name="student-mode" checked={mode === 'close'} onChange={() => { setMode('close'); change() }} />关闭查询</label></div><Checks title="操作科目" catalog={Object.fromEntries(exam.subjects.map(s => [s.subject_id!, s.name+(!exam.score_files[s.subject_id!] ? '（未导入）' : '')]))} selected={subjects} disabled={id => mode === 'open' && !exam.score_files[id]} onChange={ids => { setSubjects(ids); change() }} />
    <div className="exam-filters"><select aria-label="学生授权年级筛选" value={filters.grade} onChange={e => setFilters({ grade: e.target.value, classroom: '' })}><option value="">全部年级</option>{grades.map(g => <option key={g} value={g}>{gradeLabel(g)}</option>)}</select><select aria-label="学生授权班级筛选" value={filters.classroom} onChange={e => setFilters({ ...filters, classroom: e.target.value })}><option value="">全部班级</option>{classes.map(c => <option key={c} value={c}>{classLabel(c)}</option>)}</select></div><StudentPicker people={visible} selected={selected} onChange={ids => { setSelected(ids); change() }} />
    <h3>当前查询范围</h3><Table paginate headers={['学生ID', '姓名', '考试年级 / 班级', '已开放科目']}>{visible.map(p => <tr key={p.id}><td>{p.platform_id}</td><td>{p.name}</td><td>{classLabel(groupKey(p))}</td><td>{exam.student_permissions[p.id]?.subjects.map(subjectName).join('、') || '未授权'}</td></tr>)}</Table>
    {notice && <p className="exam-success" role="status">{notice}</p>}<div className="exam-footer"><button disabled={job.busy || !selected.length || !subjects.length} onClick={() => job.run(async () => { await examDownload(`/${exam.id}/permissions/student/preview`, `学生授权预览_${exam.exam_id}.xlsx`, body()); setNotice('授权预览已下载，可核对变更前后查询范围。') })}>下载授权预览（Excel）</button><label className="exam-file-button">上传授权信息<input aria-label="上传学生授权信息" type="file" accept=".xlsx,.xls" disabled={job.busy} onChange={e => { const file = e.target.files?.[0]; if (file) void upload(file); e.target.value = '' }} /></label><button className="primary-button" disabled={job.busy || !selected.length || !subjects.length} onClick={() => job.run(async () => { await examRequest(`/${exam.id}/permissions/student`, body()); await onChanged() })}>确认保存生效</button></div>
  </>
}

function ExamLogs() {
  const [category, setCategory] = useState('exam'), pagination = usePagination(category)
  const logs = useJsonQuery<{ items: Row[]; total: number }>(`${EXAM_ROOT}/operations?category=${category}&page=${pagination.page}&page_size=${pagination.pageSize}`)
  const kinds: Record<string, string> = { create: '创建考试', adjust: '调整科目与范围', score_import: '导入成绩', score_delete: '删除成绩文件', teacher_permission: '教师查询权限更新', student_permission: '学生查询权限更新', teacher_revoke: '撤销教师查询权限' }
  return <><div className="exam-tabs"><button className={category === 'exam' ? 'active' : ''} onClick={() => setCategory('exam')}>考试操作</button><button className={category === 'permission' ? 'active' : ''} onClick={() => setCategory('permission')}>成绩开放设置</button></div><QueryState query={logs}>{!logs.data?.items.length && <p className="inline-empty">暂无操作记录。</p>}{logs.data?.items.map(log => <article className="exam-card" key={log.id}><h3>{kinds[log.kind] || log.kind}</h3><p>{log.exam_name} <span className="exam-code">{log.exam_code}</span></p><p className="exam-muted">{log.operator_name} · {dateLabel(log.created_at)}</p><details><summary>查看操作明细</summary>{log.details.preview_rows ? <Table headers={log.kind === 'teacher_permission' ? ['考试ID','教师ID','姓名','成绩类型','成绩科目','诊断类型','诊断科目','作文报告','学生范围'] : ['考试ID','学生ID','姓名','年级','班级','操作','操作科目','变更前','变更后']}>{log.details.preview_rows.map((row: any[], i: number) => <tr key={i}>{row.map((value, j) => <td key={j}>{String(value)}</td>)}</tr>)}</Table> : log.kind === 'create' || log.kind === 'adjust' ? <>{['before','after'].map(which => log.details[which] && <div key={which}><h4>{which === 'before' ? '调整前' : '保存后'}</h4><Table headers={['科目', '满分', '参试人数']}>{log.details[which].subjects.map((s: ExamSubject) => <tr key={s.key}><td>{s.name}</td><td>{s.full_score}</td><td>{s.student_ids.length}</td></tr>)}</Table><Table paginate headers={['学生ID','姓名','考试学年','年级 / 班级']}>{Object.values(log.details[which].snapshots as Record<string,Person>).map(p => <tr key={p.id}><td>{p.platform_id}</td><td>{p.name}</td><td>{log.details[which].academic_year}</td><td>{classLabel(groupKey(p))}</td></tr>)}</Table></div>)}</> : <p>{[log.details.subject_name, log.details.filename || log.details.files?.join('、'), log.details.teacher_name && `教师 ${log.details.teacher_name}（${log.details.teacher_platform_id}）查询权限已撤销`].filter(Boolean).join(' · ') || '权限已撤销，历史操作记录保留。'}{log.details.students && ` · ${log.details.students.length} 人`}</p>}</details></article>)}</QueryState>{logs.data && <Pager {...pagination} total={logs.data.total} />}</>
}
