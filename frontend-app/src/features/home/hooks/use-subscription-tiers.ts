import { useQuery } from "@tanstack/react-query";

import type { ApiError } from "@/types/api";

import { getSubscriptionTiers } from "../api/plans-api";
import type { SubscriptionTierInfo } from "../types";

export const planKeys = {
  all: ["subscription-tiers"] as const,
};

/** The plans the backend offers (they don't change while the app runs). */
export function useSubscriptionTiers() {
  return useQuery<SubscriptionTierInfo[], ApiError>({
    queryKey: planKeys.all,
    queryFn: getSubscriptionTiers,
    staleTime: Infinity,
  });
}
