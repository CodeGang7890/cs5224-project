import type { SubscriptionTier } from "@/features/auth";

/** One item of GET /api/auth/subscription-tiers/. */
export interface SubscriptionTierInfo {
  id: SubscriptionTier;
  name: string;
}
