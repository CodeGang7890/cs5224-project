import type { OrderStatus } from "@/features/orders";

/** Who services are booked with, e.g. one photographer, teacher or venue (`/api/service-providers/`). */
export interface ServiceProvider {
  id: number;
  business: number;
  name: string;
  /** Optional note for the team (not shown to customers). */
  description: string;
  /** Inactive providers take no new bookings. */
  is_active: boolean;
  /** Read-only: the services they do (set on each service). */
  services: number[];
}

/** Writable fields. `id`, `business` and `services` aren't sent. */
export type ServiceProviderInput = Pick<
  ServiceProvider,
  "name" | "description" | "is_active"
>;

/** One provider's week (`/api/weekly-availabilities/`). */
export interface WeeklyAvailability {
  id: number;
  service_provider: number;
  /** The Monday (YYYY-MM-DD). */
  week: string;
  /** 672 letters, one per 15-minute block from Monday 00:00 (local time): see `availability.ts`. */
  availability: string;
}

/** Something customers book a time for (`/api/services/`), e.g. a photoshoot. */
export interface Service {
  id: number;
  business: number;
  name: string;
  /** Short summary the chat assistant tells customers when they ask what the service is. */
  description: string;
  /** Long extra details the assistant looks up only when a question needs them. */
  information: string;
  /** Decimal string, e.g. "180.00". */
  price: string;
  /** How long the service takes, with the customer (a multiple of 15). */
  duration_minutes: number;
  /** Time blocked after each booking, without the customer (a multiple of 15). */
  buffer_minutes: number;
  /** Bookings only start every this many minutes, counted from midnight (15: any quarter hour; 30, 60…). */
  start_interval_minutes: number;
  /** IDs of the service providers who can do it. */
  service_providers: number[];
  is_active: boolean;
}

export type ServiceInput = Omit<Service, "id" | "business">;

/** One booking in a provider's week (`GET /api/service-providers/{id}/calendar/`). */
export interface CalendarBooking {
  id: number;
  /** The service's name, from the booking. */
  service: string;
  /** The customer's `name` detail, if any. */
  customer: string | null;
  details: Record<string, string | number>;
  start_time: string;
  end_time: string;
  /** `end_time` + the buffer. */
  blocked_until: string;
  order_status: OrderStatus;
  /** Random 128-bit reference (32 hex characters) the payment is made under. */
  payment_reference: string;
  /** Decimal string. */
  total: string;
  is_sandbox: boolean;
  chat_session: number | null;
  /** Positions in the week's letters (may be < 0 or ≥ 672 for bookings running into another week). */
  start_block: number;
  /** Where the buffer starts. */
  end_block: number;
  /** The first block after the buffer. */
  until_block: number;
}

/** A provider's week: its letters (all U if it has no WeeklyAvailability yet) and its bookings. */
export interface WeekCalendar {
  service_provider: number;
  /** The Monday (YYYY-MM-DD). */
  week: string;
  /** The time zone the blocks are in, e.g. "Asia/Singapore". */
  time_zone: string;
  /** The WeeklyAvailability's ID; null if the week has none yet. */
  id: number | null;
  availability: string;
  bookings: CalendarBooking[];
}

/** Body of `POST /api/service-providers/{id}/slots/`: open (or close) times on some days of a date range. */
export interface SetSlotsInput {
  /** YYYY-MM-DD, inclusive both ends (at most 26 weeks). */
  date_from: string;
  date_to: string;
  /** 0 = Monday … 6 = Sunday. */
  weekdays: number[];
  /** "HH:MM" on the quarter hour; `time_to` may be "24:00". */
  time_from: string;
  time_to: string;
  /** true: available (O); false: unavailable (U). */
  available: boolean;
}

/** Body of `POST /api/service-providers/{id}/copy-week/`. */
export interface CopyWeekInput {
  /** Mondays (YYYY-MM-DD). `target_week` defaults to the week after `source_week`. */
  source_week: string;
  target_week?: string;
  /** How many weeks to copy to (1–26). */
  weeks?: number;
}

/** What a slots / copy-week request did. */
export interface WeeksChange {
  weeks: WeeklyAvailability[];
  /** Blocks that changed. */
  changed: number;
  /** Blocks left alone because they're booked. */
  skipped: number;
}
