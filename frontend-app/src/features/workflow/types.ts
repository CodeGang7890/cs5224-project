/** Block types, mirrored from configuration-service `chat_app/constants.py`. */
export const BLOCK_TYPES = [
  'START_BLOCK',
  'PRODUCT_SELECTION_BLOCK',
  'DETAILS_COLLECTION_BLOCK',
  'CONFIRMATION_BLOCK',
] as const

export type BlockType = (typeof BLOCK_TYPES)[number]

export const START_BLOCK: BlockType = 'START_BLOCK'

/** Block types users can add. There's always exactly one START_BLOCK, which can't be added or deleted. */
export const ADDABLE_BLOCK_TYPES = BLOCK_TYPES.filter((type) => type !== START_BLOCK)

/** Block IDs are integers or non-blank strings (new blocks get UUIDs). */
export type BlockId = number | string

/** One block of the chat flow, as stored in `ChatConfiguration.config_json`. */
export interface ChatBlock {
  id: BlockId
  next_block_id: BlockId | null
  block_type: BlockType
  position_x: number
  position_y: number
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
