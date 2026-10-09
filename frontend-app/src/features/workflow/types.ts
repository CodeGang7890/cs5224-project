/**
 * The chat flow's steps, mirrored from configuration-service `chat_app/constants.py`. The flow is
 * fixed: `ChatSession.chat_state_id` is one of these.
 */
export const CHAT_STEPS = ['start', 'product_selection', 'details_collection', 'confirmation'] as const

export type ChatStep = (typeof CHAT_STEPS)[number]

/** Types of customer detail, mirrored from configuration-service `chat_app/constants.py`. */
export const DETAIL_FIELD_TYPES = ['text', 'number', 'email', 'phone'] as const

export type DetailFieldType = (typeof DETAIL_FIELD_TYPES)[number]

/** One customer detail the Details collection step asks for (see `details.ts` for the rules). */
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
  last_updated: string | null
}

/** The only writable field. `id`, `business` and `last_updated` are read-only. */
export type ChatConfigurationInput = Pick<ChatConfiguration, 'detail_fields'>
