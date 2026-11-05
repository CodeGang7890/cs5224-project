import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { LIVE_REFRESH_INTERVAL_MS } from "@/lib/live-refresh";
import type { ApiError, Paginated } from "@/types/api";

import { createFaq, deleteFaq, listFaqs, updateFaq } from "../api/faqs-api";
import type { Faq, FaqInput } from "../types";

export const FAQS_PAGE_SIZE = 20; // matches the backend's PAGE_SIZE

export const faqKeys = {
  all: ["faqs"] as const,
  list: (page: number) => [...faqKeys.all, "list", page] as const,
};

export function useFaqs(page: number) {
  return useQuery<Paginated<Faq>, ApiError>({
    queryKey: faqKeys.list(page),
    refetchInterval: LIVE_REFRESH_INTERVAL_MS,
    queryFn: () => listFaqs(page),
    placeholderData: keepPreviousData,
  });
}

export type SaveFaqVariables =
  | { id?: undefined; input: FaqInput }
  | { id: number; input: Partial<FaqInput> };

/** Creates (no `id`) or updates (with `id`) an FAQ, then refreshes the lists. */
export function useSaveFaq() {
  const queryClient = useQueryClient();
  return useMutation<Faq, ApiError, SaveFaqVariables>({
    mutationFn: ({ id, input }) =>
      id === undefined ? createFaq(input as FaqInput) : updateFaq(id, input),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: faqKeys.all }),
  });
}

export function useDeleteFaq() {
  const queryClient = useQueryClient();
  return useMutation<void, ApiError, number>({
    mutationFn: deleteFaq,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: faqKeys.all }),
  });
}
