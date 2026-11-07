import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { signInWithProvider, type SocialProvider } from "@/lib/firebase";
import {
  type AuthTokens,
  type LoginMethod,
  selectIsAuthenticated,
  useAuthStore,
} from "@/stores/auth-store";
import type { ApiError } from "@/types/api";

import {
  getCurrentUser,
  login,
  loginWithFirebase,
  logout,
  signUp,
} from "../api/auth-api";
import type { CurrentUser, LoginCredentials, SignUpInput } from "../types";

export const authKeys = {
  currentUser: ["auth", "current-user"] as const,
};

/** The logged-in user's profile (GET /api/auth/me/). Disabled while logged out. */
export function useCurrentUser() {
  const isAuthenticated = useAuthStore(selectIsAuthenticated);
  return useQuery<CurrentUser, ApiError>({
    queryKey: authKeys.currentUser,
    queryFn: getCurrentUser,
    enabled: isAuthenticated,
    staleTime: 5 * 60_000,
  });
}

/**
 * Everything components need for authentication:
 *
 *   const { isAuthenticated, user, login, signUp, loginWithProvider, logout } = useAuth()
 *
 * Requests don't need any auth code: every client from `createApiClient` attaches the
 * access token and refreshes it automatically. Cached data is reset whenever the user logs
 * in or out (see `useResetQueriesOnAuthChange`).
 */
export function useAuth() {
  const queryClient = useQueryClient();
  const isAuthenticated = useAuthStore(selectIsAuthenticated);
  const setTokens = useAuthStore((state) => state.setTokens);
  const clearTokens = useAuthStore((state) => state.clearTokens);
  const currentUser = useCurrentUser();

  // Stores the tokens and loads the profile before resolving, so the UI switches straight to the
  // logged-in state.
  const startSession = async (tokens: AuthTokens, method: LoginMethod) => {
    setTokens({ access: tokens.access, refresh: tokens.refresh }, method);
    await queryClient.fetchQuery({
      queryKey: authKeys.currentUser,
      queryFn: getCurrentUser,
    });
  };

  const loginMutation = useMutation<void, ApiError, LoginCredentials>({
    mutationFn: async (credentials) =>
      startSession(await login(credentials), "password"),
  });

  const signUpMutation = useMutation<void, ApiError, SignUpInput>({
    mutationFn: async (input) => startSession(await signUp(input), "password"),
  });

  // Google / Facebook: the popup (a `SocialLoginError` if cancelled or refused), then our tokens.
  // Must be called from the click, so the popup isn't blocked.
  const providerMutation = useMutation<void, ApiError | Error, SocialProvider>({
    mutationFn: async (provider) =>
      startSession(
        await loginWithFirebase(await signInWithProvider(provider)),
        provider,
      ),
  });

  const logoutMutation = useMutation<void, ApiError, void>({
    mutationFn: async () => {
      const { refreshToken } = useAuthStore.getState();
      clearTokens();
      // Best effort: revoke the refresh token server-side. Logging out locally never fails.
      if (refreshToken) await logout(refreshToken).catch(() => undefined);
    },
  });

  return {
    isAuthenticated,
    /** The logged-in user's profile, or undefined while logged out / loading. */
    user: isAuthenticated ? currentUser.data : undefined,
    isLoadingUser: isAuthenticated && currentUser.isPending,
    login: loginMutation.mutateAsync,
    isLoggingIn: loginMutation.isPending,
    loginError: loginMutation.error,
    signUp: signUpMutation.mutateAsync,
    isSigningUp: signUpMutation.isPending,
    signUpError: signUpMutation.error,
    loginWithProvider: providerMutation.mutateAsync,
    /** Which provider's login is in progress, if any. */
    pendingProvider: providerMutation.isPending
      ? providerMutation.variables
      : undefined,
    logout: () => logoutMutation.mutate(),
  };
}
