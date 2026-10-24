// Public API of the auth feature.
export { AuthDialog } from "./components/auth-dialog";
export { RequireAuth } from "./components/require-auth";
export { authKeys, useAuth, useCurrentUser } from "./hooks/use-auth";
export { useResetQueriesOnAuthChange } from "./hooks/use-reset-queries-on-auth-change";
export type { CurrentUser, LoginCredentials, SignUpInput } from "./types";
