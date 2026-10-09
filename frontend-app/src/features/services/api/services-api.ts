import { configurationApiClient } from '@/lib/api-client'
import type { Paginated } from '@/types/api'

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
} from '../types'

// Plain async functions that call configuration-service. Lists are scoped to the logged-in
// user's business by the backend; `business` is never sent (it defaults to yours).

export async function listServices(page: number): Promise<Paginated<Service>> {
  const { data } = await configurationApiClient.get<Paginated<Service>>('/services/', { params: { page } })
  return data
}

export async function createService(input: ServiceInput): Promise<Service> {
  const { data } = await configurationApiClient.post<Service>('/services/', input)
  return data
}

export async function updateService(id: number, changes: Partial<ServiceInput>): Promise<Service> {
  const { data } = await configurationApiClient.patch<Service>(`/services/${id}/`, changes)
  return data
}

export async function deleteService(id: number): Promise<void> {
  await configurationApiClient.delete(`/services/${id}/`)
}

/** The first page of service providers (20; plenty for a team). */
export async function listProviders(): Promise<Paginated<ServiceProvider>> {
  const { data } = await configurationApiClient.get<Paginated<ServiceProvider>>('/service-providers/')
  return data
}

export async function createProvider(input: ServiceProviderInput): Promise<ServiceProvider> {
  const { data } = await configurationApiClient.post<ServiceProvider>('/service-providers/', input)
  return data
}

export async function updateProvider(id: number, changes: Partial<ServiceProviderInput>): Promise<ServiceProvider> {
  const { data } = await configurationApiClient.patch<ServiceProvider>(`/service-providers/${id}/`, changes)
  return data
}

export async function deleteProvider(id: number): Promise<void> {
  await configurationApiClient.delete(`/service-providers/${id}/`)
}

/** The week containing `day` (YYYY-MM-DD) of a provider, with its bookings. */
export async function getWeekCalendar(providerId: number, day: string): Promise<WeekCalendar> {
  const { data } = await configurationApiClient.get<WeekCalendar>(`/service-providers/${providerId}/calendar/`, {
    params: { week: day },
  })
  return data
}

/** Saves a week's letters: creates its WeeklyAvailability (`id` null) or updates it. Only O ↔ U may change. */
export async function saveWeek(
  week: { id: number | null; service_provider: number; week: string },
  availability: string,
): Promise<WeeklyAvailability> {
  const { data } =
    week.id === null
      ? await configurationApiClient.post<WeeklyAvailability>('/weekly-availabilities/', {
          service_provider: week.service_provider,
          week: week.week,
          availability,
        })
      : await configurationApiClient.patch<WeeklyAvailability>(`/weekly-availabilities/${week.id}/`, { availability })
  return data
}

export async function setSlots(providerId: number, input: SetSlotsInput): Promise<WeeksChange> {
  const { data } = await configurationApiClient.post<WeeksChange>(`/service-providers/${providerId}/slots/`, input)
  return data
}

export async function copyWeek(providerId: number, input: CopyWeekInput): Promise<WeeksChange> {
  const { data } = await configurationApiClient.post<WeeksChange>(`/service-providers/${providerId}/copy-week/`, input)
  return data
}
