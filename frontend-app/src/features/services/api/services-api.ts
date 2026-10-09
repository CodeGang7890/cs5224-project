import { configurationApiClient } from '@/lib/api-client'
import type { Paginated } from '@/types/api'

import type { Service, ServiceInput, WeekCalendar, WeeklyAvailability, WeeklyAvailabilityInput } from '../types'

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

/** The first page of weekly availabilities (20; plenty for a team's calendars). */
export async function listAvailabilities(): Promise<Paginated<WeeklyAvailability>> {
  const { data } = await configurationApiClient.get<Paginated<WeeklyAvailability>>('/weekly-availabilities/')
  return data
}

export async function createAvailability(input: WeeklyAvailabilityInput): Promise<WeeklyAvailability> {
  const { data } = await configurationApiClient.post<WeeklyAvailability>('/weekly-availabilities/', input)
  return data
}

export async function updateAvailability(
  id: number,
  changes: Partial<WeeklyAvailabilityInput>,
): Promise<WeeklyAvailability> {
  const { data } = await configurationApiClient.patch<WeeklyAvailability>(`/weekly-availabilities/${id}/`, changes)
  return data
}

export async function deleteAvailability(id: number): Promise<void> {
  await configurationApiClient.delete(`/weekly-availabilities/${id}/`)
}

/** The week containing `day` (YYYY-MM-DD) of a calendar, with its bookings. */
export async function getWeekCalendar(id: number, day: string): Promise<WeekCalendar> {
  const { data } = await configurationApiClient.get<WeekCalendar>(`/weekly-availabilities/${id}/calendar/`, {
    params: { week: day },
  })
  return data
}
