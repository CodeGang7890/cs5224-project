import { configurationApiClient } from "@/lib/api-client";

import type {
  ChatConfiguration,
  ChatConfigurationInput,
  ReplyStyle,
} from "../types";

// The backend always uses the logged-in user's business, so there's no ID in the URL.
const PATH = "/chat/configuration/";

/** The business's chat configuration (the defaults, with `id` null, if it hasn't saved one). */
export async function getChatConfiguration(): Promise<ChatConfiguration> {
  const { data } = await configurationApiClient.get<ChatConfiguration>(PATH);
  return data;
}

/** Replaces the settings (the backend validates them). Creates the configuration if it doesn't exist. */
export async function saveChatConfiguration(
  input: ChatConfigurationInput,
): Promise<ChatConfiguration> {
  const { data } = await configurationApiClient.put<ChatConfiguration>(
    PATH,
    input,
  );
  return data;
}

/** The reply styles a business can choose (the presets, then "custom"). */
export async function getReplyStyles(): Promise<ReplyStyle[]> {
  const { data } = await configurationApiClient.get<ReplyStyle[]>(
    `${PATH}reply-styles/`,
  );
  return data;
}
