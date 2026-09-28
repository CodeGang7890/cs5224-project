import axios, { AxiosError } from 'axios'

import { env } from '@/config/env'
import type { ApiError } from '@/types/api'

/**
 * Shared Axios instance. All HTTP calls go through this client so that
 * base URL, headers, auth and error handling are configured in one place.
 */
export const apiClient = axios.create({
  baseURL: env.apiBaseUrl,
  timeout: 15_000,
  headers: { 'Content-Type': 'application/json' },
})

apiClient.interceptors.request.use((config) => {
  // Attach auth here once the app has authentication, e.g.:
  // const token = useAuthStore.getState().token
  // if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError<{ message?: string }>) => {
    const apiError: ApiError = {
      message: error.response?.data?.message ?? error.message ?? 'Unexpected error',
      status: error.response?.status,
      data: error.response?.data,
    }
    return Promise.reject(apiError)
  },
)
