/** Block types, mirrored from configuration-service `chat_app/constants.py`. */
export const BLOCK_TYPES = [
  'START_BLOCK',
  'PRODUCT_SELECTION_BLOCK',
  'DETAILS_COLLECTION_BLOCK',
  'CONFIRMATION_BLOCK',
  'SEND_MESSAGE_BLOCK',
] as const

export type BlockType = (typeof BLOCK_TYPES)[number]

export const START_BLOCK: BlockType = 'START_BLOCK'

/** Block types users can add. There's always exactly one START_BLOCK, which can't be added or deleted. */
export const ADDABLE_BLOCK_TYPES = BLOCK_TYPES.filter((type) => type !== START_BLOCK)

/** Block IDs are integers or non-blank strings (new blocks get UUIDs). */
export type BlockId = number | string

export const DETAILS_COLLECTION_BLOCK: BlockType = 'DETAILS_COLLECTION_BLOCK'
/** Sends its fixed `message` to the customer, then the chat moves straight on to the next block. */
export const SEND_MESSAGE_BLOCK: BlockType = 'SEND_MESSAGE_BLOCK'

/** Types of customer detail, mirrored from configuration-service `chat_app/constants.py`. */
export const DETAIL_FIELD_TYPES = ['text', 'number', 'email', 'phone'] as const

export type DetailFieldType = (typeof DETAIL_FIELD_TYPES)[number]

/** One customer detail a DETAILS_COLLECTION_BLOCK asks for (see `details.ts` for the rules). */
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

/** One block of the chat flow, as stored in `ChatConfiguration.config_json`. */
export interface ChatBlock {
  id: BlockId
  next_block_id: BlockId | null
  block_type: BlockType
  position_x: number
  position_y: number
  /** DETAILS_COLLECTION_BLOCK only; without it, the block asks for the default name and email. */
  fields?: DetailField[]
  /** SEND_MESSAGE_BLOCK only, and required there: the message it sends the customer. */
  message?: string
}

/** A business's chat configuration (`/api/chat/configuration/`). Each business has at most one. */
export interface ChatConfiguration {
  id: number
  business: number
  config_json: ChatBlock[]
  last_updated: string
}

/** The only writable field. `id`, `business` and `last_updated` are read-only. */
export type ChatConfigurationInput = Pick<ChatConfiguration, 'config_json'>
