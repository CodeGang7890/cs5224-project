export interface LoginCredentials {
  username: string
  password: string
}

/** Response of GET /api/auth/me/ */
export interface CurrentUser {
  id: number
  username: string
  email: string
  first_name: string
  last_name: string
  /** ID of the BusinessConfiguration the account belongs to (null for e.g. the admin superuser). */
  business: number | null
  business_name: string | null
  is_staff: boolean
  is_superuser: boolean
}
