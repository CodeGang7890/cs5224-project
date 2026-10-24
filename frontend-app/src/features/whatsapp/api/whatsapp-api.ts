import { configurationApiClient } from "@/lib/api-client";
import type { ApiError } from "@/types/api";

import type { EmbeddedSignupInput, WhatsAppConfiguration } from "../types";

// The backend always uses the logged-in user's business, so there's no ID in the URL.
const PATH = "/configuration/whatsapp/";

/** The business's WhatsApp connection, or `null` if it hasn't connected yet (404). */
export async function getWhatsAppConfiguration(): Promise<WhatsAppConfiguration | null> {
  try {
    const { data } =
      await configurationApiClient.get<WhatsAppConfiguration>(PATH);
    return data;
  } catch (error) {
    if ((error as ApiError).status === 404) return null;
    throw error;
  }
}

// The backend makes several calls to Meta (exchange the code, check and register the number, set up
// the webhook), so allow more than the client's default timeout.
const EMBEDDED_SIGNUP_TIMEOUT_MS = 90_000;

/** Connects (or reconnects) with what the Embedded Signup popup returned. Send it at once: the code expires. */
export async function connectWithEmbeddedSignup(
  input: EmbeddedSignupInput,
): Promise<WhatsAppConfiguration> {
  const { data } = await configurationApiClient.post<WhatsAppConfiguration>(
    `${PATH}embedded-signup/`,
    input,
    {
      timeout: EMBEDDED_SIGNUP_TIMEOUT_MS,
    },
  );
  return data;
}

export async function deleteWhatsAppConfiguration(): Promise<void> {
  await configurationApiClient.delete(PATH);
}
