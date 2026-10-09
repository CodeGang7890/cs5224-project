// A week's availability is 672 letters: one per 15-minute block, from Monday 00:00 (local time,
// configuration-service `DJANGO_SCHEDULE_TIME_ZONE`). Mirrors configuration-service
// `product_app/models.py`.

export const SLOT_MINUTES = 15
export const SLOTS_PER_DAY = (24 * 60) / SLOT_MINUTES // 96
export const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'] as const
export const AVAILABILITY_LENGTH = SLOTS_PER_DAY * DAYS.length // 672
/** How many weeks one slots / copy-week request may change (the backend's `WEEKS_CHANGED_MAX`). */
export const WEEKS_CHANGED_MAX = 26

export const SLOT_LETTERS = ['O', 'U', 'H', 'X'] as const
export type SlotLetter = (typeof SLOT_LETTERS)[number]
/** The letters the business sets; H and X come only from bookings. */
export const EDITABLE_LETTERS = ['O', 'U'] as const
export type EditableLetter = (typeof EDITABLE_LETTERS)[number]

export const SLOT_META: Record<SlotLetter, { label: string; description: string; className: string }> = {
  O: { label: 'Available', description: 'Customers can book this time.', className: 'bg-emerald-500/70' },
  U: { label: 'Unavailable', description: 'Not open for bookings.', className: 'bg-muted' },
  H: { label: 'On hold', description: 'Booked, waiting for payment.', className: 'bg-amber-400/80' },
  X: { label: 'Booked', description: 'Booked and paid.', className: 'bg-rose-500/70' },
}

/** A week with no availability yet: nothing open. */
export const UNAVAILABLE_WEEK = 'U'.repeat(AVAILABILITY_LENGTH)

export function isBooked(letter: string): boolean {
  return letter === 'H' || letter === 'X'
}

/** Position of the block starting `slot` blocks after midnight on `day` (0 = Monday). */
export function blockIndex(day: number, slot: number): number {
  return day * SLOTS_PER_DAY + slot
}

/** "HH:MM" for the start of block `slot` of a day (96 = "24:00"). */
export function slotTime(slot: number): string {
  const minutes = slot * SLOT_MINUTES
  return `${String(Math.floor(minutes / 60)).padStart(2, '0')}:${String(minutes % 60).padStart(2, '0')}`
}

/**
 * `availability` with blocks `fromSlot` (inclusive) to `toSlot` (exclusive) of each of `days` set
 * to `letter`. Booked blocks (H / X) are left as they are, as the backend does.
 */
export function paint(availability: string, days: number[], fromSlot: number, toSlot: number, letter: EditableLetter): string {
  const letters = availability.split('')
  for (const day of days) {
    for (let slot = Math.max(0, fromSlot); slot < Math.min(SLOTS_PER_DAY, toSlot); slot++) {
      const index = blockIndex(day, slot)
      if (!isBooked(letters[index])) letters[index] = letter
    }
  }
  return letters.join('')
}

/** `latest` with the blocks the user changed (`draft` vs `base`) applied, where they aren't booked now. */
export function applyEdits(base: string, draft: string, latest: string): string {
  return latest
    .split('')
    .map((letter, index) => (draft[index] !== base[index] && !isBooked(letter) ? draft[index] : letter))
    .join('')
}

/** Hours of the week with `letter`. */
export function hoursOf(availability: string, letter: SlotLetter): number {
  return (availability.split(letter).length - 1) / (60 / SLOT_MINUTES)
}

// --- Dates (YYYY-MM-DD strings, read as local dates) -------------------------------------------

function parseDay(day: string): Date {
  return new Date(`${day}T00:00:00`)
}

/** YYYY-MM-DD of a local date. */
export function isoDay(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

export function today(): string {
  return isoDay(new Date())
}

export function addDays(day: string, days: number): string {
  const date = parseDay(day)
  date.setDate(date.getDate() + days)
  return isoDay(date)
}

/** The Monday of the week `day` is in. */
export function mondayOf(day: string): string {
  return addDays(day, -((parseDay(day).getDay() + 6) % 7))
}

/** Whether `value` is a real YYYY-MM-DD date. */
export function isIsoDay(value: string): boolean {
  return /^\d{4}-\d{2}-\d{2}$/.test(value) && isoDay(parseDay(value)) === value
}

/** "7 Sep", or "7 Sep 2026" with the year. */
export function formatDay(day: string, withYear = false): string {
  return parseDay(day).toLocaleDateString([], { day: 'numeric', month: 'short', year: withYear ? 'numeric' : undefined })
}

/** "7 – 13 Sep 2026" for the week starting on Monday `week`. */
export function formatWeek(week: string): string {
  return `${formatDay(week)} – ${formatDay(addDays(week, 6), true)}`
}

/** Day labels of the week starting on Monday `week`, e.g. "Mon 7". */
export function weekDayLabels(week: string): string[] {
  return DAYS.map((label, index) => `${label} ${parseDay(addDays(week, index)).getDate()}`)
}
