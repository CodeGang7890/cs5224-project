import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { productKeys } from "@/features/products";
import type { ApiError, DetailedPaginated } from "@/types/api";

import { completeOrder, getOrder, listOrders } from "../api/orders-api";
import type { Order, OrderListParams } from "../types";

export const orderKeys = {
  all: ["orders"] as const,
  list: (params: OrderListParams) =>
    [...orderKeys.all, "list", params] as const,
  detail: (id: number) => [...orderKeys.all, "detail", id] as const,
};

/** One page of orders (keeps showing the previous page while the next one loads). */
export function useOrders(params: OrderListParams) {
  return useQuery<DetailedPaginated<Order>, ApiError>({
    queryKey: orderKeys.list(params),
    queryFn: () => listOrders(params),
    placeholderData: keepPreviousData,
  });
}

/** One order, e.g. opened from a link while it isn't on the current page. */
export function useOrder(id: number | null, enabled = true) {
  return useQuery<Order, ApiError>({
    queryKey: orderKeys.detail(id ?? 0),
    queryFn: () => getOrder(id as number),
    enabled: enabled && id !== null,
  });
}

/** Payment received → completed. Its products move from on hold to sold, so they're refreshed too. */
export function useCompleteOrder() {
  const queryClient = useQueryClient();
  return useMutation<Order, ApiError, number>({
    mutationFn: completeOrder,
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: orderKeys.all }),
        queryClient.invalidateQueries({ queryKey: productKeys.all }),
      ]),
  });
}
