import type { ApiError } from '@/types/api'

// The Chat Sandbox pretends to be a customer with this mock phone number. It must pass the
// backend's phone validation (international format: "+", a country code not starting with 0,
// 7–15 digits), which rules out "000"; "+1" followed by zeros is clearly fake but valid.
export const SANDBOX_PHONE_NUMBER = '+10000000000'
export const SANDBOX_DISPLAY_NAME = 'sandbox_user'

/** Backend limit for one message (`CHAT_MESSAGE_MAX_LENGTH`). */
export const CHAT_MESSAGE_MAX_LENGTH = 4096

/** The create-session API returns 400 `non_field_errors` when the business has no chat configuration. */
export function isMissingChatConfiguration(error: ApiError): boolean {
  const data = error.data as { non_field_errors?: unknown } | undefined
  return error.status === 400 && Array.isArray(data?.non_field_errors)
}
