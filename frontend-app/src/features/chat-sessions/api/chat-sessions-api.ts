import { configurationApiClient } from '@/lib/api-client'
import type { ApiError, Paginated } from '@/types/api'

import { SANDBOX_DISPLAY_NAME, SANDBOX_PHONE_NUMBER } from '../sandbox'
import type { ChatMessage, ChatSession, ChatSessionInput, CustomerMessageInput } from '../types'

// The backend waits up to 120 s for the local LLM, far longer than the client's 15 s default.
const CUSTOMER_MESSAGE_TIMEOUT_MS = 150_000

/** Your business's sessions (paginated), optionally only the one with `phoneNumber`. */
export async function listChatSessions(params: { page?: number; phoneNumber?: string } = {}) {
  const { data } = await configurationApiClient.get<Paginated<ChatSession>>('/chat/sessions/', {
    params: { page: params.page, phone_number: params.phoneNumber },
  })
  return data
}

export async function createChatSession(input: ChatSessionInput): Promise<ChatSession> {
  const { data } = await configurationApiClient.post<ChatSession>('/chat/sessions/', input)
  return data
}

/** Sends a message as the customer and returns the assistant's reply (public endpoint). */
export async function sendCustomerMessage(input: CustomerMessageInput): Promise<ChatMessage> {
  const { data } = await configurationApiClient.post<ChatMessage>('/chat/sessions/messages/', input, {
    timeout: CUSTOMER_MESSAGE_TIMEOUT_MS,
  })
  return data
}

async function findSessionByPhone(phoneNumber: string): Promise<ChatSession | null> {
  const { results } = await listChatSessions({ phoneNumber })
  return results[0] ?? null
}

/** The business's sandbox session, created on first use. */
export async function getOrCreateSandboxSession(): Promise<ChatSession> {
  const existing = await findSessionByPhone(SANDBOX_PHONE_NUMBER)
  if (existing) return existing
  try {
    return await createChatSession({ phone_number: SANDBOX_PHONE_NUMBER, display_name: SANDBOX_DISPLAY_NAME })
  } catch (error) {
    // Created in the meantime (e.g. in another tab): the number is now taken, so fetch it.
    const data = (error as ApiError).data as { phone_number?: unknown } | undefined
    if ((error as ApiError).status === 400 && data?.phone_number) {
      const session = await findSessionByPhone(SANDBOX_PHONE_NUMBER)
      if (session) return session
    }
    throw error
  }
}
