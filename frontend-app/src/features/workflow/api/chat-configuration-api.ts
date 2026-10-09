import { configurationApiClient } from '@/lib/api-client'

import type { ChatConfiguration, ChatConfigurationInput } from '../types'

// The backend always uses the logged-in user's business, so there's no ID in the URL.
const PATH = '/chat/configuration/'

/** The business's chat configuration (the defaults, with `id` null, if it hasn't saved one). */
export async function getChatConfiguration(): Promise<ChatConfiguration> {
  const { data } = await configurationApiClient.get<ChatConfiguration>(PATH)
  return data
}

/** Replaces `detail_fields` (the backend validates it). Creates the configuration if it doesn't exist. */
export async function saveChatConfiguration(input: ChatConfigurationInput): Promise<ChatConfiguration> {
  const { data } = await configurationApiClient.put<ChatConfiguration>(PATH, input)
  return data
}
