import { useEffect, useRef } from 'react'

import { cn } from '@/lib/utils'

import { DAYS, SLOT_META, SLOTS_PER_DAY, blockIndex, isBooked, slotTime, type SlotLetter } from '../availability'
import { bookingAt } from '../schedule'
import type { CalendarBooking } from '../types'

/** Height of one 15-minute row, in px (an hour = 4 rows). */
export const ROW_HEIGHT = 10

interface ScheduleGridProps {
  /** 672 letters (see `availability.ts`). */
  availability: string
  /** The week's bookings, drawn as blocks over their time (the buffer after shows as its letter). */
  bookings: CalendarBooking[]
  /** e.g. "Mon 7". */
  dayLabels: readonly string[]
  /** Column of today (0 = Monday), if it's in this week. */
  todayColumn?: number
  /** Edit mode: called for each open / closed block painted (click, or drag across blocks). */
  onPaint?: (index: number) => void
  /** Clicking a booked block (or its buffer). */
  onBookingClick: (booking: CalendarBooking) => void
  selectedBookingId?: number | null
}

/**
 * A provider's week: days across, 15-minute blocks down. Each cell is one letter; bookings are
 * drawn over theirs as buttons. Every element is placed explicitly in the CSS grid, so the
 * booking blocks can overlap the cells.
 */
export function ScheduleGrid({
  availability,
  bookings,
  dayLabels,
  todayColumn,
  onPaint,
  onBookingClick,
  selectedBookingId,
}: ScheduleGridProps) {
  const painting = useRef(false)

  useEffect(() => {
    const stop = () => {
      painting.current = false
    }
    window.addEventListener('pointerup', stop)
    window.addEventListener('pointercancel', stop)
    return () => {
      window.removeEventListener('pointerup', stop)
      window.removeEventListener('pointercancel', stop)
    }
  }, [])

  const cells = []
  for (let slot = 0; slot < SLOTS_PER_DAY; slot++) {
    const hourStart = slot % 4 === 0
    if (hourStart) {
      cells.push(
        <div
          key={`t${slot}`}
          className="text-muted-foreground pr-1 text-right text-[10px] leading-none"
          style={{ gridColumn: 1, gridRow: `${slot + 2} / span 4` }}
        >
          <span className="relative -top-1">{slotTime(slot)}</span>
        </div>,
      )
    }
    for (let day = 0; day < DAYS.length; day++) {
      const index = blockIndex(day, slot)
      const letter = availability[index] as SlotLetter
      const booked = isBooked(letter)
      const booking = booked ? bookingAt(bookings, index) : undefined
      const paintable = onPaint && !booked
      cells.push(
        <div
          key={index}
          role="gridcell"
          title={`${DAYS[day]} ${slotTime(slot)}–${slotTime(slot + 1)}: ${SLOT_META[letter]?.label ?? letter}${booking ? ` (${booking.customer ?? booking.service})` : ''}`}
          className={cn(
            'border-background border-x',
            hourStart && 'border-t-border/60 border-t',
            SLOT_META[letter]?.className,
            paintable && 'cursor-crosshair',
            booking && 'cursor-pointer',
            day === todayColumn && letter === 'U' && 'bg-sky-500/10',
          )}
          style={{ gridColumn: day + 2, gridRow: slot + 2 }}
          onPointerDown={
            paintable
              ? (event) => {
                  event.preventDefault()
                  painting.current = true
                  onPaint(index)
                }
              : undefined
          }
          onPointerEnter={paintable ? () => painting.current && onPaint(index) : undefined}
          onClick={booking ? () => onBookingClick(booking) : undefined}
        />,
      )
    }
  }

  return (
    <div
      className={cn('grid select-none', onPaint && 'touch-none')}
      style={{
        gridTemplateColumns: `3rem repeat(${DAYS.length}, minmax(0, 1fr))`,
        gridTemplateRows: `auto repeat(${SLOTS_PER_DAY}, ${ROW_HEIGHT}px)`,
      }}
      role="grid"
      aria-label="Weekly schedule"
    >
      <div className="bg-background sticky top-0 z-20" style={{ gridColumn: 1, gridRow: 1 }} />
      {dayLabels.map((label, day) => (
        <div
          key={label}
          className={cn(
            'bg-background sticky top-0 z-20 pb-1 text-center text-xs font-medium',
            day === todayColumn ? 'text-sky-600 dark:text-sky-400' : 'text-muted-foreground',
          )}
          style={{ gridColumn: day + 2, gridRow: 1 }}
        >
          {label}
          {day === todayColumn && <span className="sr-only"> (today)</span>}
        </div>
      ))}
      {cells}
      {bookings.flatMap((booking) => bookingBlocks(booking, booking.id === selectedBookingId, onBookingClick))}
    </div>
  )
}

/** A booking's duration as one button per day it covers in this week. */
function bookingBlocks(booking: CalendarBooking, selected: boolean, onClick: (booking: CalendarBooking) => void) {
  const blocks = []
  for (let day = 0; day < DAYS.length; day++) {
    const dayStart = day * SLOTS_PER_DAY
    const from = Math.max(booking.start_block, dayStart)
    const to = Math.min(booking.end_block, dayStart + SLOTS_PER_DAY)
    if (from >= to) continue
    const rows = to - from
    const onHold = booking.order_status === 'pending_payment'
    blocks.push(
      <button
        key={`${booking.id}-${day}`}
        type="button"
        onClick={() => onClick(booking)}
        aria-label={`${booking.service} for ${booking.customer ?? 'a customer'}: ${onHold ? 'on hold, pending payment' : 'booked'}`}
        className={cn(
          'z-10 mx-px overflow-hidden rounded-sm border px-1 text-left text-[10px] leading-tight shadow-sm',
          'focus-visible:ring-ring focus-visible:ring-2 focus-visible:outline-none',
          onHold
            ? 'border-amber-600/60 bg-amber-200 text-amber-950 dark:bg-amber-900 dark:text-amber-50'
            : 'border-rose-600/60 bg-rose-200 text-rose-950 dark:bg-rose-900 dark:text-rose-50',
          booking.is_sandbox && 'border-dashed',
          selected && 'ring-ring ring-2',
        )}
        style={{ gridColumn: day + 2, gridRow: `${from - dayStart + 2} / ${to - dayStart + 2}` }}
      >
        {rows >= 2 && <span className="block truncate font-semibold">{booking.customer ?? 'Customer'}</span>}
        {rows >= 3 && <span className="block truncate">{booking.service}</span>}
      </button>,
    )
  }
  return blocks
}

/** The colour key for the letters. */
export function SlotLegend() {
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
      {(Object.keys(SLOT_META) as SlotLetter[]).map((letter) => (
        <li key={letter} className="flex items-center gap-1.5" title={SLOT_META[letter].description}>
          <span className={cn('size-3 rounded-sm border', SLOT_META[letter].className)} />
          <span className="font-medium">{SLOT_META[letter].label}</span>
          <span className="text-muted-foreground">({letter})</span>
        </li>
      ))}
    </ul>
  )
}
