// A weekly availability is 672 letters: one per 15-minute block of the week, from Monday 00:00
// (local time, configuration-service `DJANGO_SCHEDULE_TIME_ZONE`). Mirrors configuration-service
// `product_app/models.py`.

export const SLOT_MINUTES = 15
export const SLOTS_PER_DAY = (24 * 60) / SLOT_MINUTES // 96
export const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'] as const
export const AVAILABILITY_LENGTH = SLOTS_PER_DAY * DAYS.length // 672

export const SLOT_LETTERS = ['O', 'X', 'H'] as const
export type SlotLetter = (typeof SLOT_LETTERS)[number]

export const SLOT_META: Record<SlotLetter, { label: string; description: string; className: string }> = {
  O: { label: 'Available', description: 'Customers can book this time.', className: 'bg-emerald-500/80' },
  X: { label: 'Taken', description: 'Not available.', className: 'bg-muted' },
  H: { label: 'On hold', description: 'Held back for now: not bookable.', className: 'bg-amber-400/80' },
}

/** A new calendar: nothing bookable until you open some blocks. */
export const EMPTY_WEEK = 'X'.repeat(AVAILABILITY_LENGTH)

/** Position of the block starting `slot` blocks after midnight on `day` (0 = Monday). */
export function blockIndex(day: number, slot: number): number {
  return day * SLOTS_PER_DAY + slot
}

/** "HH:MM" for the start of block `slot` of a day (96 = "24:00"). */
export function slotTime(slot: number): string {
  const minutes = slot * SLOT_MINUTES
  return `${String(Math.floor(minutes / 60)).padStart(2, '0')}:${String(minutes % 60).padStart(2, '0')}`
}

/** `availability` with blocks `fromSlot` (inclusive) to `toSlot` (exclusive) of each of `days` set to `letter`. */
export function paint(availability: string, days: number[], fromSlot: number, toSlot: number, letter: SlotLetter): string {
  const letters = availability.split('')
  for (const day of days) {
    for (let slot = Math.max(0, fromSlot); slot < Math.min(SLOTS_PER_DAY, toSlot); slot++) {
      letters[blockIndex(day, slot)] = letter
    }
  }
  return letters.join('')
}

/** Hours per week that can be booked (O blocks). */
export function openHours(availability: string): number {
  return (availability.split('O').length - 1) / (60 / SLOT_MINUTES)
}

/** Whether a string is a valid weekly availability (the backend checks too). */
export function isValidAvailability(value: string): boolean {
  return value.length === AVAILABILITY_LENGTH && /^[OXH]+$/.test(value)
}

/** One line per day with its available hours, e.g. "Mon 09:00–12:00, 13:00–18:00". */
export function describeWeek(availability: string): string[] {
  return DAYS.flatMap((label, day) => {
    const ranges: string[] = []
    let start: number | null = null
    for (let slot = 0; slot <= SLOTS_PER_DAY; slot++) {
      const open = slot < SLOTS_PER_DAY && availability[blockIndex(day, slot)] === 'O'
      if (open && start === null) start = slot
      if (!open && start !== null) {
        ranges.push(`${slotTime(start)}–${slotTime(slot)}`)
        start = null
      }
    }
    return ranges.length ? [`${label} ${ranges.join(', ')}`] : []
  })
}
