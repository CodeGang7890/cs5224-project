import { configurationApiClient } from "@/lib/api-client";
import type { DetailedPaginated } from "@/types/api";

import type { ScheduleItem, ScheduleListParams } from "../types";

/** The logged-in business's bookings, filtered, sorted and paginated by the backend. */
export async function listSchedules(
  params: ScheduleListParams,
): Promise<DetailedPaginated<ScheduleItem>> {
  const { data } = await configurationApiClient.get<
    DetailedPaginated<ScheduleItem>
  >("/schedules/", { params });
  return data;
}

/** One booking (403 if it's another business's, 404 if it doesn't exist). */
export async function getSchedule(id: number): Promise<ScheduleItem> {
  const { data } = await configurationApiClient.get<ScheduleItem>(
    `/schedules/${id}/`,
  );
  return data;
}

/** Marks a paid booking as completed (payment received → completed; 400 for any other status). */
export async function completeSchedule(id: number): Promise<ScheduleItem> {
  const { data } = await configurationApiClient.post<ScheduleItem>(
    `/schedules/${id}/complete/`,
  );
  return data;
}
