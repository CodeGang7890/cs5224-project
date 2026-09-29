/** Who sent a message, mirrored from configuration-service `chat_app/constants.py`. */
export type SentBy = 'customer' | 'business-manual' | 'business-automated'

/** One message of `ChatSession.chat_message_json`. */
export interface ChatMessage {
  message: string
  sent_by: SentBy
  /** ISO 8601 with a timezone. */
  message_time: string
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
  /** A test chat from the Chat Sandbox rather than a real customer. */
  is_sandbox: boolean
}

/** Body of POST /api/chat/sandbox-sessions/ (both optional); the backend sets everything else. */
export type SandboxChatSessionInput = Partial<Pick<ChatSession, 'display_name' | 'phone_number'>>
