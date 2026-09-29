import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import type { ApiError } from '@/types/api'

import { getChatConfiguration, saveChatConfiguration } from '../api/chat-configuration-api'
import type { ChatConfiguration, ChatConfigurationInput } from '../types'

export const chatConfigurationKeys = {
  all: ['chat-configuration'] as const,
  detail: () => [...chatConfigurationKeys.all, 'detail'] as const,
}

/** `data` is `null` when the business has no chat configuration yet. */
export function useChatConfiguration() {
  return useQuery<ChatConfiguration | null, ApiError>({
    queryKey: chatConfigurationKeys.detail(),
    queryFn: getChatConfiguration,
  })
}

/** Saves the flow (PUT) and puts the saved configuration straight into the cache. */
export function useSaveChatConfiguration() {
  const queryClient = useQueryClient()
  return useMutation<ChatConfiguration, ApiError, ChatConfigurationInput>({
    mutationFn: saveChatConfiguration,
    onSuccess: (saved) => queryClient.setQueryData(chatConfigurationKeys.detail(), saved),
  })
}
