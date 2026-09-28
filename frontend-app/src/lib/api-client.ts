import axios, { AxiosError, type AxiosInstance } from 'axios'

import { env } from '@/config/env'
import type { ApiError } from '@/types/api'

/**
 * Creates an Axios instance with the app's shared defaults and error handling.
 * Create one client per backend service (see below) and use it in feature `api/` files.
 */
export function createApiClient(baseURL: string): AxiosInstance {
  const client = axios.create({
    baseURL,
    timeout: 15_000,
    headers: { 'Content-Type': 'application/json' },
  })

  client.interceptors.request.use((config) => {
    // Attach auth here once the app has authentication, e.g.:
    // const token = useAuthStore.getState().token
    // if (token) config.headers.Authorization = `Bearer ${token}`
    return config
  })

  client.interceptors.response.use(
    (response) => response,
    (error: AxiosError<{ detail?: string; message?: string }>) => {
      const apiError: ApiError = {
        // DRF puts error text in `detail`.
        message:
          error.response?.data?.detail ??
          error.response?.data?.message ??
          error.message ??
          'Unexpected error',
        status: error.response?.status,
        data: error.response?.data,
      }
      return Promise.reject(apiError)
    },
  )

  return client
}

/** Client for configuration-service (Django). */
export const configurationApiClient = createApiClient(env.configurationServiceUrl)
