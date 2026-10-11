import { configurationApiClient } from '@/lib/api-client'
import type { ApiError } from '@/types/api'

import type { WhatsAppConfiguration, WhatsAppConfigurationInput } from '../types'

// The backend always uses the logged-in user's business, so there's no ID in the URL.
const PATH = '/configuration/whatsapp/'

/** The business's WhatsApp connection, or `null` if it hasn't connected yet (404). */
export async function getWhatsAppConfiguration(): Promise<WhatsAppConfiguration | null> {
  try {
    const { data } = await configurationApiClient.get<WhatsAppConfiguration>(PATH)
    return data
  } catch (error) {
    if ((error as ApiError).status === 404) return null
    throw error
  }
}

/** Connects WhatsApp, or updates the connection (blank secrets are kept). */
export async function saveWhatsAppConfiguration(input: WhatsAppConfigurationInput): Promise<WhatsAppConfiguration> {
  const { data } = await configurationApiClient.put<WhatsAppConfiguration>(PATH, input)
  return data
}

export async function deleteWhatsAppConfiguration(): Promise<void> {
  await configurationApiClient.delete(PATH)
}
