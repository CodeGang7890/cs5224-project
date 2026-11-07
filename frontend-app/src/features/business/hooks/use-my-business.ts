import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useCurrentUser } from "@/features/auth";
import type { ApiError } from "@/types/api";

import { getMyBusiness, saveMyBusiness } from "../api/business-api";
import type { Business, BusinessInput } from "../types";

export const businessKeys = {
  all: ["my-business"] as const,
  detail: () => [...businessKeys.all, "detail"] as const,
};

/** `data` is `null` while the account has no business. */
export function useMyBusiness(enabled = true) {
  return useQuery<Business | null, ApiError>({
    queryKey: businessKeys.detail(),
    queryFn: getMyBusiness,
    enabled,
  });
}

/**
 * Creates or updates the business. Creating one links the account to it, which changes what every other
 * request returns (403 → data), so all queries are refreshed, the current user (`business`) included.
 */
export function useSaveMyBusiness() {
  const queryClient = useQueryClient();
  return useMutation<Business, ApiError, BusinessInput>({
    mutationFn: saveMyBusiness,
    onSuccess: async (saved) => {
      queryClient.setQueryData(businessKeys.detail(), saved);
      await queryClient.invalidateQueries();
    },
  });
}

/**
 * Whether the logged-in user must create their business first: a new account (sign up, or a first
 * Google / Facebook login). Staff accounts (e.g. the admin superuser) never need one. Undefined while
 * the profile loads; false if it couldn't be loaded (the pages then show their own errors).
 */
export function useNeedsBusiness(): boolean | undefined {
  const { data: user, isError } = useCurrentUser();
  if (!user) return isError ? false : undefined;
  return user.business === null && !user.is_staff;
}
