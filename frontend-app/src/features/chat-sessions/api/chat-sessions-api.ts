import { configurationApiClient, messagingApiClient } from '@/lib/api-client'
import type { DetailedPaginated, Paginated } from '@/types/api'

import type { ChatSession, ChatSessionListParams, SandboxChatSessionInput, SandboxMessageReply } from '../types'

/** The logged-in business's chat sessions, filtered, sorted and paginated by the backend. */
export async function listChatSessions(params: ChatSessionListParams): Promise<DetailedPaginated<ChatSession>> {
  const { data } = await configurationApiClient.get<DetailedPaginated<ChatSession>>('/chat/sessions/', { params })
  return data
}

// Sandbox (test) chat sessions of the logged-in user's business.

// The backend's chat flow makes several calls to the local LLM per message (the router, one per
// order step it passes, maybe the question check, plus the reply), far longer than the client's 15 s default.
const SEND_MESSAGE_TIMEOUT_MS = 300_000

export async function listSandboxSessions(page: number): Promise<Paginated<ChatSession>> {
  const { data } = await configurationApiClient.get<Paginated<ChatSession>>('/chat/sandbox-sessions/', {
    params: { page },
  })
  return data
}

export async function createSandboxSession(input: SandboxChatSessionInput): Promise<ChatSession> {
  const { data } = await configurationApiClient.post<ChatSession>('/chat/sandbox-sessions/', input)
  return data
}

export async function deleteSandboxSession(id: number): Promise<void> {
  await configurationApiClient.delete(`/chat/sandbox-sessions/${id}/`)
}

/**
 * Sends a message as the pretend customer and returns the assistant's reply (with debug info).
 * The chat flow runs in messaging-service; everything else about chats stays in configuration-service.
 */
export async function sendSandboxMessage(id: number, message: string): Promise<SandboxMessageReply> {
  const { data } = await messagingApiClient.post<SandboxMessageReply>(
    `/chat/sandbox-sessions/${id}/messages/`,
    { message },
    { timeout: SEND_MESSAGE_TIMEOUT_MS },
  )
  return data
}
