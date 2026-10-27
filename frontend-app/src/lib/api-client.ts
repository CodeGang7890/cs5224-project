import axios, { AxiosError, type AxiosInstance, type InternalAxiosRequestConfig } from 'axios'

import { env } from '@/config/env'
import { type AuthTokens, useAuthStore } from '@/stores/auth-store'
import type { ApiError } from '@/types/api'

declare module 'axios' {
  interface AxiosRequestConfig {
    /** Don't attach the access token or try to refresh it (login/refresh/logout calls). */
    skipAuth?: boolean
    /** Internal: set once a request has been retried after a token refresh. */
    _retriedAfterRefresh?: boolean
  }
}

// --- Token refresh --------------------------------------------------------------------

const REFRESH_PATH = '/auth/token/refresh/'

// Shared in-flight refresh, so a burst of 401s triggers only one refresh call.
let refreshPromise: Promise<string> | null = null

/** Exchanges the refresh token for new tokens (rotated) and returns the new access token. */
function refreshAccessToken(): Promise<string> {
  refreshPromise ??= (async () => {
    const { refreshToken, setTokens, clearTokens } = useAuthStore.getState()
    if (!refreshToken) throw new Error('Not logged in')
    try {
      // Bare axios: must not go through the interceptors below.
      const { data } = await axios.post<AuthTokens>(`${env.configurationServiceUrl}${REFRESH_PATH}`, {
        refresh: refreshToken,
      })
      setTokens(data)
      return data.access
    } catch (error) {
      // Refresh token expired or revoked: the session is over.
      clearTokens()
      throw error
    }
  })().finally(() => {
    refreshPromise = null
  })
  return refreshPromise
}

// --- Client factory -------------------------------------------------------------------

function toApiError(error: unknown): ApiError {
  if (!axios.isAxiosError(error)) {
    return { message: error instanceof Error ? error.message : 'Unexpected error' }
  }
  const data = (error as AxiosError<{ detail?: string; message?: string }>).response?.data
  return {
    // DRF puts error text in `detail`.
    message: data?.detail ?? data?.message ?? error.message ?? 'Unexpected error',
    status: error.response?.status,
    data,
  }
}

/**
 * Creates an Axios instance with the app's shared defaults, authentication and error handling:
 * - attaches `Authorization: Bearer <access token>` when logged in,
 * - on a 401, refreshes the tokens once and retries the request (logging out if that fails),
 * - normalises every error to `ApiError`.
 * Use the shared client in feature `api/` files.
 */
export function createApiClient(baseURL: string): AxiosInstance {
  const client = axios.create({
    baseURL,
    timeout: 15_000,
    headers: { 'Content-Type': 'application/json' },
  })

  client.interceptors.request.use((config) => {
    const { accessToken } = useAuthStore.getState()
    if (accessToken && !config.skipAuth && !config.headers.Authorization) {
      config.headers.Authorization = `Bearer ${accessToken}`
    }
    return config
  })

  client.interceptors.response.use(
    (response) => response,
    async (error: AxiosError) => {
      const config = error.config as InternalAxiosRequestConfig | undefined
      const canRefresh =
        error.response?.status === 401 &&
        config &&
        !config.skipAuth &&
        !config._retriedAfterRefresh &&
        useAuthStore.getState().refreshToken !== null

      if (canRefresh) {
        let accessToken: string
        try {
          accessToken = await refreshAccessToken()
        } catch {
          // Session expired (tokens are now cleared): report the original 401.
          return Promise.reject(toApiError(error))
        }
        config._retriedAfterRefresh = true
        config.headers.Authorization = `Bearer ${accessToken}`
        // Errors from the retry already pass through this interceptor, so they're ApiErrors.
        return client.request(config)
      }
      return Promise.reject(toApiError(error))
    },
  )

  return client
}

/** Client for configuration-service (Django). Paths are relative to its `/api` root. */
export const configurationApiClient = createApiClient(env.configurationServiceUrl)
