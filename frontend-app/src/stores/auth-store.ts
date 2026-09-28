import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export interface AuthTokens {
  access: string
  refresh: string
}

interface AuthState {
  accessToken: string | null
  refreshToken: string | null
  setTokens: (tokens: AuthTokens) => void
  clearTokens: () => void
}

const STORAGE_KEY = 'auth'

/**
 * JWT access/refresh tokens, persisted to localStorage so a login survives page reloads.
 * Don't read tokens in components: `@/lib/api-client` attaches and refreshes them, and
 * `useAuth()` (`@/features/auth`) is the component-facing API.
 */
export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      accessToken: null,
      refreshToken: null,
      setTokens: ({ access, refresh }) => set({ accessToken: access, refreshToken: refresh }),
      clearTokens: () => set({ accessToken: null, refreshToken: null }),
    }),
    { name: STORAGE_KEY },
  ),
)

/** Logged in = we hold a refresh token (the access token may be expired and get refreshed). */
export const selectIsAuthenticated = (state: AuthState) => state.refreshToken !== null

// Keep tabs in sync: logging in/out (or a token refresh) in one tab updates the others.
if (typeof window !== 'undefined') {
  window.addEventListener('storage', (event) => {
    if (event.key === STORAGE_KEY) void useAuthStore.persist.rehydrate()
  })
}
