import { useRef, useState } from 'react'
import { ErrorDisplay } from './ErrorDisplay'
import { useApiAction } from '../hooks/useApi'

export type WorkflowRecord = {
  id: string
  status: string
  state_version: number
  resolution?: string | null
  allowed_transitions: string[]
}

export function ReasonForm({ label, busy, onSubmit, onCancel }: {
  label: string; busy: boolean; onSubmit: (reason: string) => void; onCancel: () => void
}) {
  const [reason, setReason] = useState('')
  return <form className="workflow-reason" onSubmit={event => { event.preventDefault(); if (!busy && reason.trim()) onSubmit(reason.trim()) }}>
    <label className="form-field"><span>{label}说明（必填）</span><textarea autoFocus className="form-textarea" required maxLength={500} value={reason} onChange={event => setReason(event.target.value)} placeholder="填写实际核查、处理结果或返工原因，不要填写不必要的学生个人信息。" /></label>
    <div className="card-actions"><button className="primary-button" type="submit" disabled={busy || !reason.trim()}>{busy ? '保存中…' : `确认${label}`}</button><button className="secondary-button" type="button" disabled={busy} onClick={onCancel}>取消</button></div>
  </form>
}

export function WorkflowControls({ kind, item }: { kind: 'feedback' | 'risk' | 'handoff'; item: WorkflowRecord }) {
  const mutation = useApiAction('PATCH')
  const locked = useRef(false)
  const [target, setTarget] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  const labels: Record<string, string> = {
    acknowledged: ['resolved', 'closed'].includes(item.status) ? '重新跟进' : '确认事件',
    accepted: '接单', resolved: kind === 'handoff' ? '完成跟进' : '标记解决',
    closed: '关闭', open: '重新打开',
  }
  const save = (status: string, resolution?: string) => {
    if (locked.current) return
    locked.current = true
    setSaved(false)
    mutation.mutate({ path: `/platform/management/${kind === 'risk' ? 'risks' : kind === 'handoff' ? 'handoffs' : 'feedback'}/${item.id}`, body: { status, resolution, expected_version: item.state_version } }, {
      onSuccess: () => { setTarget(null); setSaved(true) },
      onSettled: () => { locked.current = false },
    })
  }
  const start = (status: string) => {
    mutation.reset()
    setSaved(false)
    if (['resolved', 'closed'].includes(status) || ['resolved', 'closed'].includes(item.status)) setTarget(status)
    else save(status)
  }
  return <div className="workflow-controls">
    <ErrorDisplay error={mutation.error} title="操作失败" variant="banner" onDismiss={mutation.reset} />
    {item.resolution && <p className="workflow-resolution"><strong>处理说明：</strong>{item.resolution}</p>}
    {saved && <span className="subtle" role="status">操作已保存。</span>}
    {target ? <ReasonForm key={target} label={labels[target] || target} busy={mutation.isPending} onSubmit={reason => save(target, reason)} onCancel={() => setTarget(null)} /> : <div className="card-actions">
      {(item.allowed_transitions || []).map(status => <button key={status} className={`action-link${status === 'closed' ? ' action-link--danger' : ''}`} disabled={mutation.isPending} onClick={() => start(status)}>{labels[status] || status}</button>)}
      {!item.allowed_transitions?.length && <span className="subtle">当前无可用操作</span>}
    </div>}
  </div>
}
