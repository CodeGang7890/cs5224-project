import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import type { ApiError, DetailedPaginated } from "@/types/api";

import {
  completeSchedule,
  getSchedule,
  listSchedules,
} from "../api/schedules-api";
import type { ScheduleItem, ScheduleListParams } from "../types";

export const scheduleKeys = {
  all: ["schedules"] as const,
  list: (params: ScheduleListParams) =>
    [...scheduleKeys.all, "list", params] as const,
  detail: (id: number) => [...scheduleKeys.all, "detail", id] as const,
};

/** One page of bookings (keeps showing the previous page while the next one loads). */
export function useSchedules(params: ScheduleListParams) {
  return useQuery<DetailedPaginated<ScheduleItem>, ApiError>({
    queryKey: scheduleKeys.list(params),
    queryFn: () => listSchedules(params),
    placeholderData: keepPreviousData,
  });
}

/** One booking, e.g. opened from a link while it isn't on the current page. */
export function useSchedule(id: number | null, enabled = true) {
  return useQuery<ScheduleItem, ApiError>({
    queryKey: scheduleKeys.detail(id ?? 0),
    queryFn: () => getSchedule(id as number),
    enabled: enabled && id !== null,
  });
}

/**
 * Payment received → completed. The schedules' calendars show each booking's status, so they're
 * refreshed too (`providerKeys.all` of `@/features/services`, by its key: that feature imports this one).
 */
export function useCompleteSchedule() {
  const queryClient = useQueryClient();
  return useMutation<ScheduleItem, ApiError, number>({
    mutationFn: completeSchedule,
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: scheduleKeys.all }),
        queryClient.invalidateQueries({ queryKey: ["service-providers"] }),
      ]),
  });
}
