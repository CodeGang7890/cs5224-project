// Public API of the auth feature.
export { LoginDialog } from './components/login-dialog'
export { RequireAuth } from './components/require-auth'
export { authKeys, useAuth, useCurrentUser } from './hooks/use-auth'
export { useResetQueriesOnAuthChange } from './hooks/use-reset-queries-on-auth-change'
export type { CurrentUser, LoginCredentials } from './types'
