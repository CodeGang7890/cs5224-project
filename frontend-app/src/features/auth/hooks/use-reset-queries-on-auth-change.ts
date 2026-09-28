import { useEffect, useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'

import { selectIsAuthenticated, useAuthStore } from '@/stores/auth-store'

import { authKeys } from './use-auth'

const isCurrentUserQuery = (queryKey: readonly unknown[]) =>
  queryKey[0] === authKeys.currentUser[0] && queryKey[1] === authKeys.currentUser[1]

/**
 * Resets cached queries when the user logs in or out (including an expired session or a
 * login/logout in another tab), so one user's data never shows for another.
 * Mounted once in `AppProviders`.
 */
export function useResetQueriesOnAuthChange() {
  const queryClient = useQueryClient()
  const isAuthenticated = useAuthStore(selectIsAuthenticated)
  const previous = useRef(isAuthenticated)

  useEffect(() => {
    if (previous.current === isAuthenticated) return
    previous.current = isAuthenticated

    if (!isAuthenticated) {
      // Drop the old profile entirely so the next login never flashes the previous user.
      queryClient.removeQueries({ queryKey: authKeys.currentUser })
    }
    // The current-user query is excluded: `login()` fetches it itself, and resetting it
    // here would cancel that in-flight request.
    void queryClient.resetQueries({ predicate: (query) => !isCurrentUserQuery(query.queryKey) })
  }, [isAuthenticated, queryClient])
}
