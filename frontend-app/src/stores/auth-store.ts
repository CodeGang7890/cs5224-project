import { create } from "zustand";
import { persist } from "zustand/middleware";

export interface AuthTokens {
  access: string;
  refresh: string;
}

/** How this session logged in (shown in the profile; the backend doesn't record it). */
export type LoginMethod = "password" | "google" | "facebook";

interface AuthState {
  accessToken: string | null;
  refreshToken: string | null;
  /** Null for a session from before this was tracked. */
  loginMethod: LoginMethod | null;
  /** `loginMethod` is set when logging in; a token refresh leaves it out and keeps it. */
  setTokens: (tokens: AuthTokens, loginMethod?: LoginMethod) => void;
  clearTokens: () => void;
}

const STORAGE_KEY = "auth";

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
      loginMethod: null,
      setTokens: ({ access, refresh }, loginMethod) =>
        set((state) => ({
          accessToken: access,
          refreshToken: refresh,
          loginMethod: loginMethod ?? state.loginMethod,
        })),
      clearTokens: () =>
        set({ accessToken: null, refreshToken: null, loginMethod: null }),
    }),
    { name: STORAGE_KEY },
  ),
);

/** Logged in = we hold a refresh token (the access token may be expired and get refreshed). */
export const selectIsAuthenticated = (state: AuthState) =>
  state.refreshToken !== null;

// Keep tabs in sync: logging in/out (or a token refresh) in one tab updates the others.
if (typeof window !== "undefined") {
  window.addEventListener("storage", (event) => {
    if (event.key === STORAGE_KEY) void useAuthStore.persist.rehydrate();
  });
}
