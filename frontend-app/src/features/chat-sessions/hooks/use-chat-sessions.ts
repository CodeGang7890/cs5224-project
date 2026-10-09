import {
  keepPreviousData,
  useInfiniteQuery,
  useIsMutating,
  useMutation,
  useQuery,
  useQueryClient,
  type InfiniteData,
  type QueryClient,
} from '@tanstack/react-query'

import { orderKeys, scheduleKeys } from '@/features/orders'
import { productKeys } from '@/features/products'
import { availabilityKeys } from '@/features/services'
import type { ApiError, DetailedPaginated, Paginated } from '@/types/api'

import {
  createSandboxSession,
  deleteSandboxSession,
  listChatSessions,
  listSandboxSessions,
  sendSandboxMessage,
} from '../api/chat-sessions-api'
import type {
  ChatMessage,
  ChatSession,
  ChatSessionListParams,
  SandboxChatSessionInput,
  SandboxMessageReply,
  SandboxTurnDebug,
} from '../types'

export const chatSessionKeys = {
  all: ['chat-sessions'] as const,
  list: (params: ChatSessionListParams) => [...chatSessionKeys.all, 'list', params] as const,
  sandboxList: () => [...chatSessionKeys.all, 'sandbox', 'list'] as const,
  sendSandboxMessage: (sessionId: number) => [...chatSessionKeys.all, 'sandbox', 'send', sessionId] as const,
  /** Debug info of a session's latest turn: only ever set from send responses, never fetched. */
  sandboxTurnDebug: (sessionId: number) => [...chatSessionKeys.all, 'sandbox', 'debug', sessionId] as const,
}

/** One page of chat sessions for the Chats tab (keeps showing the previous page while loading). */
export function useChatSessions(params: ChatSessionListParams) {
  return useQuery<DetailedPaginated<ChatSession>, ApiError>({
    queryKey: chatSessionKeys.list(params),
    queryFn: () => listChatSessions(params),
    placeholderData: keepPreviousData,
  })
}

type SessionPages = InfiniteData<Paginated<ChatSession>, number>

/** Sandbox sessions, most recent chat first, 20 per page ("load more" via `fetchNextPage`). */
export function useSandboxSessions() {
  return useInfiniteQuery<Paginated<ChatSession>, ApiError, SessionPages, readonly unknown[], number>({
    queryKey: chatSessionKeys.sandboxList(),
    queryFn: ({ pageParam }) => listSandboxSessions(pageParam),
    initialPageParam: 1,
    getNextPageParam: (lastPage, _pages, lastPageParam) => (lastPage.next ? lastPageParam + 1 : undefined),
  })
}

/** Applies `update` to one session in the cached list. */
function updateCachedSession(queryClient: QueryClient, id: number, update: (session: ChatSession) => ChatSession) {
  queryClient.setQueryData<SessionPages>(chatSessionKeys.sandboxList(), (data) =>
    data && {
      ...data,
      pages: data.pages.map((page) => ({
        ...page,
        results: page.results.map((session) => (session.id === id ? update(session) : session)),
      })),
    },
  )
}

function withMessage(session: ChatSession, message: ChatMessage): ChatSession {
  return {
    ...session,
    chat_message_json: [...session.chat_message_json, message],
    last_chat_time: message.message_time,
  }
}

export function useCreateSandboxSession() {
  const queryClient = useQueryClient()
  return useMutation<ChatSession, ApiError, SandboxChatSessionInput>({
    mutationFn: createSandboxSession,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: chatSessionKeys.sandboxList() }),
  })
}

export function useDeleteSandboxSession() {
  const queryClient = useQueryClient()
  return useMutation<void, ApiError, number>({
    mutationFn: deleteSandboxSession,
    onSuccess: (_data, id) => {
      // Drop it from the screen straight away, then re-sync the pages.
      queryClient.setQueryData<SessionPages>(chatSessionKeys.sandboxList(), (data) =>
        data && {
          ...data,
          pages: data.pages.map((page) => ({ ...page, results: page.results.filter((s) => s.id !== id) })),
        },
      )
      return queryClient.invalidateQueries({ queryKey: chatSessionKeys.sandboxList() })
    },
  })
}

/**
 * Sends a message in one sandbox session. The message shows straight away, the reply is added
 * when it arrives, and afterwards the list is re-fetched so the screen matches the server (which
 * also keeps the message if the LLM failed). The callbacks live on the mutation, so they still
 * run if you switch to another chat while waiting.
 */
export function useSendSandboxMessage(sessionId: number) {
  const queryClient = useQueryClient()
  return useMutation<SandboxMessageReply, ApiError, string>({
    mutationKey: chatSessionKeys.sendSandboxMessage(sessionId),
    mutationFn: (message) => sendSandboxMessage(sessionId, message),
    onMutate: async (message) => {
      await queryClient.cancelQueries({ queryKey: chatSessionKeys.sandboxList() })
      updateCachedSession(queryClient, sessionId, (session) =>
        withMessage(session, { message, sent_by: 'customer', message_time: new Date().toISOString() }),
      )
    },
    onSuccess: ({ debug, ...reply }) => {
      // Keep it until the page reloads, even while no debug panel is showing it.
      queryClient.setQueryDefaults(chatSessionKeys.sandboxTurnDebug(sessionId), { gcTime: Infinity })
      queryClient.setQueryData(chatSessionKeys.sandboxTurnDebug(sessionId), debug)
      updateCachedSession(queryClient, sessionId, (session) => withMessage(session, reply))
      // Confirming placed an order: it's a new order, and its products' stock changed.
      if (debug.order_id !== null) {
        void queryClient.invalidateQueries({ queryKey: orderKeys.all })
        void queryClient.invalidateQueries({ queryKey: productKeys.all })
      }
      // Confirming made a booking: a new booking, and the calendars changed.
      if (debug.booking_id !== null) {
        void queryClient.invalidateQueries({ queryKey: scheduleKeys.all })
        void queryClient.invalidateQueries({ queryKey: availabilityKeys.all })
      }
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: chatSessionKeys.sandboxList() }),
  })
}

/**
 * What happened inside this session's latest turn (from the last send response), or undefined
 * before any message was sent since the page loaded. It isn't stored on the backend.
 */
export function useSandboxTurnDebug(sessionId: number) {
  return useQuery<SandboxTurnDebug | null>({
    queryKey: chatSessionKeys.sandboxTurnDebug(sessionId),
    queryFn: () => null, // never runs (enabled: false): the data only comes from setQueryData
    enabled: false,
    staleTime: Infinity,
  }).data
}

/** Whether a message in this session is waiting for its reply (works across remounts). */
export function useIsSendingSandboxMessage(sessionId: number): boolean {
  return useIsMutating({ mutationKey: chatSessionKeys.sendSandboxMessage(sessionId) }) > 0
}
