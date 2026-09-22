import { useState } from 'react'
import { useApiQuery } from '../hooks/useApi'
import { ErrorDisplay } from './ErrorDisplay'
import { ReportVersions } from '../features/education/LearningPanels'

export function ReportSource({ id, hasSource }: { id: string; hasSource: boolean }) {
  const [open, setOpen] = useState(false)
  const source = useApiQuery<{ version: string; raw_content: string; source: string; generated_at: string }>(`/platform/student/diagnosis/${id}/source`, ['report-source', id], { enabled: open, staleTime: 0, gcTime: 0, refetchOnWindowFocus: true })
  return <div className="report-source">
    <button className="action-link" disabled={!hasSource} onClick={() => setOpen(value => !value)} aria-expanded={open}>{open ? '收起原始依据' : '查看原始依据 ↗'}</button>
    {!hasSource && <p className="subtle">该报告版本尚未接入原始内容，不能以摘要代替原件。</p>}
    <ReportVersions id={id} />
    {open && <section className="panel" aria-label="报告原始依据"><p>已存储原文 · {source.data?.version || '—'}（非原始 PDF 附件预览）</p>{source.isFetching ? <p>正在核验权益并读取原文…</p> : source.error ? <ErrorDisplay error={source.error} onRetry={() => { void source.refetch() }} /> : <pre className="report-source__text">{source.data?.raw_content}</pre>}</section>}
  </div>
}
