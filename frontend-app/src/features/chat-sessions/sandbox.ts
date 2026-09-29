import type { ApiError } from '@/types/api'

import type { ChatSession } from './types'

/** Backend limit for one message (`CHAT_MESSAGE_MAX_LENGTH`). */
export const CHAT_MESSAGE_MAX_LENGTH = 4096

/** Creating a session returns 400 `non_field_errors` when the business has no chat configuration. */
export function isMissingChatConfiguration(error: ApiError): boolean {
  const data = error.data as { non_field_errors?: unknown } | undefined
  return error.status === 400 && Array.isArray(data?.non_field_errors)
}

/** What to call a session in the UI. */
export function sessionLabel(session: ChatSession): string {
  return session.display_name || session.phone_number || `Sandbox chat #${session.id}`
}

const TEST_CHAT_NAME = /^Test chat (\d+)$/

/** Name for a new sandbox chat: "Test chat N", one more than the highest N so far. */
export function nextSandboxChatName(sessions: ChatSession[]): string {
  const highest = Math.max(0, ...sessions.map((s) => Number(TEST_CHAT_NAME.exec(s.display_name)?.[1] ?? 0)))
  return `Test chat ${highest + 1}`
}
