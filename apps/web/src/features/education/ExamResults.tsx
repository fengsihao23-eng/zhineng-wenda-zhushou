import { useState } from 'react'
import { AppShell } from '../../layouts/AppShell'
import { getUserInfo } from '../../utils/auth'
import { useJsonQuery } from '../../hooks/useApi'
import { QueryState, Table, type Row } from './shared'
import { EXAM_ROOT, examDownload } from './ExamWorkbench'
import { ErrorDisplay } from '../../components/ErrorDisplay'
import { ReportPdfViewer } from './ReportWorkbench'

const TYPES: Record<string, string> = { student: '个人单科成绩 / 诊断', classSubject: '班级单科成绩 / 诊断', gradeSubject: '年级单科成绩 / 诊断', classAll: '班级综合成绩 / 诊断', gradeAll: '年级综合成绩 / 诊断', school: '全校综合成绩 / 诊断' }

export function ExamResultsPage() {
  const teacher = getUserInfo()?.roles.includes('TEACHER')
  const exams = useJsonQuery<Row[]>(`${EXAM_ROOT}/my-exams`)
  const [selected, setSelected] = useState(''), [viewType, setViewType] = useState('student'), [error, setError] = useState<Error | null>(null), [busy, setBusy] = useState(false)
  const [pdf, setPdf] = useState<{ filename: string; pages: number; path: string } | null>(null)
  const current = exams.data?.find(e => e.id === selected) || exams.data?.[0]
  const allowed = current && teacher ? [...new Set([...(current.permissions.score_types || []), ...(current.permissions.diagnosis_types || [])])] as string[] : ['student']
  if (teacher && current?.permissions.essay_types?.length && !allowed.length) allowed.push('student')
  const type = allowed.includes(viewType) ? viewType : allowed[0] || 'student'
  const result = useJsonQuery<{ scores: Row[]; totals: Row[]; reports: Row[] }>(`${EXAM_ROOT}/my-exams/${current?.id}?view_type=${type}`, !!current)
  const composite = ['classAll', 'gradeAll', 'school'].includes(type)
  const download = async (report: Row) => {
    setError(null); setBusy(true)
    try { await examDownload(`/my-exams/${current!.id}/reports/${report.id}/original?view_type=${type}`, report.filename || `${report.report_type}_${report.version || '报告'}.pdf`) } catch (e) { setError(e as Error) } finally { setBusy(false) }
  }
  return <AppShell title="考试成绩与报告" eyebrow={teacher ? '教师工作台 / 已授权考试' : '学生空间 / 已开放考试'}><section className="exam-workbench"><p className="exam-note">{teacher ? '按运营管理员为本次考试保存的查询内容、科目及学生范围展示。' : '展示运营管理员已向你开放的本人成绩、小题得分与报告。'}</p><QueryState query={exams}>
    {!exams.data?.length ? <p className="inline-empty">暂无已开放的考试，请等待运营管理员完成查询授权。</p> : <><div className="exam-filters"><select aria-label="选择已授权考试" value={current?.id || ''} onChange={e => setSelected(e.target.value)}>{exams.data?.map(exam => <option key={exam.id} value={exam.id}>{exam.name} · {exam.exam_id}</option>)}</select>{teacher && <select aria-label="查询内容类型" value={type} onChange={e => setViewType(e.target.value)}>{allowed.map(key => <option key={key} value={key}>{TYPES[key]}</option>)}</select>}<button onClick={() => { void exams.refetch(); void result.refetch() }}>刷新查询范围</button></div><QueryState query={result}>
      <h2>{composite ? '综合成绩' : '单科成绩'}</h2>{composite ? <Table paginate headers={['学生ID', '姓名', '考试年级 / 班级', '总分 / 满分', '班级名次', '年级名次']}>{result.data?.totals.map(row => <tr key={row.student_id}><td>{row.student_id}</td><td>{row.student_name}</td><td>{row.grade} / {row.class_number}</td><td>{row.total_score} / {row.full_score}</td><td>{row.class_rank ?? '—'}</td><td>{row.grade_rank ?? '—'}</td></tr>)}</Table> : <Table paginate headers={[...(teacher ? ['学生ID', '姓名', '考试年级 / 班级'] : []), '科目', '得分 / 满分', '班级名次', '年级名次', '小题得分']}>{result.data?.scores.map((row, index) => <tr key={index}>{teacher && <><td>{row.student_id}</td><td>{row.student_name}</td><td>{row.grade} / {row.class_number}</td></>}<td>{row.subject}</td><td>{row.score} / {row.full_score}</td><td>{row.class_rank ?? '—'}</td><td>{row.grade_rank ?? '—'}</td><td>{row.questions?.length ? <details><summary>查看 {row.questions.length} 题</summary>{row.questions.map((q: Row) => <p key={q.question_no}>第 {q.question_no} 题：{q.score} 分</p>)}</details> : '未导入小题明细'}</td></tr>)}</Table>}
      {!(composite ? result.data?.totals.length : result.data?.scores.length) && <p className="inline-empty">该查询类型下暂无已授权的完整成绩。</p>}{!teacher && !!result.data?.totals.length && <p className="exam-success">本人本次考试总分：{result.data.totals[0].total_score} / {result.data.totals[0].full_score} · 班级名次 {result.data.totals[0].class_rank ?? '—'} · 年级名次 {result.data.totals[0].grade_rank ?? '—'}</p>}<h2>报告原件</h2><ErrorDisplay error={error} variant="banner" onDismiss={() => setError(null)} />{!result.data?.reports.length ? <p className="inline-empty">暂无已上传且在查询授权范围内的报告。</p> : <Table headers={['报告类型 / 对象', '科目', '版本', '上传时间', '原件']}>{result.data.reports.map(report => <tr key={report.id}><td>{report.type_name || (report.report_type === 'marked_work' ? '作文批改报告' : '诊断报告')}{report.target_label && <div className="exam-muted">{report.target_label}</div>}</td><td>{report.subject_names?.join('、') || '—'}</td><td>{report.version ? `v${report.version}` : '—'}</td><td>{new Date(report.generated_at).toLocaleDateString('zh-CN')}</td><td><div className="exam-actions">{report.managed && <button onClick={() => setPdf({ filename: report.filename, pages: report.page_count, path: `${EXAM_ROOT}/my-exams/${current!.id}/reports/${report.id}/original?view_type=${type}` })}>查看 PDF</button>}<button disabled={busy} onClick={() => void download(report)}>下载 PDF 原件</button></div></td></tr>)}</Table>}
    </QueryState></>}
  </QueryState>{pdf && <div className="report-workbench"><ReportPdfViewer source={pdf} close={() => setPdf(null)} /></div>}</section></AppShell>
}
