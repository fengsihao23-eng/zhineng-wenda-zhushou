import { useCallback, useEffect, useState, type ReactNode } from 'react'
import './ListControls.css'

export const PAGE_SIZES = [10, 20, 50, 100] as const

export function usePagination(resetKey = '') {
  const [state, setState] = useState({ page: 1, pageSize: 20, resetKey })
  const page = state.resetKey === resetKey ? state.page : 1
  useEffect(() => {
    setState(current => current.resetKey === resetKey ? current : { ...current, page: 1, resetKey })
  }, [resetKey])
  const onChange = useCallback((next: number) => setState(current => ({ ...current, page: next, resetKey })), [resetKey])
  const onPageSizeChange = (pageSize: number) => setState({ page: 1, pageSize, resetKey })
  return { page, pageSize: state.pageSize, onChange, onPageSizeChange }
}

export function useClientPagination<T>(items: readonly T[], resetKey = '') {
  const pagination = usePagination(resetKey)
  const page = Math.min(pagination.page, Math.max(1, Math.ceil(items.length / pagination.pageSize)))
  useEffect(() => {
    if (pagination.page !== page) pagination.onChange(page)
  }, [page, pagination.page, pagination.onChange])
  return {
    ...pagination,
    page,
    total: items.length,
    items: items.slice((page - 1) * pagination.pageSize, page * pagination.pageSize),
  }
}

type PaginationProps = {
  page: number
  pageSize: number
  total: number
  onChange: (page: number) => void
  onPageSizeChange: (pageSize: number) => void
}

export function Pagination({ page, pageSize, total, onChange, onPageSizeChange }: PaginationProps) {
  const pages = Math.max(1, Math.ceil(total / pageSize))
  const current = Math.min(page, pages)
  // A deletion or a refreshed result set may remove the last page.
  useEffect(() => {
    if (page > pages) onChange(pages)
  }, [page, pages, onChange])
  return <nav className="list-pagination" aria-label="列表分页">
    <span className="list-pagination__count">共 {total} 条</span>
    <label className="list-pagination__size">每页显示
      <select aria-label="每页显示条数" value={pageSize} onChange={event => onPageSizeChange(Number(event.target.value))}>
        {PAGE_SIZES.map(size => <option key={size} value={size}>{size} 条</option>)}
      </select>
    </label>
    <div className="list-pagination__pages">
      <button type="button" disabled={current <= 1} onClick={() => onChange(current - 1)}>上一页</button>
      <span aria-live="polite">第 {current} / {pages} 页</span>
      <button type="button" disabled={current >= pages} onClick={() => onChange(current + 1)}>下一页</button>
    </div>
  </nav>
}

export function ListView<T>({ items, resetKey = '', children }: {
  items: readonly T[]
  resetKey?: string
  children: (items: readonly T[]) => ReactNode
}) {
  const pagination = useClientPagination(items, resetKey)
  return <><Pagination {...pagination} />{children(pagination.items)}</>
}
