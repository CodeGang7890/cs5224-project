/** Who sent a message, mirrored from configuration-service `chat_app/constants.py`. */
export type SentBy = 'customer' | 'business-manual' | 'business-automated'

/** One message of `ChatSession.chat_message_json`. */
export interface ChatMessage {
  message: string
  sent_by: SentBy
  /** ISO 8601 with a timezone. */
  message_time: string
}

/** A conversation between a business and one customer (`/api/chat/sessions/`). */
export interface ChatSession {
  id: number
  business: number
  phone_number: string
  display_name: string
  created_time: string
  last_chat_time: string
  /** Oldest message first. */
  chat_message_json: ChatMessage[]
  /** Block `id` in the business's chat configuration that the customer is at. */
  chat_state_id: number | string | null
}

/** Writable fields when creating a session; the backend sets everything else. */
export type ChatSessionInput = Pick<ChatSession, 'phone_number' | 'display_name'>

/** Body of POST /api/chat/sessions/messages/ (what a customer sends). */
export interface CustomerMessageInput {
  business_id: number
  phone_number: string
  message: string
}
