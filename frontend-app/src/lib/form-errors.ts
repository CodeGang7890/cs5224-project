import type { ApiError } from '@/types/api'

export interface FormErrors {
  /** Per-field messages, keyed by API field name. */
  fields: Record<string, string>
  /** Errors not tied to one field (e.g. uniqueness, 403, network). */
  form?: string
}

/**
 * Converts an API error into form errors. DRF validation errors (400) look like
 * `{ field: ["message", ...], non_field_errors: [...] }`; anything else becomes a form error.
 */
export function getFormErrors(error: ApiError): FormErrors {
  const data = error.data
  if (error.status === 400 && data && typeof data === 'object' && !Array.isArray(data)) {
    const fields: Record<string, string> = {}
    let form: string | undefined
    for (const [key, value] of Object.entries(data as Record<string, unknown>)) {
      const message = Array.isArray(value) ? value.map(String).join(' ') : String(value)
      if (key === 'non_field_errors' || key === 'detail') form = message
      else fields[key] = message
    }
    return { fields, form }
  }
  if (error.status === undefined) return { fields: {}, form: "Couldn't reach the server. Please try again." }
  return { fields: {}, form: error.message }
}
