import { Link, useParams } from 'react-router-dom'
import { AppShell, useCurrentRole } from '../layouts/AppShell'
import { ErrorDisplay } from '../components/ErrorDisplay'
import { useJsonQuery } from '../hooks/useApi'
import './ManagementPages.css'

type StudentDetail = {
  student: { name: string; student_no: string | null }; scope: string;
  subject_scores: Array<{ exam: string; subject: string; score: number; full_score: number; date: string | null }>;
  question_losses: Array<{ exam: string; subject: string; question_no: string; lost_score: number }>;
}

export function StudentDetailPage() {
  const { studentId } = useParams()
  const role = useCurrentRole()
  const query = useJsonQuery<StudentDetail>(`/platform/management/students/${studentId}`)
  const data = query.data
  return <AppShell title="学生学情详情"><Link to={role === 'teacher' ? '/teacher/students' : '/admin/students'}>← 返回学生列表</Link>
    {query.isLoading ? <div className="loading-state">正在读取授权范围内学情…</div> : query.error ? <ErrorDisplay error={query.error} onRetry={() => { void query.refetch() }} /> : data && <>
      <section className="panel"><h2>{data.student.name}</h2><p>{data.scope === 'teaching_subjects' ? '仅展示当前有效任教班级与学科；总分及其他学科不开放。' : '当前学校授权范围内的数据。'} 本次查看已记录审计。</p><p>学号：{data.student.student_no || '未填写'}</p></section>
      <section className="panel"><h2>学科成绩</h2>{data.subject_scores.length ? <div className="data-table-wrap"><table className="data-table"><thead><tr><th>考试</th><th>学科</th><th>得分 / 满分</th><th>日期</th></tr></thead><tbody>{data.subject_scores.map((row, i) => <tr key={i}><td>{row.exam}</td><td>{row.subject}</td><td>{row.score} / {row.full_score}</td><td>{row.date || '—'}</td></tr>)}</tbody></table></div> : <p className="inline-empty">当前授权范围内暂无学科成绩。</p>}</section>
      <section className="panel"><h2>小题丢分事实</h2><p>得分记录不代表对学生能力或失分原因的诊断。</p>{data.question_losses.length ? <ul>{data.question_losses.map((row, i) => <li key={i}>{row.exam} · {row.subject} 第 {row.question_no} 题：丢分 {row.lost_score}</li>)}</ul> : <p className="inline-empty">暂无可展示的小题丢分记录。</p>}</section>
    </>}
  </AppShell>
}

type SchoolDetail = { name: string; code: string; status: string; students: number; open_risks: number; open_feedback: number; open_handoffs: number; activity_note: string }

export function SchoolDetailPage() {
  const { schoolId } = useParams()
  const query = useJsonQuery<SchoolDetail>(`/platform/management/schools/${schoolId}`)
  const data = query.data
  return <AppShell title="学校运营详情" eyebrow="市级运营中心 / 学校运营"><Link to="/ops/schools">← 返回学校列表</Link>
    {query.isLoading ? <div className="loading-state">正在读取学校运营汇总…</div> : query.error ? <ErrorDisplay error={query.error} onRetry={() => { void query.refetch() }} /> : data && <section className="panel"><h2>{data.name}</h2><p>{data.code} · {data.status === 'active' ? '接入正常' : data.status}</p><dl><dt>在籍学生</dt><dd>{data.students}</dd><dt>待处理风险</dt><dd>{data.open_risks}</dd><dt>待处理反馈</dt><dd>{data.open_feedback}</dd><dt>待跟进工单</dt><dd>{data.open_handoffs}</dd></dl><p>{data.activity_note}</p><p>此处仅展示该学校的实时汇总，不包含学生个人信息。</p></section>}
  </AppShell>
}
