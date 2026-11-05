import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { LIVE_REFRESH_INTERVAL_MS } from "@/lib/live-refresh";
import type { ApiError, Paginated } from "@/types/api";

import {
  copyWeek,
  createProvider,
  createService,
  deleteProvider,
  deleteService,
  getWeekCalendar,
  listProviders,
  listServices,
  saveWeek,
  setSlots,
  updateProvider,
  updateService,
} from "../api/services-api";
import type {
  CopyWeekInput,
  Service,
  ServiceInput,
  ServiceProvider,
  ServiceProviderInput,
  SetSlotsInput,
  WeekCalendar,
  WeeklyAvailability,
  WeeksChange,
} from "../types";

export const SERVICES_PAGE_SIZE = 20; // matches the backend's PAGE_SIZE

export const serviceKeys = {
  all: ["services"] as const,
  list: (page: number) => [...serviceKeys.all, "list", page] as const,
  hasBookable: () => [...serviceKeys.all, "has-bookable"] as const,
};

// Providers list which services they do, and services list their providers, so changing either
// refreshes both. Calendars live here too: bookings and slot changes refresh them.
export const providerKeys = {
  all: ["service-providers"] as const,
  list: () => [...providerKeys.all, "list"] as const,
  calendars: () => [...providerKeys.all, "calendar"] as const,
  calendar: (id: number, week: string) =>
    [...providerKeys.calendars(), id, week] as const,
};

function useInvalidateBoth() {
  const queryClient = useQueryClient();
  return () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: serviceKeys.all }),
      queryClient.invalidateQueries({ queryKey: providerKeys.all }),
    ]);
}

export function useServices(page: number) {
  return useQuery<Paginated<Service>, ApiError>({
    queryKey: serviceKeys.list(page),
    refetchInterval: LIVE_REFRESH_INTERVAL_MS,
    queryFn: () => listServices(page),
    placeholderData: keepPreviousData,
  });
}

export type SaveServiceVariables =
  | { id?: undefined; input: ServiceInput }
  | { id: number; input: Partial<ServiceInput> };

/** Creates (no `id`) or updates (with `id`) a service. */
export function useSaveService() {
  const invalidate = useInvalidateBoth();
  return useMutation<Service, ApiError, SaveServiceVariables>({
    mutationFn: ({ id, input }) =>
      id === undefined
        ? createService(input as ServiceInput)
        : updateService(id, input),
    onSuccess: invalidate,
  });
}

export function useDeleteService() {
  const invalidate = useInvalidateBoth();
  return useMutation<void, ApiError, number>({
    mutationFn: deleteService,
    onSuccess: invalidate,
  });
}

export function useProviders() {
  return useQuery<Paginated<ServiceProvider>, ApiError>({
    queryKey: providerKeys.list(),
    refetchInterval: LIVE_REFRESH_INTERVAL_MS,
    queryFn: listProviders,
  });
}

export type SaveProviderVariables =
  | { id?: undefined; input: ServiceProviderInput }
  | { id: number; input: Partial<ServiceProviderInput> };

export function useSaveProvider() {
  const invalidate = useInvalidateBoth();
  return useMutation<ServiceProvider, ApiError, SaveProviderVariables>({
    mutationFn: ({ id, input }) =>
      id === undefined
        ? createProvider(input as ServiceProviderInput)
        : updateProvider(id, input),
    onSuccess: invalidate,
  });
}

export function useDeleteProvider() {
  const invalidate = useInvalidateBoth();
  return useMutation<void, ApiError, number>({
    mutationFn: deleteProvider,
    onSuccess: invalidate,
  });
}

/** A provider's week with its bookings (`week`: its Monday, YYYY-MM-DD). */
export function useWeekCalendar(providerId: number | null, week: string) {
  return useQuery<WeekCalendar, ApiError>({
    queryKey: providerKeys.calendar(providerId ?? 0, week),
    refetchInterval: LIVE_REFRESH_INTERVAL_MS,
    queryFn: () => getWeekCalendar(providerId as number, week),
    enabled: providerId !== null,
    placeholderData: keepPreviousData,
  });
}

function useInvalidateCalendars() {
  const queryClient = useQueryClient();
  return () =>
    queryClient.invalidateQueries({ queryKey: providerKeys.calendars() });
}

export function useSaveWeek() {
  const invalidate = useInvalidateCalendars();
  return useMutation<
    WeeklyAvailability,
    ApiError,
    { week: WeekCalendar; availability: string }
  >({
    mutationFn: ({ week, availability }) => saveWeek(week, availability),
    onSuccess: invalidate,
  });
}

export function useSetSlots(providerId: number) {
  const invalidate = useInvalidateCalendars();
  return useMutation<WeeksChange, ApiError, SetSlotsInput>({
    mutationFn: (input) => setSlots(providerId, input),
    onSuccess: invalidate,
  });
}

export function useCopyWeek(providerId: number) {
  const invalidate = useInvalidateCalendars();
  return useMutation<WeeksChange, ApiError, CopyWeekInput>({
    mutationFn: (input) => copyWeek(providerId, input),
    onSuccess: invalidate,
  });
}

/**
 * Whether the business has a service customers can book in the chat: active, with at least one
 * active service provider (like the backend's `active_services`). Reads every page of services.
 * Under `serviceKeys`, so saving a service or a provider refreshes it.
 */
export function useHasBookableServices() {
  return useQuery<boolean, ApiError>({
    queryKey: serviceKeys.hasBookable(),
    queryFn: async () => {
      const providers = await listProviders();
      const active = new Set(
        providers.results
          .filter((provider) => provider.is_active)
          .map((provider) => provider.id),
      );
      for (let page = 1; ; page++) {
        const data = await listServices(page);
        if (
          data.results.some(
            (service) =>
              service.is_active &&
              service.service_providers.some((id) => active.has(id)),
          )
        ) {
          return true;
        }
        if (!data.next) return false;
      }
    },
  });
}
