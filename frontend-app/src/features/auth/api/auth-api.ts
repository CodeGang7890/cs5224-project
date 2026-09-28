import { configurationApiClient } from '@/lib/api-client'
import type { AuthTokens } from '@/stores/auth-store'

import type { CurrentUser, LoginCredentials } from '../types'

// Plain async functions that call the auth API (configuration-service /api/auth/).
// Token refresh is handled automatically by the API client, not here.

export async function login(credentials: LoginCredentials): Promise<AuthTokens> {
  const { data } = await configurationApiClient.post<AuthTokens>('/auth/token/', credentials, {
    skipAuth: true,
  })
  return data
}

/** Revokes (blacklists) the refresh token on the server. */
export async function logout(refreshToken: string): Promise<void> {
  await configurationApiClient.post('/auth/logout/', { refresh: refreshToken }, { skipAuth: true })
}

export async function getCurrentUser(): Promise<CurrentUser> {
  const { data } = await configurationApiClient.get<CurrentUser>('/auth/me/')
  return data
}
