import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { selectIsAuthenticated, useAuthStore } from '@/stores/auth-store'
import type { ApiError } from '@/types/api'

import { getCurrentUser, login, logout } from '../api/auth-api'
import type { CurrentUser, LoginCredentials } from '../types'

export const authKeys = {
  currentUser: ['auth', 'current-user'] as const,
}

/** The logged-in user's profile (GET /api/auth/me/). Disabled while logged out. */
export function useCurrentUser() {
  const isAuthenticated = useAuthStore(selectIsAuthenticated)
  return useQuery<CurrentUser, ApiError>({
    queryKey: authKeys.currentUser,
    queryFn: getCurrentUser,
    enabled: isAuthenticated,
    staleTime: 5 * 60_000,
  })
}

/**
 * Everything components need for authentication:
 *
 *   const { isAuthenticated, user, login, logout } = useAuth()
 *
 * Requests don't need any auth code: every client from `createApiClient` attaches the
 * access token and refreshes it automatically. Cached data is reset whenever the user logs
 * in or out (see `useResetQueriesOnAuthChange`).
 */
export function useAuth() {
  const queryClient = useQueryClient()
  const isAuthenticated = useAuthStore(selectIsAuthenticated)
  const setTokens = useAuthStore((state) => state.setTokens)
  const clearTokens = useAuthStore((state) => state.clearTokens)
  const currentUser = useCurrentUser()

  const loginMutation = useMutation<void, ApiError, LoginCredentials>({
    mutationFn: async (credentials) => {
      setTokens(await login(credentials))
      // Load the profile before resolving, so the UI switches straight to the logged-in state.
      await queryClient.fetchQuery({ queryKey: authKeys.currentUser, queryFn: getCurrentUser })
    },
  })

  const logoutMutation = useMutation<void, ApiError, void>({
    mutationFn: async () => {
      const { refreshToken } = useAuthStore.getState()
      clearTokens()
      // Best effort: revoke the refresh token server-side. Logging out locally never fails.
      if (refreshToken) await logout(refreshToken).catch(() => undefined)
    },
  })

  return {
    isAuthenticated,
    /** The logged-in user's profile, or undefined while logged out / loading. */
    user: isAuthenticated ? currentUser.data : undefined,
    isLoadingUser: isAuthenticated && currentUser.isPending,
    login: loginMutation.mutateAsync,
    isLoggingIn: loginMutation.isPending,
    loginError: loginMutation.error,
    resetLoginError: loginMutation.reset,
    logout: () => logoutMutation.mutate(),
  }
}
