import type { ScheduleItem } from '../types'

/** "Tue 14 Oct 2026, 2:00 – 3:30 pm" (browser local time). */
export function formatBookingTime(booking: Pick<ScheduleItem, 'start_time' | 'end_time'>): string {
  const start = new Date(booking.start_time)
  const end = new Date(booking.end_time)
  const day = start.toLocaleDateString([], { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' })
  const time = (date: Date) => date.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
  return `${day}, ${time(start)} – ${time(end)}`
}

/** The customer's name (a detail with the key `name`), else their email, else nothing. */
export function bookingCustomer(booking: ScheduleItem): string | null {
  const { name, email } = booking.schedule_data.details
  return (typeof name === 'string' && name) || (typeof email === 'string' && email) || null
}
