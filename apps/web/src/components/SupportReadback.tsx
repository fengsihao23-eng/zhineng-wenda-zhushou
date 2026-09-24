import { useState } from 'react'
import { useJsonQuery } from '../hooks/useApi'
import { ErrorDisplay } from './ErrorDisplay'
import { ListView } from './ListControls'
import { HelpTip } from './HelpTip'
import { HumanConversation } from '../features/education/LearningPanels'

type Item = { id: string; status: string; category?: string; reason?: string; resolution: string | null; assigned?: boolean }
export function SupportReadback() {
  const [kind, setKind] = useState<'feedback' | 'handoffs'>('feedback')
  const query = useJsonQuery<Item[]>(`/platform/student/${kind}`)
  const labels: Record<string, string> = { open: '待处理', acknowledged: '已确认', accepted: '处理中', resolved: '已解决', closed: '已关闭' }
  return <section className="panel">
    <div className="wb-tabs"><button className={kind === 'feedback' ? 'active' : ''} onClick={() => setKind('feedback')}>反馈记录</button><button className={kind === 'handoffs' ? 'active' : ''} onClick={() => setKind('handoffs')}>人工工单</button><HelpTip label="跟进说明">查看处理进度和老师回复；人工工单中可以补充消息。</HelpTip></div>
    {query.isLoading ? <p>正在读取…</p> : query.error ? <ErrorDisplay error={query.error} onRetry={() => { void query.refetch() }} /> : !query.data?.length ? <p className="inline-empty">暂无记录。</p> : <ListView items={query.data} resetKey={kind}>{rows => rows.map(item => <article className="feedback-card" key={item.id}>
      <strong>{item.reason || item.category}</strong><p>{labels[item.status] || item.status}{item.assigned ? ' · 已有老师跟进' : ''}</p>{item.resolution && <p>{item.resolution}</p>}{kind === 'handoffs' && <HumanConversation id={item.id} student />}
    </article>)}</ListView>}
  </section>
}
