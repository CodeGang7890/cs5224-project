import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import type { ApiError } from '@/types/api'

import {
  deleteWhatsAppConfiguration,
  getWhatsAppConfiguration,
  saveWhatsAppConfiguration,
} from '../api/whatsapp-api'
import type { WhatsAppConfiguration, WhatsAppConfigurationInput } from '../types'

export const whatsAppKeys = {
  all: ['whatsapp-configuration'] as const,
  detail: () => [...whatsAppKeys.all, 'detail'] as const,
}

/** `data` is `null` when the business hasn't connected WhatsApp yet. */
export function useWhatsAppConfiguration(enabled = true) {
  return useQuery<WhatsAppConfiguration | null, ApiError>({
    queryKey: whatsAppKeys.detail(),
    queryFn: getWhatsAppConfiguration,
    enabled,
  })
}

/** Connects or updates (PUT) and puts the saved connection straight into the cache. */
export function useSaveWhatsAppConfiguration() {
  const queryClient = useQueryClient()
  return useMutation<WhatsAppConfiguration, ApiError, WhatsAppConfigurationInput>({
    mutationFn: saveWhatsAppConfiguration,
    onSuccess: (saved) => queryClient.setQueryData(whatsAppKeys.detail(), saved),
  })
}

export function useDeleteWhatsAppConfiguration() {
  const queryClient = useQueryClient()
  return useMutation<void, ApiError, void>({
    mutationFn: () => deleteWhatsAppConfiguration(),
    onSuccess: () => queryClient.setQueryData(whatsAppKeys.detail(), null),
  })
}
