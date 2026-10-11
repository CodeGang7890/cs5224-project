/**
 * The chat flow's steps, mirrored from configuration-service `chat_app/constants.py`. The flow is
 * fixed: `ChatSession.chat_state_id` is one of these.
 */
export const CHAT_STEPS = [
  'start',
  'product_selection',
  'details_collection',
  'confirmation',
  'service_selection',
  'slot_selection',
  'booking_details',
  'booking_confirmation',
] as const

export type ChatStep = (typeof CHAT_STEPS)[number]

/** Types of customer detail, mirrored from configuration-service `chat_app/constants.py`. */
export const DETAIL_FIELD_TYPES = ['text', 'number', 'email', 'phone'] as const

export type DetailFieldType = (typeof DETAIL_FIELD_TYPES)[number]

/** One customer detail the Details collection (and Booking details) step asks for (see `details.ts` for the rules). */
export interface DetailField {
  /** e.g. `postal_code`: the key in `ChatSession.chat_state_data.details`. */
  key: string
  label: string
  type: DetailFieldType
  /** Optional hint for the assistant, e.g. "6 digits". */
  description?: string
  /** False for an optional detail (asked for, but not needed to move on). Missing means required. */
  required?: boolean
  /** `text` only. */
  max_length?: number
  /** `number` only. */
  min_value?: number
  max_value?: number
}

/**
 * A business's chat configuration (`/api/chat/configuration/`): the settings of the fixed chat
 * flow's steps. Until the business saves one, the API returns the defaults with `id` and
 * `last_updated` null.
 */
export interface ChatConfiguration {
  id: number | null
  business: number
  /** The customer details the Details collection step asks for. */
  detail_fields: DetailField[]
  /** Sent word for word as the reply to a chat's first message; '' = none. May use {business_name}. */
  welcome_message: string
  /** How the assistant writes its replies (see `GET /api/chat/configuration/reply-styles/`). */
  reply_style: ReplyStyleKey
  /** With reply_style "custom": the business's own description of the style. */
  custom_style: string
  last_updated: string | null
}

/** The writable fields. `id`, `business` and `last_updated` are read-only. */
export type ChatConfigurationInput = Pick<ChatConfiguration, 'detail_fields' | 'welcome_message' | 'reply_style' | 'custom_style'>

/** Reply styles, mirrored from configuration-service `chat_app/constants.py` `REPLY_STYLES`. */
export const REPLY_STYLE_KEYS = ['friendly', 'professional', 'casual', 'brief', 'custom'] as const
export type ReplyStyleKey = (typeof REPLY_STYLE_KEYS)[number]

/** One reply style (`GET /api/chat/configuration/reply-styles/`). */
export interface ReplyStyle {
  key: ReplyStyleKey
  label: string
  description: string
  /** What the assistant is told; null for "custom" (custom_style is used). */
  instructions: string | null
}
