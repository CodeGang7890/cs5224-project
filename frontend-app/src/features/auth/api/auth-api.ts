import { configurationApiClient } from "@/lib/api-client";
import type { AuthTokens } from "@/stores/auth-store";

import type { CurrentUser, LoginCredentials, SignUpInput } from "../types";

// Plain async functions that call the auth API (configuration-service /api/auth/).
// Token refresh is handled automatically by the API client, not here.

export async function login(
  credentials: LoginCredentials,
): Promise<AuthTokens> {
  const { data } = await configurationApiClient.post<AuthTokens>(
    "/auth/token/",
    credentials,
    {
      skipAuth: true,
    },
  );
  return data;
}

/** Creates an account and returns its tokens (it's logged in straight away). */
export async function signUp(input: SignUpInput): Promise<AuthTokens> {
  const { data } = await configurationApiClient.post<AuthTokens>(
    "/auth/signup/",
    input,
    { skipAuth: true },
  );
  return data;
}

/**
 * Exchanges an Identity Platform ID token (Google / Facebook, `@/lib/firebase`) for our tokens. The first
 * login creates the account (`created`).
 */
export async function loginWithFirebase(
  idToken: string,
): Promise<AuthTokens & { created: boolean }> {
  const { data } = await configurationApiClient.post<
    AuthTokens & { created: boolean }
  >("/auth/firebase/", { id_token: idToken }, { skipAuth: true });
  return data;
}

/** Revokes (blacklists) the refresh token on the server. */
export async function logout(refreshToken: string): Promise<void> {
  await configurationApiClient.post(
    "/auth/logout/",
    { refresh: refreshToken },
    { skipAuth: true },
  );
}

export async function getCurrentUser(): Promise<CurrentUser> {
  const { data } = await configurationApiClient.get<CurrentUser>("/auth/me/");
  return data;
}
