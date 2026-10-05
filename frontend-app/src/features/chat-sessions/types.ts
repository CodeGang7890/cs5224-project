/** Who sent a message, mirrored from configuration-service `chat_app/constants.py`. */
export type SentBy = 'customer' | 'business-manual' | 'business-automated'

/** One message of `ChatSession.chat_message_json`. */
export interface ChatMessage {
  message: string
  sent_by: SentBy
  /** ISO 8601 with a timezone. */
  message_time: string
}

/** A product the customer chose; `name` and `unit_price` are a snapshot from when it was chosen. */
export interface ChatStateItem {
  product_id: number
  name: string
  /** Decimal string, e.g. "5.50". */
  unit_price: string
  quantity: number
}

/** `ChatSession.chat_state_data`: what the chat flow has collected so far. Every key is optional. */
export interface ChatStateData {
  items?: ChatStateItem[]
  /** Collected customer details by field key (the workflow's Details collection fields), e.g. `postal_code`. */
  details?: Record<string, string | number>
  /** True once the customer confirmed and the flow reached its last block. */
  completed?: boolean
  /** The order (Orders tab) placed when the customer confirmed. */
  order_id?: number
}

/** A conversation between a business and one customer, or a sandbox (test) chat. */
export interface ChatSession {
  id: number
  business: number
  /** Empty for sandbox sessions without a mock number. */
  phone_number: string
  display_name: string
  created_time: string
  last_chat_time: string
  /** Oldest message first. */
  chat_message_json: ChatMessage[]
  /** Block `id` in the business's chat configuration that the customer is at. */
  chat_state_id: number | string | null
  chat_state_data: ChatStateData
  /** A test chat from the Chat Sandbox rather than a real customer. */
  is_sandbox: boolean
}

/** One block's extraction + deterministic check in a turn of the backend's chat flow. */
export interface FlowStepDebug {
  block_id: number | string
  block_type: string
  /** The extraction system prompt sent to the LLM. */
  system_prompt: string
  /** The LLM's JSON answer, before the checks. */
  extracted: Record<string, unknown>
  complete: boolean
  go_back: boolean
  missing: string[]
  issues: string[]
  /** `chat_state_data` after this step's check. */
  chat_state_data: ChatStateData
}

/** What happened inside one sandbox message's turn (not stored; only in the send response). */
export interface SandboxTurnDebug {
  before: { chat_state_id: ChatSession['chat_state_id']; chat_state_data: ChatStateData }
  after: { chat_state_id: ChatSession['chat_state_id']; block_type?: string; chat_state_data: ChatStateData }
  steps: FlowStepDebug[]
  stop_reason: string
  finished: string[]
  /** `chat_state_data.order_id` after the turn (placed now or earlier), or null. */
  order_id: number | null
  missing: string[]
  issues: string[]
  reply_system_prompt: string
  tool_calls: { name: string; arguments: Record<string, unknown> }[]
}

/** Response of POST /api/chat/sandbox-sessions/{id}/messages/: the reply, plus debug info. */
export interface SandboxMessageReply extends ChatMessage {
  debug: SandboxTurnDebug
}

/** Body of POST /api/chat/sandbox-sessions/ (both optional); the backend sets everything else. */
export type SandboxChatSessionInput = Partial<Pick<ChatSession, 'display_name' | 'phone_number'>>

/** Which sessions to list: real customer chats (default), both, or sandbox chats only. */
export type SandboxFilter = 'exclude' | 'include' | 'only'

/** Sort options of GET /api/chat/sessions/ (`ordering`). */
export type ChatSessionOrdering =
  | '-last_chat_time'
  | 'last_chat_time'
  | '-created_time'
  | 'created_time'
  | 'display_name'
  | '-display_name'
  | 'phone_number'

/** Query parameters of GET /api/chat/sessions/ (all optional except paging and sorting). */
export interface ChatSessionListParams {
  page: number
  page_size: number
  ordering: ChatSessionOrdering
  sandbox: SandboxFilter
  search?: string
  chat_state_id?: string
  has_messages?: 'true' | 'false'
  /** ISO 8601 date-times (inclusive). */
  last_chat_time_after?: string
  last_chat_time_before?: string
  created_time_after?: string
  created_time_before?: string
}
