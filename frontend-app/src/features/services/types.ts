/** A weekly calendar (e.g. one photographer's) as returned by configuration-service (`/api/weekly-availabilities/`). */
export interface WeeklyAvailability {
  id: number
  business: number
  /** Whose calendar it is, e.g. "Photographer: Mei" (not shown to customers). */
  name: string
  /** 672 letters, one per 15-minute block of the week from Monday 00:00 (local time): see `availability.ts`. */
  availability: string
  /** Read-only: the services this calendar can do (set on each service). */
  services: number[]
}

/** Writable fields. `id`, `business` and `services` aren't sent. */
export type WeeklyAvailabilityInput = Pick<WeeklyAvailability, 'name' | 'availability'>

/** Something customers book a time for (`/api/services/`), e.g. a photoshoot. */
export interface Service {
  id: number
  business: number
  name: string
  /** Short summary the chat assistant tells customers when they ask what the service is. */
  description: string
  /** Long extra details the assistant looks up only when a question needs them. */
  information: string
  /** Decimal string, e.g. "180.00". */
  price: string
  /** How long the service takes, with the customer (a multiple of 15). */
  duration_minutes: number
  /** Time blocked after each booking, without the customer (a multiple of 15). */
  buffer_minutes: number
  /** IDs of the weekly availabilities that can do it. */
  weekly_availability: number[]
  is_active: boolean
}

export type ServiceInput = Omit<Service, 'id' | 'business'>

/** One booking in a week's calendar (`GET /api/weekly-availabilities/{id}/calendar/`). */
export interface CalendarBooking {
  id: number
  /** The service's name, from the booking. */
  service: string
  start_time: string
  end_time: string
  blocked_until: string
  order_status: string
}

/** A week of a calendar: the template with that week's bookings drawn over it (H pending payment, X paid / completed). */
export interface WeekCalendar {
  /** The Monday (YYYY-MM-DD). */
  week_start: string
  availability: string
  bookings: CalendarBooking[]
}
