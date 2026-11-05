import { configurationApiClient } from "@/lib/api-client";

import type { SubscriptionTierInfo } from "../types";

/** GET /api/auth/subscription-tiers/: the plans, cheapest first (public, so no token is sent). */
export async function getSubscriptionTiers(): Promise<SubscriptionTierInfo[]> {
  const { data } = await configurationApiClient.get<SubscriptionTierInfo[]>(
    "/auth/subscription-tiers/",
    { skipAuth: true },
  );
  return data;
}
