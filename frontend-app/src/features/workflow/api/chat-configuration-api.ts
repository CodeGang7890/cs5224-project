import { configurationApiClient } from '@/lib/api-client'
import type { ApiError } from '@/types/api'

import type { ChatConfiguration, ChatConfigurationInput } from '../types'

// The backend always uses the logged-in user's business, so there's no ID in the URL.
const PATH = '/chat/configuration/'

/** The business's chat configuration, or `null` if it hasn't saved one yet (404). */
export async function getChatConfiguration(): Promise<ChatConfiguration | null> {
  try {
    const { data } = await configurationApiClient.get<ChatConfiguration>(PATH)
    return data
  } catch (error) {
    if ((error as ApiError).status === 404) return null
    throw error
  }
}

/** Replaces `config_json` (the backend validates it). Creates the configuration if it doesn't exist. */
export async function saveChatConfiguration(input: ChatConfigurationInput): Promise<ChatConfiguration> {
  const { data } = await configurationApiClient.put<ChatConfiguration>(PATH, input)
  return data
}
