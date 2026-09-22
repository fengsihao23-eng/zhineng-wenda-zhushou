/**
 * 统一的 API 查询 hooks
 * 基于 TanStack Query 的规范化封装
 */
import { useRef, useSyncExternalStore } from 'react'
import { useQuery, useMutation, useQueryClient, type UseQueryOptions, type UseMutationOptions } from '@tanstack/react-query'
import { apiFetch, apiError } from '../services/api'
import { getAuthScope, subscribeAuth } from '../utils/auth'

// 类型定义
export interface DashboardData {
  student: { id: string; name: string }
  latest_exam: {
    id: string
    name: string
    date: string | null
    total_score: number
    full_score: number | null
    class_rank: number | null
    grade_rank: number | null
    score_delta: number | null
  } | null
  subjects: Array<{
    name: string
    score: number
    full_score: number | null
    percentage: number | null
    class_rank: number | null
    grade_rank: number | null
  }>
  exam_count: number
}

export interface TrendData {
  exams: Array<{
    id: string
    name: string
    date: string | null
    score: number
    full_score: number | null
    class_rank: number | null
    grade_rank: number | null
  }>
  subjects: Array<{
    subject: string
    exam: string
    date: string | null
    score: number
    full_score: number | null
  }>
  subject_names: string[]
}

export interface ChatSession {
  id: string
  title: string | null
  status: string
  created_at: string
  updated_at: string
  message_count: number
}

// 查询键工厂 - 统一管理所有查询键
export const queryKeys = {
  // 学生相关
  student: {
    dashboard: () => ['student', 'dashboard'] as const,
    trends: () => ['student', 'trends'] as const,
    diagnosis: () => ['student', 'diagnosis'] as const,
    mistakes: (subject?: string) => ['student', 'mistakes', subject] as const,
    authorization: () => ['student', 'authorization'] as const,
  },
  // 聊天相关
  chat: {
    sessions: () => ['chat', 'sessions'] as const,
    session: (id: string) => ['chat', 'session', id] as const,
    messages: (sessionId: string) => ['chat', 'messages', sessionId] as const,
  },
  // 管理相关
  management: {
    overview: () => ['management', 'overview'] as const,
    students: () => ['management', 'students'] as const,
    schools: () => ['management', 'schools'] as const,
    feedback: (status?: string) => ['management', 'feedback', status] as const,
    risks: (status?: string) => ['management', 'risks', status] as const,
    handoffs: (status?: string) => ['management', 'handoffs', status] as const,
    knowledge: (status?: string) => ['management', 'knowledge', status] as const,
  },
} as const

export function useAuthScope() {
  return useSyncExternalStore(subscribeAuth, getAuthScope, getAuthScope)
}

export function scopedQueryKey(queryKey: readonly unknown[], scope = getAuthScope()) {
  return [...queryKey, scope]
}

export async function fetchJson<T>(path: string, signal?: AbortSignal, scope = getAuthScope()): Promise<T> {
  if (scope !== getAuthScope()) throw new DOMException('请求已取消', 'AbortError')
  const response = await apiFetch(path, { signal })
  if (!response.ok) throw await apiError(response, '数据加载失败，请重试')
  const data = await response.json()
  if (signal?.aborted || scope !== getAuthScope()) throw new DOMException('请求已取消', 'AbortError')
  return data as T
}

export function useApiQuery<TData = unknown>(
  path: string,
  queryKey: readonly unknown[],
  options?: Omit<UseQueryOptions<TData, Error>, 'queryKey' | 'queryFn'>
) {
  const scope = useAuthScope()
  return useQuery<TData, Error>({
    queryKey: scopedQueryKey(queryKey, scope),
    queryFn: ({ signal }) => fetchJson<TData>(path, signal, scope),
    staleTime: 30_000,
    gcTime: 10 * 60 * 1000,
    ...options,
  })
}

// Equivalent endpoints share the same cache across the overview and older pages.
export function jsonQueryKey(path: string): readonly unknown[] {
  if (path === '/platform/student/dashboard') return queryKeys.student.dashboard()
  if (path === '/platform/student/trends') return queryKeys.student.trends()
  return ['json', path]
}

export function useJsonQuery<TData = unknown>(path: string, enabled = true) {
  return useApiQuery<TData>(path, jsonQueryKey(path), { enabled })
}

type ApiMutationOptions<TData, TVariables> = Omit<UseMutationOptions<TData, Error, TVariables>, 'mutationFn'> & {
  serialize?: (variables: TVariables) => unknown
}

export function useApiMutation<TData = unknown, TVariables = unknown>(
  path: string | ((variables: TVariables) => string),
  method: 'POST' | 'PUT' | 'PATCH' | 'DELETE' = 'POST',
  options?: ApiMutationOptions<TData, TVariables>
) {
  const scope = useAuthScope()
  const queryClient = useQueryClient()
  const { serialize, ...mutationOptions } = options || {}
  const submission = useRef<{ body: string; key: string } | null>(null)
  return useMutation<TData, Error, TVariables>({
    ...mutationOptions,
    mutationKey: ['api-mutation', scope],
    mutationFn: async (variables) => {
      if (scope !== getAuthScope()) throw new DOMException('请求已取消', 'AbortError')
      const url = typeof path === 'function' ? path(variables) : path
      const body = method !== 'DELETE' ? JSON.stringify(serialize ? serialize(variables) : variables) : undefined
      const fingerprint = `${url}:${body}`
      if (!submission.current || submission.current.body !== fingerprint) submission.current = { body: fingerprint, key: crypto.randomUUID() }
      const response = await apiFetch(url, {
        method,
        body,
        headers: method === 'POST' ? { 'Idempotency-Key': submission.current.key } : undefined,
      })
      if (!response.ok) throw await apiError(response, '操作失败，请重试')
      const data = response.status === 204 ? undefined : await response.json()
      if (scope !== getAuthScope()) throw new DOMException('请求已取消', 'AbortError')
      return data as TData
    },
    onSuccess: async (...args) => {
      submission.current = null
      if (scope !== getAuthScope()) return
      const url = typeof path === 'function' ? path(args[1]) : path
      if (url.startsWith('/platform/')) {
        await queryClient.invalidateQueries({ predicate: query => query.queryKey[query.queryKey.length - 1] === scope && !['chat', 'route-identity'].includes(String(query.queryKey[0])) })
      }
      if (scope === getAuthScope()) await mutationOptions.onSuccess?.(...args)
    },
    onError: (...args) => {
      if (scope === getAuthScope()) return mutationOptions.onError?.(...args)
    },
    onSettled: (...args) => {
      if (scope === getAuthScope()) return mutationOptions.onSettled?.(...args)
    },
  })
}

export function useApiAction(method: 'POST' | 'PATCH' = 'POST') {
  return useApiMutation<unknown, { path: string; body: Record<string, unknown> }>(
    variables => variables.path,
    method,
    { serialize: variables => variables.body },
  )
}

// 学生仪表盘
export function useStudentDashboard() {
  return useApiQuery<DashboardData>('/platform/student/dashboard', queryKeys.student.dashboard())
}

// 学生趋势
export function useStudentTrends() {
  return useApiQuery<TrendData>('/platform/student/trends', queryKeys.student.trends())
}

// 聊天会话列表
export function useChatSessions() {
  return useApiQuery<ChatSession[]>('/chat/sessions', queryKeys.chat.sessions())
}

// 聊天消息列表
export function useChatMessages<T>(sessionId: string) {
  return useApiQuery<T>(
    `/chat/sessions/${sessionId}/messages`,
    queryKeys.chat.messages(sessionId),
    { enabled: !!sessionId }
  )
}

// 创建聊天会话
export function useCreateChatSession() {
  const queryClient = useQueryClient()

  return useApiMutation<{ id: string; title: string | null }, { title?: string }>(
    '/chat/sessions',
    'POST',
    {
      onSuccess: () => {
        void queryClient.invalidateQueries({ queryKey: scopedQueryKey(queryKeys.chat.sessions()) })
      },
    }
  )
}

// 删除聊天会话
export function useDeleteChatSession() {
  const queryClient = useQueryClient()

  return useApiMutation<void, string>(
    (sessionId) => `/chat/sessions/${sessionId}`,
    'DELETE',
    {
      onSuccess: () => {
        void queryClient.invalidateQueries({ queryKey: scopedQueryKey(queryKeys.chat.sessions()) })
      },
    }
  )
}
