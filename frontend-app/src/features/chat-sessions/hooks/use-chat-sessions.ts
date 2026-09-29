import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import type { ApiError } from '@/types/api'

import { getOrCreateSandboxSession, sendCustomerMessage } from '../api/chat-sessions-api'
import { SANDBOX_PHONE_NUMBER } from '../sandbox'
import type { ChatMessage, ChatSession } from '../types'

export const chatSessionKeys = {
  all: ['chat-sessions'] as const,
  sandbox: (businessId: number) => [...chatSessionKeys.all, 'sandbox', businessId] as const,
}

/** The logged-in business's sandbox session (found, or created on first use). */
export function useSandboxSession(businessId: number) {
  return useQuery<ChatSession, ApiError>({
    queryKey: chatSessionKeys.sandbox(businessId),
    queryFn: getOrCreateSandboxSession,
  })
}

function appendMessage(session: ChatSession | undefined, message: ChatMessage) {
  return session && { ...session, chat_message_json: [...session.chat_message_json, message] }
}

/**
 * Sends a message as the sandbox customer. The message shows straight away, the reply is added
 * when it arrives, and afterwards the session is re-fetched so the screen matches the server
 * (which also keeps the customer's message if the LLM failed).
 */
export function useSendSandboxMessage(businessId: number) {
  const queryClient = useQueryClient()
  const queryKey = chatSessionKeys.sandbox(businessId)
  return useMutation<ChatMessage, ApiError, string>({
    mutationFn: (message) =>
      sendCustomerMessage({ business_id: businessId, phone_number: SANDBOX_PHONE_NUMBER, message }),
    onMutate: async (message) => {
      await queryClient.cancelQueries({ queryKey })
      queryClient.setQueryData<ChatSession>(queryKey, (session) =>
        appendMessage(session, { message, sent_by: 'customer', message_time: new Date().toISOString() }),
      )
    },
    onSuccess: (reply) => {
      queryClient.setQueryData<ChatSession>(queryKey, (session) => appendMessage(session, reply))
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey }),
  })
}
