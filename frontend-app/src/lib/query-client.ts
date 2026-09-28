import { QueryClient } from '@tanstack/react-query'

import type { ApiError } from '@/types/api'

// Client errors (401/403/404/400…) won't succeed on retry; retry only network/server errors once.
function shouldRetry(failureCount: number, error: unknown) {
  const status = (error as ApiError | undefined)?.status
  if (status !== undefined && status >= 400 && status < 500) return false
  return failureCount < 1
}

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      retry: shouldRetry,
      refetchOnWindowFocus: false,
    },
  },
})
