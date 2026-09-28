/** Normalised error shape thrown by the API client for every failed request. */
export interface ApiError {
  message: string
  status?: number
  data?: unknown
}
