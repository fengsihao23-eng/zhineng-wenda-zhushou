import { useRef, useState, type FormEvent } from 'react'
import { useApiAction } from '../hooks/useApi'
import { ErrorDisplay } from './ErrorDisplay'
import { ReasonForm } from './WorkflowControls'

export type Knowledge = {
  id: string; title: string; subject: string; doc_type: string; status: string; version: string;
  content: string; source_name: string; source_url: string | null; source_reference: string;
  tags: string[]; rejection_reason: string | null; state_version: number; allowed_actions: string[];
  created_at: string | null; reviewed_at: string | null;
}
const blank = { title: '', subject: '数学', doc_type: '校本讲义', content: '', source_name: '', source_reference: '', source_url: '', tags: [] as string[] }

export function KnowledgeForm({ item, onClose }: { item?: Knowledge; onClose: () => void }) {
  const [form, setForm] = useState(item ? { title: item.title, subject: item.subject, doc_type: item.doc_type, content: item.content, source_name: item.source_name, source_reference: item.source_reference, source_url: item.source_url || '', tags: item.tags } : blank)
  const mutation = useApiAction(item ? 'PATCH' : 'POST')
  const locked = useRef(false)
  const save = (event: FormEvent) => {
    event.preventDefault()
    if (locked.current) return
    locked.current = true
    mutation.mutate({ path: item ? `/platform/management/knowledge/${item.id}` : '/platform/management/knowledge', body: { ...form, ...(item ? { expected_version: item.state_version } : {}) } }, {
      onSuccess: onClose, onSettled: () => { locked.current = false },
    })
  }
  return <form className="modal-card" onSubmit={save}><h3>{item ? '编辑返工文档' : '新建知识文档'}</h3>
    {item?.rejection_reason && <p role="note">驳回意见：{item.rejection_reason}</p>}
    <ErrorDisplay error={mutation.error} title="保存失败" variant="banner" />
    <div className="form-grid">{([['title', '文档标题'], ['subject', '科目'], ['source_name', '来源名称'], ['source_reference', '来源引用'], ['source_url', '来源链接']] as const).map(([key, label]) => <label className="form-field" key={key}><span>{label}</span><input className="form-input" required={key !== 'source_url'} value={form[key]} maxLength={key === 'source_url' ? 1000 : key === 'source_reference' ? 500 : 200} onChange={event => setForm({ ...form, [key]: event.target.value })} /></label>)}
      <label className="form-field form-field--full"><span>正文内容</span><textarea className="form-textarea" required value={form.content} onChange={event => setForm({ ...form, content: event.target.value })} /></label></div>
    <div className="page-actions"><button className="primary-button" disabled={mutation.isPending}>保存草稿</button><button type="button" className="secondary-button" disabled={mutation.isPending} onClick={onClose}>取消</button></div>
  </form>
}

export function KnowledgeActions({ item, onEdit }: { item: Knowledge; onEdit: () => void }) {
  const mutation = useApiAction('POST')
  const locked = useRef(false)
  const [pending, setPending] = useState<string | null>(null)
  const labels: Record<string, string> = { submit: '提交审核', approve: '通过', reject: '驳回', offline: '下线', republish: '重新发布' }
  const submit = (action: string, reason?: string) => {
    if (locked.current) return
    locked.current = true
    mutation.mutate({ path: `/platform/management/knowledge/${item.id}/review`, body: { action, reason, expected_version: item.state_version } }, { onSuccess: () => setPending(null), onSettled: () => { locked.current = false } })
  }
  return <div><ErrorDisplay error={mutation.error} variant="banner" />{pending ? <ReasonForm label={labels[pending]} busy={mutation.isPending} onSubmit={reason => submit(pending, reason)} onCancel={() => setPending(null)} /> : <div className="table-actions">
    {['draft', 'rejected'].includes(item.status) && <button className="action-link" disabled={mutation.isPending} onClick={onEdit}>{item.status === 'rejected' ? '编辑返工' : '编辑'}</button>}
    {(item.allowed_actions || []).map(action => <button className="action-link" key={action} disabled={mutation.isPending} onClick={() => { if (['reject', 'offline'].includes(action)) setPending(action); else submit(action) }}>{labels[action] || action}</button>)}
  </div>}</div>
}
