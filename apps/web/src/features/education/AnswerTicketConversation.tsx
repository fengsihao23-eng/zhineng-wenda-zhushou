import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { ErrorDisplay } from '../../components/ErrorDisplay'
import { useApiAction, useJsonQuery } from '../../hooks/useApi'

type Ticket = {
  id: string; revision: number; status: string; question: string; currentAllowed: boolean; canReply: boolean
  assignee?: { id: string; name: string }; sources: Record<string, unknown>[]
  context: { id: string; role: string; text: string }[]
  events: { role: string; text: string; by?: string; at: string }[]
}

export function AnswerTicketConversation({ id }: { id: string }) {
  const [open, setOpen] = useState(false)
  const [text, setText] = useState(''), [reviewed, setReviewed] = useState(false)
  const [kind, setKind] = useState('routing')
  const query = useJsonQuery<Ticket>(`/answer-workbench/tickets/${id}?management=true`, open)
  const action = useApiAction(), cache = useQueryClient()
  const ticket = query.data
  const run = (name: string) => {
    if (!ticket) return
    action.mutate({ path: `/answer-workbench/tickets/${id}/${name}`, body: {
      expected: ticket.revision,
      ...(name === 'reply' ? { text, reply_kind: kind, reviewed, sources: kind === 'data' ? ticket.sources : [] } : {}),
    } }, { onSuccess: async () => { setText(''); setReviewed(false); await cache.invalidateQueries() },
      onError: () => { void query.refetch() } })
  }
  return <section>
    <button className="secondary-button" onClick={() => setOpen(value => !value)}>{open ? '收起问答留言' : '处理问答人工留言'}</button>
    {open && <div className="panel">
      {query.isLoading && <p>正在读取留言…</p>}
      {query.error && <ErrorDisplay error={query.error} onRetry={() => { void query.refetch() }} />}
      {ticket && <>
        <div className="page-toolbar"><span>{ticket.status} · 处理人：{ticket.assignee?.name || '尚未接单'}</span><button className="secondary-button" onClick={() => { void query.refetch() }}>刷新留言</button></div>
        {!ticket.currentAllowed && <p role="status">来源权限已变化或当前教师无权查看，相关内容已隐藏。可回复办理指引，数据问题请由有权限的老师核查。</p>}
        {ticket.context.length > 0 && <details><summary>查看学生提交的问答上下文</summary>{ticket.context.map(message => <p key={message.id}><strong>{message.role === 'user' ? '学生' : '助手'}：</strong>{message.text}</p>)}</details>}
        <div role="log" aria-label="问答人工留言消息">{ticket.events.map((event, index) => <article className={`wb-message wb-message--${event.role === 'operator' ? 'staff' : event.role}`} key={index}><strong>{event.by || (event.role === 'user' ? '学生' : event.role === 'operator' ? '老师' : '系统')}</strong> · <time>{event.at}</time><p>{event.text}</p></article>)}</div>
        {ticket.status === '待处理' && <button className="primary-button" disabled={action.isPending} onClick={() => run('claim')}>领取留言</button>}
        {ticket.canReply && <form className="wb-form" onSubmit={event => { event.preventDefault(); run('reply') }}>
          <label>回复类型<select aria-label="回复类型" value={kind} onChange={event => setKind(event.target.value)}><option value="routing">办理指引</option><option value="insufficient">说明资料不足</option><option value="permission">说明权限</option>{ticket.currentAllowed && ticket.sources.length > 0 && <option value="data">引用已核对的数据来源</option>}</select></label>
          <label>回复学生<textarea aria-label="回复问答人工留言" required maxLength={4000} value={text} onChange={event => setText(event.target.value)} /></label>
          <label><input type="checkbox" checked={reviewed} onChange={event => setReviewed(event.target.checked)} />已核对回复对象、来源及当前权限</label>
          <button className="primary-button" disabled={action.isPending || !text.trim() || !reviewed}>发送回复</button>
        </form>}
      </>}
      {action.error && <ErrorDisplay error={action.error} />}
    </div>}
  </section>
}
