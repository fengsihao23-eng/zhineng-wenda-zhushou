import { apiFetch, apiError } from '../../services/api'

export const REPORT_ROOT = '/platform/education/report-management'
export const REPORT_TYPES: Record<string, string> = { student: '个人学情诊断', classAll: '班级综合诊断', classSubject: '班级单科诊断', gradeAll: '年级综合诊断', gradeSubject: '年级单科诊断', school: '全校学情诊断', essay: '个人作文批改报告' }
export const REPORT_KINDS: Record<string, string> = { student: 'student', essay: 'student', classAll: 'class', classSubject: 'class', gradeAll: 'grade', gradeSubject: 'grade', school: 'school' }
export type ReportCategory = 'diagnostic' | 'essay'
export type Classification = { category: ReportCategory; report_type: string; subject_ids: string[] }
export type ReportPerson = { id: string; platform_id: string; name: string; account: string; grade: string; class_number: string }
export type ReportExam = { id: string; exam_code: string; name: string; date?: string; academic_year: string; subject_names: string[]; grades: string[]; classes: string[] }
export type ExamScope = ReportExam & { school: string; revision: number; exam_date: string; subjects: Array<{ subject_id: string; name: string; student_ids: string[] }>; snapshots: Record<string, ReportPerson>; teachers: Array<{ id: string; platform_id: string; name: string; account: string; login_allowed: boolean }> }
export type PdfUpload = { filename: string; content_base64: string }
export type ReportFile = { id: string; version: number; filename: string; file_size: number; page_count: number; content_hash: string; reason: string; operator_name: string; created_at: string }
export type ReportRecord = Classification & { id: string; exam_id: string; exam_code: string; exam_name: string; report_code: string; target_key: string; type_name: string; category_name: string; subject_names: string[]; target_label: string; grades: string[]; classes: string[]; file: ReportFile; version: number; operator_name: string; created_at: string; updated_at: string; versions?: ReportFile[]; previous_file?: ReportFile }
export type PickerItem = { value: string; label: string; detail?: string; search?: string }
export type UploadRow = Classification & { token: string; target_key: string; file: PdfUpload; blob: File; naming: Classification; nameErrors: string[]; pdfError: string; page_count: number; file_size: number; previewed: boolean; modified: boolean }

export async function reportRequest<T>(path: string, body?: unknown, method = 'POST', key?: string): Promise<T> {
  const response = await apiFetch(REPORT_ROOT + path, { method, body: body === undefined ? undefined : JSON.stringify(body), headers: key ? { 'Idempotency-Key': key } : undefined })
  if (!response.ok) throw await apiError(response, '报告操作未完成，请重试')
  return response.json() as Promise<T>
}

export async function reportBlob(path: string, body?: unknown, signal?: AbortSignal): Promise<Blob> {
  const response = await apiFetch(path, { method: body ? 'POST' : 'GET', body: body ? JSON.stringify(body) : undefined, signal })
  if (!response.ok) throw await apiError(response, '报告文件读取失败')
  return response.blob()
}

export function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob), a = document.createElement('a')
  a.href = url; a.download = filename; document.body.append(a); a.click(); a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1500)
}

export const reportDate = (value: string) => new Date(value).toLocaleString('sv-SE', { timeZone: 'Asia/Shanghai', hour12: false })
export const fileSize = (n: number) => n > 1024 * 1024 ? (n / 1024 / 1024).toFixed(1) + ' MB' : Math.max(1, Math.round(n / 1024)) + ' KB'
export const reportClass = (person: ReportPerson) => person.grade + '|' + person.class_number
export const categoryName = (value: string) => value === 'essay' ? '作文批改报告' : '诊断报告'
export const subjectLabel = (scope: ExamScope, row: Classification) => row.subject_ids.map(id => scope.subjects.find(s => s.subject_id === id)?.name || id).join('、')
export const availableSubjects = (scope: ExamScope, row: Classification) => scope.subjects.filter(s => s.student_ids.length && (row.category !== 'essay' || ['语文', '英语'].includes(s.name)))

export function targetsFor(scope: ExamScope, row: Classification): PickerItem[] {
  const rosters = row.subject_ids.map(id => scope.subjects.find(s => s.subject_id === id)?.student_ids || [])
  if (!rosters.length || rosters.some(ids => !ids.length)) return []
  const union = [...new Set(rosters.flat())].filter(id => scope.snapshots[id]), kind = REPORT_KINDS[row.report_type]
  if (kind === 'student') return union.filter(id => rosters.every(ids => ids.includes(id))).map(id => {
    const p = scope.snapshots[id]
    return { value: id, label: `${p.name} · ${p.grade} ${p.class_number} · ${p.platform_id}`, detail: `账号 ${p.account}`, search: p.account }
  })
  if (kind === 'school') return [{ value: 'school', label: scope.school + ' · 本次考试参试范围' }]
  const group = (id: string) => kind === 'class' ? reportClass(scope.snapshots[id]) : scope.snapshots[id].grade
  return [...new Set(union.map(group))].filter(key => rosters.every(ids => ids.some(id => group(id) === key)))
    .sort().map(value => ({ value, label: value.replace('|', ' '), detail: '本次考试参试范围' }))
}

export function targetLabel(scope: ExamScope, row: Classification & { target_key: string }) {
  const p = scope.snapshots[row.target_key]
  return REPORT_KINDS[row.report_type] === 'student' ? (p ? `${p.name}（${p.platform_id}）` : '未选择学生') : row.target_key === 'school' ? scope.school + ' · 本次考试参试范围' : row.target_key.replace('|', ' ') || '未选择对象'
}

export function filenamePattern(row: Classification) {
  const kind = REPORT_KINDS[row.report_type]
  return ['考试ID', ...(kind === 'student' ? ['学生ID或账号', '姓名'] : kind === 'class' ? ['年级', '班级'] : kind === 'grade' ? ['年级'] : ['本校']), '科目', '报告类型'].join('_') + '.pdf'
}

export function filenameFor(scope: ExamScope, row: Classification, target: string) {
  const kind = REPORT_KINDS[row.report_type], person = scope.snapshots[target]
  const identity = kind === 'student' ? [person.platform_id, person.name] : kind === 'class' ? target.split('|') : [kind === 'school' ? '本校' : target]
  return [scope.exam_code, ...identity, row.subject_ids.map(id => scope.subjects.find(s => s.subject_id === id)?.name).join('+'), REPORT_TYPES[row.report_type]].join('_') + '.pdf'
}

export function parseReportFilename(filename: string, scope: ExamScope, row: Classification): { target: string; errors: string[] } {
  const errors: string[] = [], kind = REPORT_KINDS[row.report_type]
  if (row.subject_ids.length !== 1) return { target: '', errors: ['每批只能上传一个科目'] }
  if (!/\.pdf$/i.test(filename)) return { target: '', errors: ['文件扩展名必须为 .pdf'] }
  const parts = filename.slice(0, -4).split('_'), candidates = targetsFor(scope, row)
  if (parts.length !== (['student', 'class'].includes(kind) ? 5 : 4) || parts.some(p => !p || p !== p.trim())) return { target: '', errors: ['命名格式不规范；字段之间用半角下划线 _ 分隔，请下载本次范围命名清单'] }
  if (parts[0] !== scope.exam_code) errors.push('文件名中的考试ID与所选考试不一致')
  if (parts.at(-1) !== REPORT_TYPES[row.report_type]) errors.push('文件名中的报告类型与所选类型不一致')
  const names = parts.at(-2)!.split('+'), expected = row.subject_ids.map(id => scope.subjects.find(s => s.subject_id === id)?.name)
  if (names.length !== expected.length || new Set(names).size !== names.length || names.some(n => !expected.includes(n))) errors.push('文件名中的科目与所选科目范围不一致')
  let target = ''
  if (kind === 'student') {
    const matches = candidates.filter(c => [scope.snapshots[c.value].platform_id, scope.snapshots[c.value].account].includes(parts[1]))
    if (matches.length !== 1) errors.push('学生ID或账号不在所选科目参试名单内或对应多人，请使用唯一学生ID')
    else { target = matches[0].value; if (scope.snapshots[target].name !== parts[2]) errors.push('学生姓名与ID／账号对应的参试学生不一致') }
  } else {
    target = kind === 'class' ? parts[1] + '|' + parts[2] : kind === 'school' ? 'school' : parts[1]
    if (kind === 'school' && parts[1] !== '本校') errors.push('全校报告的对象字段须填写“本校”')
    if (!candidates.some(c => c.value === target)) errors.push('文件名中的对象不在所选科目的参试范围内')
  }
  return { target: errors.length ? '' : target, errors }
}

export function fuzzyMatches(items: PickerItem[], query: string) {
  const terms = query.normalize('NFKC').trim().toLowerCase().split(/\s+/).filter(Boolean)
  return items.filter(item => { const hay = [item.label, item.detail, item.value, item.search].join(' ').normalize('NFKC').toLowerCase(); return terms.every(term => hay.includes(term)) })
}

export function readPdfFile(file: File): Promise<PdfUpload> {
  return new Promise((resolve, reject) => {
    if (!file.size || !file.name.toLowerCase().endsWith('.pdf')) { reject(new Error('请选择非空 PDF 文件')); return }
    if (file.size > 15 * 1024 * 1024) { reject(new Error('单份 PDF 不能超过 15 MB')); return }
    const reader = new FileReader()
    reader.onerror = () => reject(new Error('无法读取所选文件，请重新选择'))
    reader.onload = () => resolve({ filename: file.name, content_base64: String(reader.result).split(',')[1] })
    reader.readAsDataURL(file)
  })
}
