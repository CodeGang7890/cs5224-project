import { configurationApiClient } from "@/lib/api-client";
import type { ApiError } from "@/types/api";

import type { Business, BusinessInput } from "../types";

// The backend always uses the logged-in user's business, so there's no ID in the URL.
const PATH = "/configuration/business/";

export async function savePaymentExpiry(minutes: number): Promise<Business> {
  const { data } = await configurationApiClient.patch<Business>(PATH, {
    payment_expiry_minutes: minutes,
  });
  return data;
}

/** The user's business, or `null` if the account has none yet (404). */
export async function getMyBusiness(): Promise<Business | null> {
  try {
    const { data } = await configurationApiClient.get<Business>(PATH);
    return data;
  } catch (error) {
    if ((error as ApiError).status === 404) return null;
    throw error;
  }
}

/** Creates the business (an account without one: it's linked to it) or updates it. */
export async function saveMyBusiness(input: BusinessInput): Promise<Business> {
  const { data } = await configurationApiClient.put<Business>(PATH, input);
  return data;
}
