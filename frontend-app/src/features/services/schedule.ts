import { DAYS, SLOT_MINUTES } from "./availability";
import type { CalendarBooking, WeeksChange } from "./types";

// Helpers for the schedule UI (kept out of the component files for fast refresh).

/** The booking whose time (with its buffer) covers block `index`. */
export function bookingAt(
  bookings: CalendarBooking[],
  index: number,
): CalendarBooking | undefined {
  return bookings.find(
    (booking) => booking.start_block <= index && index < booking.until_block,
  );
}

/** "Mon–Fri", "Sat, Sun", "every day". */
export function describeWeekdays(weekdays: number[]): string {
  const days = [...new Set(weekdays)].sort((a, b) => a - b);
  if (days.length === 7) return "every day";
  const consecutive =
    days.length > 2 &&
    days.every((day, i) => i === 0 || day === days[i - 1] + 1);
  return consecutive
    ? `${DAYS[days[0]]}–${DAYS[days[days.length - 1]]}`
    : days.map((day) => DAYS[day]).join(", ");
}

/** A sentence saying what a slots / copy-week request did. */
export function describeChange(change: WeeksChange): string {
  const hours = change.changed / (60 / SLOT_MINUTES);
  const weeks = change.weeks.length;
  const done =
    change.changed === 0
      ? "Nothing needed changing."
      : `${hours} hour${hours === 1 ? "" : "s"} changed over ${weeks} week${weeks === 1 ? "" : "s"}.`;
  const skipped = change.skipped / (60 / SLOT_MINUTES);
  return skipped
    ? `${done} ${skipped} booked hour${skipped === 1 ? " was" : "s were"} left as they are.`
    : done;
}
