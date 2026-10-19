import { useEffect, useId, useRef, useState, type ReactNode } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { AppShell } from '../../layouts/AppShell'
import { useJsonQuery } from '../../hooks/useApi'
import { randomKey } from '../../utils/id'
import { ApiError } from '../../services/http'
import { canWrite } from './shared'
import {
  REPORT_ROOT, REPORT_TYPES, REPORT_KINDS, reportRequest, reportBlob, downloadBlob, reportDate, fileSize, reportClass,
  categoryName, subjectLabel, availableSubjects, targetsFor, targetLabel, filenamePattern, filenameFor, parseReportFilename,
  fuzzyMatches, readPdfFile, type Classification, type ReportCategory, type ReportRecord, type ReportFile, type ReportExam,
  type ExamScope, type PickerItem, type PdfUpload, type UploadRow,
} from './report-management'
import './report-workbench.css'

type ListData = { items: ReportRecord[]; total: number; counts: Record<string, number>; facets: { subjects: string[]; grades: string[]; classes: string[] } }
type Options = { school: string; exams: ReportExam[] }
type Operation = { id: string; action: string; operator_name: string; created_at: string; reason: string; details: ReportRecord[] }
type PdfSource = { filename: string; pages: number; upload?: PdfUpload; path?: string }
type Modal = { kind: 'upload' } | { kind: 'detail' | 'replace'; report: ReportRecord } | { kind: 'delete'; reports: ReportRecord[] } | { kind: 'access' }
const emptyFilters = { search: '', exam_id: '', report_type: '', subject: '', grade: '', cls: '' }
const initialClassification = (): Classification => ({ category: 'diagnostic', report_type: 'student', subject_ids: [] })
const errorText = (error: unknown) => error instanceof Error ? error.message : '操作未完成，请重试'
const mutationError = (error: unknown, fallback: string) => error instanceof ApiError && (error.code === 'NETWORK_ERROR' || !error.status || error.status >= 500)
  ? '提交结果尚未确认，请重试同一提交以核对结果，不会重复办理。' + errorText(error) : fallback + errorText(error)
const fileSource = (report: ReportRecord, file = report.file): PdfSource => ({ filename: file.filename, pages: file.page_count, path: `${REPORT_ROOT}/${report.id}/file?version=${file.version}` })
const pagePath = (path: string, page: number) => path + (path.includes('?') ? '&' : '?') + 'page=' + page

let overlayCount = 0, previousOverflow = ''
function useOverlayLock() {
  useEffect(() => {
    if (overlayCount++ === 0) { previousOverflow = document.body.style.overflow; document.body.style.overflow = 'hidden' }
    return () => { if (--overlayCount === 0) document.body.style.overflow = previousOverflow }
  }, [])
}

function useDialogKeys(ref: React.RefObject<HTMLElement>, close: () => void, enabled = true, preview = false) {
  const closeRef = useRef(close); closeRef.current = close
  useEffect(() => {
    if (!enabled) return
    const previous = document.activeElement as HTMLElement | null
    const focusable = () => [...(ref.current?.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled):not([type=hidden]), select:not(:disabled), textarea:not(:disabled), a[href], [tabindex="0"]') || [])].filter(el => el.getClientRects().length > 0)
    focusable()[0]?.focus()
    const handler = (event: KeyboardEvent) => {
      if (!preview && document.querySelector('.report-workbench .preview-cover')) return
      if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); closeRef.current() }
      if (event.key === 'Tab') {
        const items = focusable(), first = items[0], last = items[items.length - 1]
        if (event.shiftKey && (document.activeElement === first || !ref.current?.contains(document.activeElement))) { event.preventDefault(); last?.focus() }
        else if (!event.shiftKey && (document.activeElement === last || !ref.current?.contains(document.activeElement))) { event.preventDefault(); first?.focus() }
      }
    }
    document.addEventListener('keydown', handler)
    return () => { document.removeEventListener('keydown', handler); if (previous?.isConnected) previous.focus() }
  }, [ref, enabled, preview])
}

function Notice({ children, kind = 'error' }: { children?: ReactNode; kind?: 'error' | 'success' | 'warn' }) {
  return children ? <div className={`notice ${kind}`} role={kind === 'error' ? 'alert' : 'status'}>{children}</div> : null
}

function QueryFeedback({ query }: { query: { isLoading: boolean; error: Error | null; refetch: () => unknown } }) {
  return query.isLoading ? <p className="empty" role="status">正在读取…</p> : query.error ? <Notice>{query.error.message} <button className="btn small" onClick={() => void query.refetch()}>重试</button></Notice> : null
}

function Drawer({ title, wide = false, busy = false, close, children, footer }: { title: string; wide?: boolean; busy?: boolean; close: () => void; children: ReactNode; footer: ReactNode }) {
  const ref = useRef<HTMLElement>(null)
  useOverlayLock()
  useDialogKeys(ref, () => { if (!busy) close() })
  return <><div className="backdrop" onClick={() => { if (!busy) close() }} /><section ref={ref} className={`drawer ${wide ? '' : 'narrow'}`} role="dialog" aria-modal="true" aria-label={title}>
    <div className="drawer-head"><h2>{title}</h2><button className="close" aria-label="关闭抽屉" disabled={busy} onClick={close}>×</button></div>
    <div className="drawer-body">{children}</div><div className="drawer-foot">{footer}</div>
  </section></>
}

export function ReportPdfViewer({ source, close, onRendered }: { source: PdfSource; close: () => void; onRendered?: () => void }) {
  const [page, setPage] = useState(1), [url, setUrl] = useState(''), [error, setError] = useState(''), [loading, setLoading] = useState(true), [downloading, setDownloading] = useState(false), [retry, setRetry] = useState(0)
  const ref = useRef<HTMLElement>(null), renderedRef = useRef(onRendered); renderedRef.current = onRendered
  useOverlayLock()
  useDialogKeys(ref, close, true, true)
  useEffect(() => {
    const controller = new AbortController(); let objectUrl = ''
    setLoading(true); setError(''); setUrl('')
    const path = source.upload ? `${REPORT_ROOT}/pdf-preview?page=${page}` : pagePath(source.path!, page)
    void reportBlob(path, source.upload, controller.signal).then(blob => {
      if (controller.signal.aborted) return
      objectUrl = URL.createObjectURL(blob); setUrl(objectUrl)
    }).catch(e => { if (!controller.signal.aborted) { setError(errorText(e)); setLoading(false) } })
    return () => { controller.abort(); if (objectUrl) URL.revokeObjectURL(objectUrl) }
  }, [source, page, retry])
  const download = async () => {
    setDownloading(true); setError('')
    try { const blob = source.upload ? new Blob([Uint8Array.from(atob(source.upload.content_base64), c => c.charCodeAt(0))], { type: 'application/pdf' }) : await reportBlob(source.path!); downloadBlob(blob, source.filename) }
    catch (e) { setError(errorText(e)) } finally { setDownloading(false) }
  }
  return <div className="preview-cover"><section ref={ref} className="preview" role="dialog" aria-modal="true" aria-label="PDF预览">
    <div className="drawer-head"><h2>{source.filename}</h2><div className="actions"><button className="btn small" disabled={downloading} onClick={() => void download()}>{downloading ? '下载中…' : '下载 PDF'}</button><button className="close" aria-label="关闭PDF预览" onClick={close}>×</button></div></div>
    <div className="pdf-controls"><button className="btn small" disabled={page === 1 || loading} onClick={() => setPage(page - 1)}>上一页</button><span>第 {page} / {source.pages} 页</span><button className="btn small" disabled={page >= source.pages || loading} onClick={() => setPage(page + 1)}>下一页</button></div>
    <Notice>{error && <>{error} <button className="btn small" onClick={() => setRetry(retry + 1)}>重试预览</button></>}</Notice>
    <div className="pdf-reader">{loading && <div className="pdf-loading" role="status">正在渲染 PDF…</div>}{url && <img src={url} alt={`PDF第${page}页`} style={loading ? { display: 'none' } : undefined} onLoad={() => { setLoading(false); renderedRef.current?.() }} onError={() => { setLoading(false); setError('此页无法显示，请重试预览') }} />}</div>
    <div className="preview-note">请核对报告实际内容、考试、科目及对象。</div>
  </section></div>
}

function SearchPicker({ label, placeholder, hint, items, value, change, disabled = false }: { label: string; placeholder: string; hint: string; items: PickerItem[]; value: string; change: (value: string) => void; disabled?: boolean }) {
  const id = useId(), [open, setOpen] = useState(false), [query, setQuery] = useState(''), [index, setIndex] = useState(0)
  const matches = fuzzyMatches(items, query), current = items.find(item => item.value === value)
  const choose = (next: string) => { setOpen(false); setQuery(''); setIndex(0); change(next) }
  return <div className="search-picker"><div className="picker-input"><input id={id} className="control" role="combobox" aria-label={label} aria-autocomplete="list" aria-expanded={open} aria-controls={id + '-results'} aria-activedescendant={open && matches[index] ? id + '-option-' + index : undefined} autoComplete="off" placeholder={placeholder} value={open ? query : ''} disabled={disabled}
    onFocus={() => { setOpen(true); setQuery(''); setIndex(0) }} onBlur={() => { setOpen(false); setQuery('') }} onChange={e => { setQuery(e.target.value); setOpen(true); setIndex(0) }} onKeyDown={e => {
      if (e.key === 'Escape' && open) { e.preventDefault(); e.stopPropagation(); setOpen(false); return }
      if (!['ArrowDown', 'ArrowUp', 'Enter'].includes(e.key)) return
      e.preventDefault()
      if (!open) { setOpen(true); return }
      if (!matches.length) return
      if (e.key === 'Enter') choose(matches[index % matches.length].value)
      else { const next = (index + (e.key === 'ArrowDown' ? 1 : -1) + matches.length) % matches.length; setIndex(next); document.getElementById(id + '-option-' + next)?.scrollIntoView({ block: 'nearest' }) }
    }} /><span aria-hidden="true">⌕</span></div>
    {open && <div className="picker-results" id={id + '-results'} role="listbox" aria-label={label + '匹配结果'}><div className="picker-count" role="status">{matches.length ? `匹配 ${matches.length} 项，点击选择` : '未找到匹配项，请更换关键词'}</div>{matches.map((item, i) => <button type="button" role="option" id={id + '-option-' + i} key={item.value} aria-selected={item.value === value} className={`picker-option ${i === index ? 'highlighted' : ''}`} onMouseDown={e => e.preventDefault()} onClick={() => choose(item.value)}><b>{item.label}</b><span>{item.detail}</span></button>)}</div>}
    <div className="picker-current">已选：<strong>{current ? current.label + (current.detail ? ' · ' + current.detail : '') : '尚未选择'}</strong></div><div className="muted picker-hint">{hint}</div>
  </div>
}

function Paging({ page, total, change }: { page: number; total: number; change: (page: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / 12))
  return <div className="paging"><span className="muted">共 {total} 份</span><div className="actions"><button className="btn small" disabled={page <= 1} onClick={() => change(page - 1)}>上一页</button><span className="muted">{page} / {pages}</span><button className="btn small" disabled={page >= pages} onClick={() => change(page + 1)}>下一页</button></div></div>
}

export function ReportWorkbenchPage({ view = 'list' }: { view?: 'list' | 'create' }) {
  const navigate = useNavigate(), cache = useQueryClient(), writable = canWrite()
  const [page, setPage] = useState(1), [category, setCategory] = useState(''), [filters, setFilters] = useState(emptyFilters), [tab, setTab] = useState('reports')
  const [selection, setSelection] = useState<Map<string, ReportRecord>>(new Map()), [modal, setModal] = useState<Modal | null>(view === 'create' && writable ? { kind: 'upload' } : null), [notice, setNotice] = useState('')
  const options = useJsonQuery<Options>(REPORT_ROOT + '/options')
  const params = new URLSearchParams({ ...Object.fromEntries(Object.entries(filters).filter(([, value]) => value)), category, page: String(page), page_size: '12' })
  const list = useJsonQuery<ListData>(`${REPORT_ROOT}?${params}`, tab === 'reports')
  const close = () => { setModal(null); if (view === 'create') navigate('/admin/reports', { replace: true }) }
  const changed = async (message: string) => { close(); setNotice(message); setSelection(new Map()); await cache.invalidateQueries({ predicate: query => query.queryKey.some(key => typeof key === 'string' && (key.includes('report-management') || key.includes('exam-management'))) }) }
  const filter = (key: keyof typeof filters, value: string) => { setFilters(previous => ({ ...previous, [key]: value, ...(key === 'exam_id' ? { grade: '', cls: '', subject: '' } : key === 'grade' ? { cls: '' } : {}) })); setPage(1) }
  const switchTab = (next: string) => { setTab(next); setPage(1); setSelection(new Map()); setNotice('') }
  const reset = () => { setFilters(emptyFilters); setPage(1) }
  const toggle = (report: ReportRecord, checked: boolean) => setSelection(previous => { const next = new Map(previous); if (checked) next.set(report.id, report); else next.delete(report.id); return next })
  const examFacets = options.data?.exams.filter(exam => !filters.exam_id || exam.id === filters.exam_id) || []
  const subjects = [...new Set([...(list.data?.facets.subjects || []), ...examFacets.flatMap(exam => exam.subject_names || [])])].sort()
  const grades = [...new Set([...(list.data?.facets.grades || []), ...examFacets.flatMap(exam => exam.grades || [])])].sort()
  const classes = [...new Set([...(list.data?.facets.classes || []), ...examFacets.flatMap(exam => exam.classes || [])])].filter(cls => !filters.grade || cls.startsWith(filters.grade + '|')).sort()
  return <AppShell eyebrow="业务生产 / 学校范围"><section className="report-workbench" aria-label="报告管理"><div className="shell">
    <div className="crumb">业务生产 / 学校范围</div><h1>报告管理</h1>
    <nav className="nav" aria-label="报告管理页面"><Link to="/admin/school?tab=exam-management">考务管理</Link><button className={tab === 'reports' ? 'active' : ''} onClick={() => switchTab('reports')}>报告维护</button><button className={tab === 'logs' ? 'active' : ''} onClick={() => switchTab('logs')}>操作记录</button></nav>
    <Notice kind="success">{notice}</Notice><div className="card">
      {tab === 'reports' ? <><div className="toolbar"><div className="actions"><h2>报告维护</h2><span className="stat-inline">共 {list.data?.counts.all || 0} 份报告</span></div><div className="actions"><button className="btn" onClick={() => setModal({ kind: 'access' })}>核对查询权限</button>{writable && <button className="btn primary" onClick={() => { setNotice(''); setModal({ kind: 'upload' }) }}>＋ 上传报告</button>}</div></div>
        <div className="segmented" role="tablist" aria-label="报告类别">{[['', '全部报告'], ['diagnostic', '诊断报告'], ['essay', '作文批改报告']].map(([key, label]) => <button key={key} role="tab" aria-selected={category === key} className={category === key ? 'on' : ''} onClick={() => { setCategory(key); filter('report_type', ''); setSelection(new Map()) }}>{label} <span className="muted">{list.data?.counts[key || 'all'] || 0}</span></button>)}</div>
        <div className="filters"><input className="control search" aria-label="搜索报告" placeholder="搜索报告ID / 对象 / 文件名" value={filters.search} onChange={e => filter('search', e.target.value)} /><select className="control" aria-label="考试筛选" value={filters.exam_id} onChange={e => filter('exam_id', e.target.value)}><option value="">全部考试</option>{options.data?.exams.map(exam => <option key={exam.id} value={exam.id}>{exam.name} · {exam.exam_code}</option>)}</select>
          <select className="control" aria-label="报告类型筛选" value={filters.report_type} onChange={e => filter('report_type', e.target.value)}><option value="">全部报告类型</option>{Object.entries(REPORT_TYPES).filter(([key]) => category === 'essay' ? key === 'essay' : category === 'diagnostic' ? key !== 'essay' : true).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select>
          {(['subject', 'grade', 'cls'] as const).map((key, i) => <select key={key} className="control" aria-label={['全部科目', '全部年级', '全部班级'][i]} value={filters[key]} onChange={e => filter(key, e.target.value)}><option value="">{['全部科目', '全部年级', '全部班级'][i]}</option>{[subjects, grades, classes][i].map(value => <option key={value} value={value}>{value.replace('|', ' ')}</option>)}</select>)}<button className="btn small" onClick={reset}>重置</button>
        </div><div className="selected-bar"><span className="muted">{selection.size ? `已选 ${selection.size} 份` : '可按报告对象、考试和科目筛选'}</span>{writable && <div className="actions">{!!selection.size && <button className="btn quiet" onClick={() => setSelection(new Map())}>清空选择</button>}<button className="btn small danger" disabled={!selection.size} onClick={() => setModal({ kind: 'delete', reports: [...selection.values()] })}>删除所选</button></div>}</div>
        <QueryFeedback query={list} /><QueryFeedback query={options} />{list.data && !list.error && <><div className="table-wrap"><table><thead><tr><th className="checkcol">{writable && <input type="checkbox" aria-label="选择当前页全部报告" checked={!!list.data.items.length && list.data.items.every(r => selection.has(r.id))} onChange={e => { const next = new Map(selection); list.data!.items.forEach(r => { if (e.target.checked) next.set(r.id, r); else next.delete(r.id) }); setSelection(next) }} />}</th>{['报告 / 类别', '所属考试', '科目', '报告对象', '当前文件', '更新时间', '操作'].map(label => <th key={label}>{label}</th>)}</tr></thead><tbody>
          {list.data.items.map(report => <tr key={report.id}><td className="checkcol">{writable && <input type="checkbox" aria-label={`选择 ${report.report_code}`} checked={selection.has(report.id)} onChange={e => toggle(report, e.target.checked)} />}</td><td className="wrap"><strong>{report.type_name}</strong><span className={`pill ${report.category === 'essay' ? 'green' : ''}`}>{report.category_name}</span><div className="sub">{report.report_code}</div></td><td className="wrap">{report.exam_name}<div className="sub">{report.exam_code}</div></td><td>{report.subject_names.join('、')}</td><td className="wrap">{report.target_label}</td><td className="wrap">{report.file.filename}<div className="sub">v{report.version} · {fileSize(report.file.file_size)}</div></td><td className="muted mono">{reportDate(report.updated_at)}</td><td><div className="actions"><button className="btn quiet" onClick={() => setModal({ kind: 'detail', report })}>查看</button>{writable && <><button className="btn quiet" onClick={() => setModal({ kind: 'replace', report })}>替换</button><button className="btn quiet" onClick={() => setModal({ kind: 'delete', reports: [report] })}>删除</button></>}</div></td></tr>)}
          {!list.data.items.length && <tr><td colSpan={8}><div className="empty">没有匹配的报告<br /><button className="btn quiet" onClick={reset}>清除筛选</button></div></td></tr>}
        </tbody></table></div><Paging page={page} total={list.data.total} change={setPage} /></>}
      </> : <ReportLogs back={() => switchTab('reports')} />}
    </div>
    {modal?.kind === 'upload' && <ReportUpload exams={options.data?.exams || []} initialExam={filters.exam_id} close={close} saved={changed} />}
    {modal?.kind === 'detail' && <ReportDetail report={modal.report} close={close} replace={() => setModal({ kind: 'replace', report: modal.report })} remove={() => setModal({ kind: 'delete', reports: [modal.report] })} writable={writable} />}
    {modal?.kind === 'replace' && <ReportReplace report={modal.report} close={close} saved={changed} />}
    {modal?.kind === 'delete' && <ReportDelete reports={modal.reports} close={close} saved={changed} />}
    {modal?.kind === 'access' && <ReportAccess exams={options.data?.exams || []} initialExam={filters.exam_id} close={close} />}
  </div></section></AppShell>
}

function ClassificationFields({ row, scope, change, disabled = false, batch = true }: { row: Classification; scope: ExamScope; change: (row: Classification) => void; disabled?: boolean; batch?: boolean }) {
  const id = useId()
  return <><div className="form-row"><label className="required" htmlFor={id + '-category'}>报告类别</label><select id={id + '-category'} className="control" aria-label={batch ? '本批报告类别' : '文件报告类别'} disabled={disabled} value={row.category} onChange={e => {
    const category = e.target.value as ReportCategory, next = { ...row, category, report_type: category === 'essay' ? 'essay' : 'student' }; next.subject_ids = next.subject_ids.filter(sub => availableSubjects(scope, next).some(s => s.subject_id === sub)); change(next)
  }}><option value="diagnostic">诊断报告</option><option value="essay">作文批改报告</option></select></div>
    <div className="form-row"><label className="required" htmlFor={id + '-type'}>报告类型</label>{row.category === 'essay' ? <div className="control" aria-readonly="true">个人作文批改报告</div> : <select id={id + '-type'} className="control" aria-label={batch ? '本批报告类型' : '文件报告类型'} disabled={disabled} value={row.report_type} onChange={e => change({ ...row, report_type: e.target.value })}>{Object.entries(REPORT_TYPES).filter(([key]) => key !== 'essay').map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select>}</div>
    <div className="form-row"><label className="required">上传科目</label><div>{batch ? <><div className="choices">{availableSubjects(scope, row).map(subject => <label key={subject.subject_id}><input type="radio" name={id + '-subject'} aria-label={subject.name} disabled={disabled} checked={row.subject_ids.includes(subject.subject_id)} onChange={() => change({ ...row, subject_ids: [subject.subject_id] })} />{subject.name}</label>)}{!availableSubjects(scope, row).length && <span className="muted">本次考试没有符合此报告类别的参试科目</span>}</div><div className="muted">单选，每批只上传一个科目的报告。</div></> : <><div className="control" aria-readonly="true">{subjectLabel(scope, row)}</div><div className="muted picker-hint">同批科目保持一致；如需更换，请返回第一步统一选择。</div></>}</div></div>
  </>
}

function ReportUpload({ exams, initialExam, close, saved }: { exams: ReportExam[]; initialExam: string; close: () => void; saved: (message: string) => Promise<void> }) {
  const [examId, setExamId] = useState(initialExam || exams[0]?.id || ''), [config, setConfig] = useState<Classification>(initialClassification), [rows, setRows] = useState<UploadRow[]>([]), [active, setActive] = useState(0), [step, setStep] = useState(1)
  const [error, setError] = useState(''), [reading, setReading] = useState(false), [busy, setBusy] = useState(false), [preview, setPreview] = useState<PdfSource | null>(null), [previewToken, setPreviewToken] = useState(''), [drag, setDrag] = useState(false)
  const [targetClass, setTargetClass] = useState(''), [editType, setEditType] = useState(false), [checksum, setChecksum] = useState('')
  const inputId = useId(), generation = useRef(0), saveKey = useRef(randomKey())
  const scopeQuery = useJsonQuery<ExamScope>(`${REPORT_ROOT}/exams/${examId}`, !!examId), scope = scopeQuery.data
  useEffect(() => () => { generation.current++ }, [])
  useEffect(() => { if (!examId && exams.length) setExamId(initialExam || exams[0].id) }, [examId, exams, initialExam])
  const invalidate = () => { setChecksum(''); saveKey.current = randomKey(); setError('') }
  const configure = (next: Classification) => {
    invalidate(); setConfig(next)
    if (scope) setRows(previous => previous.map(row => { const parsed = parseReportFilename(row.file.filename, scope, next); return { ...row, ...next, naming: { ...next, subject_ids: [...next.subject_ids] }, target_key: parsed.target, nameErrors: parsed.errors, modified: false, previewed: false } }))
  }
  const changeExam = (id: string) => { generation.current++; setExamId(id); setConfig(initialClassification()); setRows([]); setActive(0); setTargetClass(''); invalidate() }
  const ready = !!scope && config.subject_ids.length === 1 && targetsFor(scope, config).length > 0
  const rowErrors = (row: UploadRow) => [row.pdfError, ...row.nameErrors].filter(Boolean)
  const pass = rows.filter(row => !rowErrors(row).length).length
  const addFiles = async (files: FileList | File[]) => {
    if (!scope || !ready || reading || busy) return
    const selected = Array.from(files)
    if (!selected.length) return
    if (selected.length + rows.length > 30 || selected.reduce((n, file) => n + file.size, 0) + rows.reduce((n, row) => n + row.file_size, 0) > 30 * 1024 * 1024) { setError('每批最多 30 份文件，合计不能超过 30 MB，请分批上传'); return }
    invalidate(); setReading(true)
    const currentGeneration = generation.current, first = rows.length
    const added = selected.map(file => { const parsed = parseReportFilename(file.name, scope, config); return { token: randomKey(), ...config, subject_ids: [...config.subject_ids], target_key: parsed.target, file: { filename: file.name, content_base64: '' }, blob: file, naming: { ...config, subject_ids: [...config.subject_ids] }, nameErrors: parsed.errors, pdfError: '正在校验 PDF…', page_count: 0, file_size: file.size, previewed: false, modified: false } })
    setRows(previous => [...previous, ...added])
    const checked = await Promise.all(added.map(async row => {
      try { const file = await readPdfFile(row.blob), result = await reportRequest<{ page_count: number }>('/inspect-pdf', file); return { ...row, file, page_count: result.page_count, pdfError: '' } }
      catch (e) { return { ...row, pdfError: errorText(e) } }
    }))
    if (currentGeneration !== generation.current) return
    setRows(previous => previous.map(row => checked.find(item => item.token === row.token) || row)); setActive(first); setReading(false)
  }
  const payload = () => ({ exam_id: examId, expected_exam_revision: scope!.revision, reports: rows.map(row => ({ category: row.category, report_type: row.report_type, subject_ids: row.subject_ids, target_key: row.target_key, file: row.file, naming: row.naming, previewed: row.previewed })) })
  const next = async () => {
    setError('')
    if (step === 1) { if (pass === rows.length && rows.length && ready) { setStep(2); setTargetClass(''); setEditType(false) } return }
    const problem = rows.find(row => !targetsFor(scope!, row).some(target => target.value === row.target_key) || rowErrors(row).length || !row.previewed)
    if (problem) { setActive(rows.indexOf(problem)); setError(problem.file.filename + '：' + (!problem.previewed ? '请先预览 PDF 并核对实际内容与归属' : [...rowErrors(problem), '请核对有效的报告对象'].join('；'))); return }
    setBusy(true)
    try { const result = await reportRequest<{ preview_hash: string }>('/batches/preview', payload()); setChecksum(result.preview_hash); setStep(3) }
    catch (e) { setError(errorText(e)) } finally { setBusy(false) }
  }
  const save = async () => {
    if (busy || !checksum) return
    setBusy(true); setError('')
    try { await reportRequest('/batches', { ...payload(), preview_hash: checksum }, 'POST', saveKey.current); await saved(`已保存 ${rows.length} 份报告`) }
    catch (e) { setError(mutationError(e, '保存失败，整批未写入：')); setBusy(false) }
  }
  const updateRow = (next: Classification & { target_key?: string }) => {
    invalidate(); setRows(previous => previous.map((row, i) => {
      if (i !== active) return row
      const updated = { ...row, ...next, previewed: false, modified: true }
      if (REPORT_KINDS[updated.report_type] === 'school') updated.target_key = 'school'
      else if (!targetsFor(scope!, updated).some(target => target.value === updated.target_key)) updated.target_key = ''
      return updated
    })); setTargetClass('')
  }
  const downloadNames = async () => {
    setBusy(true); setError('')
    try { downloadBlob(await reportBlob(`${REPORT_ROOT}/exams/${examId}/naming-list`, config), `报告文件命名清单_${scope!.exam_code}.csv`) } catch (e) { setError(errorText(e)) } finally { setBusy(false) }
  }
  const row = rows[active], kind = row ? REPORT_KINDS[row.report_type] : '', candidates = scope && row ? targetsFor(scope, row) : []
  const classes = scope && row && kind === 'student' ? [...new Set(candidates.map(item => reportClass(scope.snapshots[item.value])))].sort() : []
  const targets = kind === 'student' && targetClass && scope ? candidates.filter(item => reportClass(scope.snapshots[item.value]) === targetClass) : candidates
  const selectedTarget = candidates.find(item => item.value === row?.target_key)
  const targetOptions = selectedTarget && !targets.some(item => item.value === selectedTarget.value) ? [selectedTarget, ...targets] : targets
  return <Drawer title="上传报告" wide busy={busy} close={close} footer={<><button className="btn" disabled={busy} onClick={close}>取消</button><div className="actions">{step === 1 && <><span className="muted">校验通过 {pass} / {rows.length} 份</span><button className="btn primary" disabled={!ready || !rows.length || reading || pass !== rows.length || busy} onClick={() => void next()}>下一步：预览归属</button></>}{step === 2 && <><button className="btn" disabled={busy} onClick={() => { setStep(1); invalidate() }}>上一步</button><button className="btn primary" disabled={busy} onClick={() => void next()}>{busy ? '校验中…' : '下一步：核对清单'}</button></>}{step === 3 && <><button className="btn" disabled={busy} onClick={() => { setStep(2); invalidate() }}>返回修改</button><button className="btn primary" disabled={busy} onClick={() => void save()}>{busy ? '保存中…' : '确认保存'}</button></>}</div></>}>
    <div className="steps">{['选择范围与校验文件', '预览并调整归属', '核对并保存'].map((label, i) => <div key={label} className={`step ${step === i + 1 ? 'active' : step > i + 1 ? 'done' : ''}`}>{i + 1}. {label}</div>)}</div>
    {step === 1 && <><div className="form-row"><label className="required">所属考试</label><SearchPicker label="上传所属考试" placeholder="输入考试名称 / ID关键词" hint="支持考试名称或ID关键词模糊搜索，点击匹配项选择。" items={exams.map(exam => ({ value: exam.id, label: exam.name, detail: exam.exam_code + ' · ' + (exam.date || '') }))} value={examId} change={changeExam} disabled={reading || busy} /></div>
      <QueryFeedback query={scopeQuery} />{!exams.length && <Notice kind="warn">本校暂无已配置参试范围的考试。请先到 <Link className="report-empty-link" to="/admin/school?tab=exam-management">考务管理</Link> 创建考试。</Notice>}
      {scope && <><section className="scope-panel"><h3>本批报告范围</h3><ClassificationFields row={config} scope={scope} change={configure} disabled={reading || busy} /><div className="muted">科目、班级和学生取自考务管理中本次考试的参试范围。每批仅选择一个科目，可批量上传本科目的多份报告。</div></section>
        {ready ? <section className="naming-panel"><div className="actions"><h3>文件命名规则</h3><button className="btn small" disabled={busy || reading} onClick={() => void downloadNames()}>下载本次范围命名清单</button></div><code>{filenamePattern(config)}</code><div className="naming-example">示例：<span>{filenameFor(scope, config, targetsFor(scope, config)[0].value)}</span></div><p>考试ID、报告类型和科目须与上方一致。字段用半角下划线 _ 分隔，每批仅上传一个科目的文件；学生ID／账号及姓名须对应参试名单。上传后自动校验 PDF、文件名与参试范围，并预填归属，下一步可修改。</p></section> : <Notice kind="warn">请先选择报告类别、类型和科目，再查看命名规则并上传文件。</Notice>}
      </>}
      <label className={`dropzone ${ready ? '' : 'unavailable'} ${drag ? 'drag' : ''}`} htmlFor={ready && !reading ? inputId : undefined} aria-disabled={!ready || reading} onDragOver={e => { e.preventDefault(); if (ready && !reading) setDrag(true) }} onDragLeave={() => setDrag(false)} onDrop={e => { e.preventDefault(); setDrag(false); void addFiles(e.dataTransfer.files) }}><span className="upload-symbol">↥</span><strong>{ready ? '选择或拖入 PDF 文件' : '请先完成上方报告范围选择'}</strong><span className="muted">{reading ? '正在校验 PDF 和文件命名…' : '支持同一科目批量上传；不规范文件请改名后重新选择'}</span><span className="muted">单份不超过 15 MB、100 页；每批最多 30 份，合计不超过 30 MB</span></label>
      <input id={inputId} aria-label="上传 PDF 文件" type="file" accept="application/pdf,.pdf" multiple hidden disabled={!ready || reading || busy} onChange={e => { if (e.target.files) void addFiles(e.target.files); e.target.value = '' }} />
      {rows.map((file, i) => <div className="file-line" key={file.token}><div><div className="filename">{file.file.filename}</div><div className={`file-result ${rowErrors(file).length ? 'invalid' : 'valid'}`}>{rowErrors(file).length ? rowErrors(file).map((message, j) => <div key={j}>{message}</div>) : `✓ PDF、命名及参试范围校验通过 · 文件名识别：${targetLabel(scope!, file)} · ${file.page_count} 页`}</div></div><button className="btn quiet" disabled={reading || busy} onClick={() => { setRows(rows.filter((_, index) => index !== i)); setActive(0); invalidate() }}>移除</button></div>)}
    </>}
    {step === 2 && scope && row && <><div className="batch-summary"><span className="muted">{scope.name}</span><span className="muted">已按文件名识别 {rows.length} 份 · 可逐份修改</span></div><div className="queue-layout"><aside className="file-list">{rows.map((file, i) => <button className={`file-entry ${active === i ? 'active' : ''}`} key={file.token} onClick={() => { setActive(i); setTargetClass(''); setEditType(false) }}><span className="fname">{file.file.filename}</span><span className={`pill ${file.modified ? '' : 'green'}`}>{file.modified ? '已手动调整' : '已自动关联'}</span> <span className={`pill ${file.previewed ? 'green' : 'gray'}`}>{file.previewed ? '已预览' : '待预览'}</span></button>)}</aside><div className="assignment"><div className="assignment-head"><h3 style={{ margin: 0 }}>报告归属</h3><button className="btn small" onClick={() => { setPreviewToken(row.token); setPreview({ filename: row.file.filename, pages: row.page_count, upload: row.file }) }}>预览 PDF</button></div><div className="muted filename">{row.file.filename}</div><Notice kind="success">{row.modified ? '已手动调整归属，保存时以当前选项为准。' : '已根据文件名识别并关联参试对象，可修改下方归属。'}</Notice><div className="classification-summary"><div><b>{categoryName(row.category)} / {REPORT_TYPES[row.report_type]}</b><div className="muted">科目：{subjectLabel(scope, row)}</div></div><button className="btn small" onClick={() => setEditType(!editType)}>{editType ? '收起' : '修改报告类型'}</button></div>
      {editType && <div className="scope-panel"><ClassificationFields row={row} scope={scope} change={updateRow} batch={false} /></div>}
      {kind === 'school' ? <div className="form-row"><label>报告对象</label><div className="control">{scope.school} · 本次考试参试范围</div></div> : <>{!!classes.length && <div className="form-row"><label>班级筛选<br /><span className="muted">（可选）</span></label><div><select className="control" aria-label="班级筛选（可选）" value={targetClass} onChange={e => setTargetClass(e.target.value)}><option value="">不限班级</option>{classes.map(cls => <option key={cls} value={cls}>{cls.replace('|', ' ')}</option>)}</select><div className="muted picker-hint">用于缩小下方学生候选范围，不改变当前关联学生。</div></div></div>}
        <div className="form-row"><label className="required">{kind === 'student' ? '关联学生' : kind === 'class' ? '关联班级' : '关联年级'}</label><SearchPicker label={kind === 'student' ? '关联学生' : kind === 'class' ? '关联班级' : '关联年级'} placeholder={kind === 'student' ? '输入学生姓名 / ID / 账号关键词' : '输入年级 / 班级关键词'} hint="支持关键词模糊搜索，点击匹配项选择。仅显示本次考试本科目的参试对象。" items={targetOptions} value={row.target_key} change={target => updateRow({ category: row.category, report_type: row.report_type, subject_ids: row.subject_ids, target_key: target })} /></div></>}
      <div className="panel"><div className="muted">当前归属</div><b>{targetLabel(scope, row)}</b><div className="muted">{subjectLabel(scope, row)} · {REPORT_TYPES[row.report_type]}</div></div>
    </div></div></>}
    {step === 3 && scope && <><div className="batch-summary"><h3>待保存 {rows.length} 份报告</h3><span className="muted">{scope.name} · {scope.exam_code}</span></div><div className="table-wrap"><table><thead><tr>{['文件', '类别 / 类型', '科目', '对象'].map(label => <th key={label}>{label}</th>)}</tr></thead><tbody>{rows.map(file => <tr key={file.token}><td className="wrap">{file.file.filename}<div className="sub">{file.page_count} 页 · {fileSize(file.file_size)}</div></td><td>{categoryName(file.category)}<div className="sub">{REPORT_TYPES[file.report_type]}</div></td><td>{subjectLabel(scope, file)}</td><td className="wrap">{targetLabel(scope, file)}</td></tr>)}</tbody></table></div></>}
    <Notice>{error}</Notice>
    {preview && <ReportPdfViewer source={preview} close={() => setPreview(null)} onRendered={() => setRows(previous => previous.map(file => file.token === previewToken && !file.previewed ? { ...file, previewed: true } : file))} />}
  </Drawer>
}

function Metadata({ report }: { report: ReportRecord }) {
  return <div className="kv"><span>报告ID</span><div>{report.report_code}</div><span>所属考试</span><div>{report.exam_name}<div className="muted">{report.exam_code}</div></div><span>类别 / 类型</span><div>{report.category_name} / {report.type_name}</div><span>科目范围</span><div>{report.subject_names.join('、')}</div><span>报告对象</span><div>{report.target_label}</div></div>
}

function ReportDetail({ report, close, replace, remove, writable }: { report: ReportRecord; close: () => void; replace: () => void; remove: () => void; writable: boolean }) {
  const query = useJsonQuery<ReportRecord>(`${REPORT_ROOT}/${report.id}`), [preview, setPreview] = useState<PdfSource | null>(null), [error, setError] = useState(''), [busy, setBusy] = useState(false)
  const row = query.data || report
  const download = async (file: ReportFile) => { setBusy(true); setError(''); try { downloadBlob(await reportBlob(fileSource(row, file).path!), file.filename) } catch (e) { setError(errorText(e)) } finally { setBusy(false) } }
  return <Drawer title="报告详情" close={close} busy={busy} footer={<><button className="btn" disabled={busy} onClick={close}>关闭</button>{writable && <div className="actions"><button className="btn danger" disabled={busy || !!query.error} onClick={remove}>删除报告</button><button className="btn primary" disabled={busy || !!query.error} onClick={replace}>替换更新</button></div>}</>}>
    <QueryFeedback query={query} /><Metadata report={row} /><div className="panel"><h3>当前文件 <span className="pill green">v{row.version}</span></h3><div className="filename">{row.file.filename}</div><p className="muted">{row.file.page_count} 页 · {fileSize(row.file.file_size)} · {reportDate(row.updated_at)}</p><div className="actions"><button className="btn small" disabled={busy || !!query.error} onClick={() => setPreview(fileSource(row))}>预览 PDF</button><button className="btn small" disabled={busy || !!query.error} onClick={() => void download(row.file)}>下载 PDF</button></div></div>
    <h3>版本记录</h3><div className="history">{(row.versions || [row.file]).map(file => <div className="history-item" key={file.version}><b>v{file.version} · {file.version === row.version ? '当前版本' : '历史版本'}</b><div>{file.filename}</div><div>{reportDate(file.created_at)} · {file.operator_name}</div>{file.reason && <div>{file.reason}</div>}{file.version !== row.version && <div className="history-file"><button className="btn small" disabled={busy} onClick={() => setPreview(fileSource(row, file))}>预览历史 PDF</button><button className="btn small" disabled={busy} onClick={() => void download(file)}>下载</button></div>}</div>)}</div><Notice>{error}</Notice>
    {preview && <ReportPdfViewer source={preview} close={() => setPreview(null)} />}
  </Drawer>
}

function ReportReplace({ report, close, saved }: { report: ReportRecord; close: () => void; saved: (message: string) => Promise<void> }) {
  const [file, setFile] = useState<(PdfUpload & { page_count: number; file_size: number }) | null>(null), [preview, setPreview] = useState<PdfSource | null>(null), [previewed, setPreviewed] = useState(false), [confirmed, setConfirmed] = useState(false), [reason, setReason] = useState(''), [reading, setReading] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState('')
  const inputId = useId(), generation = useRef(0), key = useRef(randomKey())
  useEffect(() => () => { generation.current++ }, [])
  const pick = async (selected?: File) => {
    if (!selected) return
    const token = ++generation.current; setReading(true); setFile(null); setPreviewed(false); setConfirmed(false); setError(''); key.current = randomKey()
    try { const upload = await readPdfFile(selected), parsed = await reportRequest<{ page_count: number; file_size: number }>('/inspect-pdf', upload); if (token === generation.current) setFile({ ...upload, ...parsed }) }
    catch (e) { if (token === generation.current) setError(errorText(e)) } finally { if (token === generation.current) setReading(false) }
  }
  const save = async () => {
    if (!file || !previewed || !confirmed || !reason.trim()) { setError('请选择有效 PDF、填写原因，并预览核对新文件'); return }
    setBusy(true); setError('')
    try { await reportRequest(`/${report.id}/replace`, { expected_version: report.version, file: { filename: file.filename, content_base64: file.content_base64 }, reason: reason.trim(), previewed, confirmed }, 'POST', key.current); await saved('已替换 PDF，原归属与查询授权不变') }
    catch (e) { setError(mutationError(e, '替换失败，原报告仍可用：')); setBusy(false) }
  }
  return <Drawer title="替换更新" close={close} busy={busy} footer={<><button className="btn" disabled={busy} onClick={close}>取消</button><button className="btn primary" disabled={!file || reading || busy} onClick={() => void save()}>{busy ? '替换中…' : `确认替换为 v${report.version + 1}`}</button></>}>
    <Metadata report={report} /><div className="panel"><h3>原文件 · v{report.version}</h3><div className="filename">{report.file.filename}</div><button className="btn quiet" onClick={() => setPreview(fileSource(report))}>查看原 PDF</button></div><h3>替换文件</h3><label className="btn" htmlFor={inputId}>选择新 PDF</label><input id={inputId} aria-label="选择新 PDF" type="file" accept="application/pdf,.pdf" hidden disabled={reading || busy} onChange={e => { void pick(e.target.files?.[0]); e.target.value = '' }} />
    {file ? <div className="file-line"><span>{file.filename}<div className="muted">{file.page_count} 页 · {fileSize(file.file_size)}</div></span><button className="btn small" disabled={busy} onClick={() => setPreview({ filename: file.filename, pages: file.page_count, upload: { filename: file.filename, content_base64: file.content_base64 } })}>预览新 PDF</button></div> : <p className="muted" role="status">{reading ? '正在校验 PDF…' : '尚未选择替换文件'}</p>}
    <div className="form-row"><label className="required" htmlFor={inputId + '-reason'}>替换原因</label><textarea id={inputId + '-reason'} className="control reason" aria-label="替换原因" maxLength={1000} placeholder="填写更新原因" value={reason} disabled={busy} onChange={e => { setReason(e.target.value); key.current = randomKey() }} /></div><label className="audit-check"><input type="checkbox" disabled={!previewed || busy} checked={confirmed} onChange={e => { setConfirmed(e.target.checked); key.current = randomKey() }} />已核对新 PDF，报告归属保持不变</label><Notice>{error}</Notice>
    {preview && <ReportPdfViewer source={preview} close={() => setPreview(null)} onRendered={preview.upload ? () => setPreviewed(true) : undefined} />}
  </Drawer>
}

function BatchTable({ reports }: { reports: ReportRecord[] }) {
  return <div className="table-wrap"><table><thead><tr>{['报告ID / 文件', '所属考试', '类别 / 类型', '科目', '对象'].map(label => <th key={label}>{label}</th>)}</tr></thead><tbody>{reports.map(report => <tr key={report.id}><td className="wrap">{report.report_code}<div className="sub">{report.file.filename} · v{report.version}</div></td><td className="wrap">{report.exam_name}<div className="sub">{report.exam_code}</div></td><td>{report.category_name}<div className="sub">{report.type_name}</div></td><td>{report.subject_names.join('、')}</td><td className="wrap">{report.target_label}</td></tr>)}</tbody></table></div>
}

function ReportDelete({ reports, close, saved }: { reports: ReportRecord[]; close: () => void; saved: (message: string) => Promise<void> }) {
  const [reason, setReason] = useState(''), [confirmed, setConfirmed] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState(''), key = useRef(randomKey()), inputId = useId()
  const save = async () => {
    if (!reason.trim() || !confirmed) { setError('请填写删除原因并确认清单'); return }
    setBusy(true); setError('')
    try { await reportRequest('/delete', { reports: reports.map(report => ({ id: report.id, expected_version: report.version })), reason: reason.trim(), confirmed }, 'POST', key.current); await saved(`已删除 ${reports.length} 份报告`) }
    catch (e) { setError(mutationError(e, '删除失败，全部原报告保持可用：')); setBusy(false) }
  }
  return <Drawer title={`删除报告 · ${reports.length} 份`} wide={reports.length > 3} close={close} busy={busy} footer={<><button className="btn" disabled={busy} onClick={close}>取消</button><button className="btn danger" disabled={busy} onClick={() => void save()}>{busy ? '删除中…' : '确认删除'}</button></>}>
    <Notice kind="warn">删除后，这 {reports.length} 份报告不再提供查询。考试、成绩、档案及其他报告保留。</Notice><BatchTable reports={reports} /><div className="form-row"><label className="required" htmlFor={inputId}>删除原因</label><textarea id={inputId} className="control reason" aria-label="删除原因" placeholder="填写误传、重复或其他删除原因" value={reason} disabled={busy} maxLength={1000} onChange={e => { setReason(e.target.value); key.current = randomKey() }} /></div><label className="audit-check"><input type="checkbox" disabled={busy} checked={confirmed} onChange={e => { setConfirmed(e.target.checked); key.current = randomKey() }} />已核对所选报告，确认删除</label><Notice>{error}</Notice>
  </Drawer>
}

function ReportLogs({ back }: { back: () => void }) {
  const [page, setPage] = useState(1), query = useJsonQuery<{ items: Operation[]; total: number }>(`${REPORT_ROOT}/operations?page=${page}&page_size=12`)
  return <><div className="toolbar"><div className="actions"><h2>操作记录</h2><span className="stat-inline">共 {query.data?.total || 0} 条</span></div><button className="btn" onClick={back}>返回报告维护</button></div><QueryFeedback query={query} /><div className="logs">{query.data?.items.map(log => <article className="log" key={log.id}><div className="log-meta"><div className="actions"><span className={`pill ${log.action === '删除报告' ? 'red' : log.action === '替换更新' ? 'green' : ''}`}>{log.action}</span><b>{log.details.length} 份报告</b><span className="pill green">成功</span></div><span className="muted mono">{reportDate(log.created_at)} · {log.operator_name}</span></div>{log.reason && <p>{log.reason}</p>}<details><summary>查看报告明细</summary><BatchTable reports={log.details} />{log.details.filter(row => row.previous_file).map(row => <p className="muted" key={row.id}>原文件：{row.previous_file!.filename} · v{row.previous_file!.version} → {row.file.filename} · v{row.version}</p>)}</details></article>)}{query.data && !query.data.items.length && <div className="empty">暂无操作记录</div>}</div>{!!query.data?.total && <Paging page={page} total={query.data.total} change={setPage} />}</>
}

type AccessRow = { id: string; report_code: string; type_name: string; target_label: string; subject_names: string[]; exam_name: string; exam_code: string; allowed: boolean; why: string }
function ReportAccess({ exams, initialExam, close }: { exams: ReportExam[]; initialExam: string; close: () => void }) {
  const [examId, setExamId] = useState(initialExam || exams[0]?.id || ''), [kind, setKind] = useState('teacher'), [identity, setIdentity] = useState(''), [login, setLogin] = useState(true), [preview, setPreview] = useState<PdfSource | null>(null), [error, setError] = useState(''), [busy, setBusy] = useState(false)
  const scope = useJsonQuery<ExamScope>(`${REPORT_ROOT}/exams/${examId}`, !!examId)
  const identities: PickerItem[] = kind === 'teacher' ? scope.data?.teachers.map(teacher => ({ value: teacher.id, label: teacher.name, detail: teacher.platform_id + ' · 账号 ' + teacher.account + (teacher.login_allowed ? '' : ' · 账号不可登录') })) || [] : scope.data ? [...new Set(scope.data.subjects.flatMap(subject => subject.student_ids))].map(id => {
    const person = scope.data!.snapshots[id]; return { value: id, label: person.name, detail: `${person.platform_id} · 账号 ${person.account} · ${person.grade} ${person.class_number}` }
  }) : []
  const recipient = identities.some(item => item.value === identity) ? identity : identities[0]?.value || ''
  const query = useJsonQuery<{ reports: AccessRow[] }>(`${REPORT_ROOT}/access-check?${new URLSearchParams({ exam_id: examId, kind, recipient_id: recipient, login: String(login) })}`, !!examId && !!recipient)
  const show = async (row: AccessRow) => { setBusy(true); setError(''); try { const report = await reportRequest<ReportRecord>(`/${row.id}`, undefined, 'GET'); setPreview(fileSource(report)) } catch (e) { setError(errorText(e)) } finally { setBusy(false) } }
  return <Drawer title="核对报告查询权限" close={close} busy={busy} footer={<button className="btn" disabled={busy} onClick={close}>关闭</button>}>
    <div className="form-row"><label>所属考试</label><SearchPicker label="权限核对所属考试" placeholder="输入考试名称 / ID关键词" hint="支持考试名称或ID关键词模糊搜索，点击匹配项选择。" items={exams.map(exam => ({ value: exam.id, label: exam.name, detail: exam.exam_code + ' · ' + (exam.date || '') }))} value={examId} change={id => { setExamId(id); setIdentity('') }} /></div>
    <div className="form-row"><label htmlFor="report-access-role">查询身份</label><select id="report-access-role" className="control" aria-label="查询身份" value={kind} onChange={e => { setKind(e.target.value); setIdentity('') }}><option value="teacher">教师（含校长等兼任角色）</option><option value="student">学生</option></select></div>
    <QueryFeedback query={scope} /><div className="form-row"><label>查询账号</label><SearchPicker label="查询账号" placeholder="输入姓名 / ID / 账号关键词" hint="支持姓名、ID或账号关键词模糊搜索，点击匹配项选择。" items={identities} value={recipient} change={setIdentity} /></div>
    <label className="audit-check"><input type="checkbox" checked={login} onChange={e => setLogin(e.target.checked)} />账号可正常登录</label><Notice kind="warn">{kind === 'student' ? '仅显示所选学生本人的个人报告；查询状态按本次考试授权判定。' : '按已保存的考试授权核对；本页不修改查询权限。'}</Notice><QueryFeedback query={query} /><Notice>{error}</Notice>
    <div className="table-wrap"><table className="access-table"><thead><tr>{['报告 / 对象', '所属考试', '查询判定', '操作'].map(label => <th key={label}>{label}</th>)}</tr></thead><tbody>{query.data?.reports.map(row => <tr key={row.id}><td className="access-report">{row.type_name}<div className="sub">{row.target_label} · {row.subject_names.join('、')}</div></td><td className="access-exam">{row.exam_name}<div className="sub">{row.exam_code}</div></td><td><span className={`pill ${row.allowed ? 'green' : 'gray'}`}>{row.allowed ? '可查询' : '不可查询'}</span><div className="sub">{row.why}</div></td><td>{row.allowed && <button className="btn small" disabled={busy} onClick={() => void show(row)}>查看 PDF</button>}</td></tr>)}{(!query.isLoading && !query.data?.reports.length) && <tr><td colSpan={4}><div className="empty">{!exams.length ? '本校暂无已配置参试范围的考试' : !recipient ? '本次考试暂无可核对账号' : kind === 'student' ? '该学生在本次考试中暂无个人报告' : '本次考试暂无报告'}</div></td></tr>}</tbody></table></div>
    {preview && <ReportPdfViewer source={preview} close={() => setPreview(null)} />}
  </Drawer>
}
