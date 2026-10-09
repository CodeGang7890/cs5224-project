import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import type { ApiError, Paginated } from '@/types/api'

import {
  createAvailability,
  createService,
  deleteAvailability,
  deleteService,
  getWeekCalendar,
  listAvailabilities,
  listServices,
  updateAvailability,
  updateService,
} from '../api/services-api'
import type { Service, ServiceInput, WeekCalendar, WeeklyAvailability, WeeklyAvailabilityInput } from '../types'

export const SERVICES_PAGE_SIZE = 20 // matches the backend's PAGE_SIZE

export const serviceKeys = {
  all: ['services'] as const,
  list: (page: number) => [...serviceKeys.all, 'list', page] as const,
}

// Availabilities list which services they do, and services list their availabilities, so
// changing either refreshes both.
export const availabilityKeys = {
  all: ['weekly-availabilities'] as const,
  list: () => [...availabilityKeys.all, 'list'] as const,
  calendar: (id: number, day: string) => [...availabilityKeys.all, 'calendar', id, day] as const,
}

function useInvalidateBoth() {
  const queryClient = useQueryClient()
  return () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: serviceKeys.all }),
      queryClient.invalidateQueries({ queryKey: availabilityKeys.all }),
    ])
}

export function useServices(page: number) {
  return useQuery<Paginated<Service>, ApiError>({
    queryKey: serviceKeys.list(page),
    queryFn: () => listServices(page),
    placeholderData: keepPreviousData,
  })
}

export type SaveServiceVariables =
  | { id?: undefined; input: ServiceInput }
  | { id: number; input: Partial<ServiceInput> }

/** Creates (no `id`) or updates (with `id`) a service. */
export function useSaveService() {
  const invalidate = useInvalidateBoth()
  return useMutation<Service, ApiError, SaveServiceVariables>({
    mutationFn: ({ id, input }) => (id === undefined ? createService(input as ServiceInput) : updateService(id, input)),
    onSuccess: invalidate,
  })
}

export function useDeleteService() {
  const invalidate = useInvalidateBoth()
  return useMutation<void, ApiError, number>({ mutationFn: deleteService, onSuccess: invalidate })
}

export function useAvailabilities() {
  return useQuery<Paginated<WeeklyAvailability>, ApiError>({
    queryKey: availabilityKeys.list(),
    queryFn: listAvailabilities,
  })
}

export type SaveAvailabilityVariables =
  | { id?: undefined; input: WeeklyAvailabilityInput }
  | { id: number; input: Partial<WeeklyAvailabilityInput> }

export function useSaveAvailability() {
  const invalidate = useInvalidateBoth()
  return useMutation<WeeklyAvailability, ApiError, SaveAvailabilityVariables>({
    mutationFn: ({ id, input }) =>
      id === undefined ? createAvailability(input as WeeklyAvailabilityInput) : updateAvailability(id, input),
    onSuccess: invalidate,
  })
}

export function useDeleteAvailability() {
  const invalidate = useInvalidateBoth()
  return useMutation<void, ApiError, number>({ mutationFn: deleteAvailability, onSuccess: invalidate })
}

/** A week of a calendar with its bookings (`day`: any day of the week, YYYY-MM-DD). */
export function useWeekCalendar(id: number | null, day: string) {
  return useQuery<WeekCalendar, ApiError>({
    queryKey: availabilityKeys.calendar(id ?? 0, day),
    queryFn: () => getWeekCalendar(id as number, day),
    enabled: id !== null,
    placeholderData: keepPreviousData,
  })
}
