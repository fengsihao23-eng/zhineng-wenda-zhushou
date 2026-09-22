import { QueryClient } from '@tanstack/react-query'
import { getAuthScope, subscribeAuth } from '../utils/auth'
import { ApiError, isAbortError } from './http'

export function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        refetchOnWindowFocus: false,
        retry: (count, error) => !isAbortError(error) && !(error instanceof ApiError && error.status && error.status < 500) && count < 1,
        staleTime: 30_000,
      },
      mutations: { retry: false },
    },
  })
}

/** Install before rendering, so logout clears caches synchronously with identity changes. */
export function bindQueryClientToAuth(client: QueryClient): () => void {
  let scope = getAuthScope()
  return subscribeAuth(() => {
    const nextScope = getAuthScope()
    if (scope === nextScope) return
    scope = nextScope
    void client.cancelQueries()
    client.clear()
  })
}
