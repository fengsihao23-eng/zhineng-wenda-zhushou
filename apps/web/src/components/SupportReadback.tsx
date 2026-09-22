import { useJsonQuery } from '../hooks/useApi'
import { ErrorDisplay } from './ErrorDisplay'
import { HumanConversation } from '../features/education/LearningPanels'

type Item = { id: string; status: string; category?: string; reason?: string; resolution: string | null; assigned?: boolean }
export function SupportReadback() {
  const feedback = useJsonQuery<Item[]>('/platform/student/feedback')
  const handoffs = useJsonQuery<Item[]>('/platform/student/handoffs')
  const labels: Record<string, string> = { open: '待处理', acknowledged: '已确认', accepted: '处理中', resolved: '已解决', closed: '已关闭' }
  return <section className="panel"><h2>我的反馈与跟进进度</h2><p>查看真实处理进度、老师回复与历史记录，也可以补充消息。</p>
    {([['反馈记录', feedback], ['人工工单', handoffs]] as const).map(([title, query]) => <section key={title}><h3>{title}</h3>{query.isLoading ? <p>正在读取…</p> : query.error ? <ErrorDisplay error={query.error} onRetry={() => { void query.refetch() }} /> : !query.data?.length ? <p className="inline-empty">暂无{title}。</p> : query.data.map(item => <article className="feedback-card" key={item.id}><strong>{item.reason || item.category}</strong><p>{labels[item.status] || item.status}{item.assigned ? ' · 已有老师跟进' : ''}</p><p>{item.resolution || '尚无处理说明。'}</p>{title === '人工工单' && <HumanConversation id={item.id} student />}</article>)}</section>)}
  </section>
}
