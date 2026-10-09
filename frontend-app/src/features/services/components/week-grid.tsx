import { useEffect, useRef, type RefObject } from 'react'

import { cn } from '@/lib/utils'

import { DAYS, SLOT_META, SLOTS_PER_DAY, blockIndex, slotTime, type SlotLetter } from '../availability'

interface WeekGridProps {
  /** 672 letters (see `availability.ts`). */
  availability: string
  /** Called for each block painted (click, or drag across blocks). Omit for a read-only grid. */
  onPaint?: (day: number, slot: number) => void
  /** Day labels, e.g. with dates for a calendar week (default: Mon … Sun). */
  dayLabels?: readonly string[]
  className?: string
}

/**
 * A week of 15-minute blocks: days across, times down (one row per block, an hour per 4 rows).
 * Editable grids paint while the pointer is held down, so a drag fills a range.
 */
export function WeekGrid({ availability, onPaint, dayLabels = DAYS, className }: WeekGridProps) {
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

  return (
    <div
      className={cn('grid select-none text-[10px]', onPaint && 'touch-none', className)}
      style={{ gridTemplateColumns: `3rem repeat(${DAYS.length}, minmax(0, 1fr))` }}
      role="grid"
      aria-label="Weekly availability"
    >
      <div />
      {dayLabels.map((label) => (
        <div key={label} className="text-muted-foreground pb-1 text-center font-medium">
          {label}
        </div>
      ))}
      {Array.from({ length: SLOTS_PER_DAY }, (_, slot) => (
        <Row key={slot} slot={slot} availability={availability} onPaint={onPaint} painting={painting} />
      ))}
    </div>
  )
}

function Row({
  slot,
  availability,
  onPaint,
  painting,
}: {
  slot: number
  availability: string
  onPaint?: (day: number, slot: number) => void
  painting: RefObject<boolean>
}) {
  const hourStart = slot % 4 === 0
  return (
    <>
      {/* The label overflows its 6px row, so it can't stretch the row. */}
      <div className="relative h-1.5">
        {hourStart && (
          <span className="text-muted-foreground absolute top-0 right-1 -translate-y-1/3 leading-none">
            {slotTime(slot)}
          </span>
        )}
      </div>
      {DAYS.map((label, day) => {
        const letter = availability[blockIndex(day, slot)] as SlotLetter
        return (
          <div
            key={label}
            role="gridcell"
            aria-label={`${label} ${slotTime(slot)}–${slotTime(slot + 1)}: ${SLOT_META[letter]?.label ?? letter}`}
            className={cn(
              'h-1.5 border-x border-background',
              hourStart && 'border-t border-t-border/60',
              SLOT_META[letter]?.className,
              onPaint && 'cursor-crosshair',
            )}
            onPointerDown={
              onPaint &&
              ((event) => {
                event.preventDefault()
                painting.current = true
                onPaint(day, slot)
              })
            }
            onPointerEnter={onPaint && (() => painting.current && onPaint(day, slot))}
          />
        )
      })}
    </>
  )
}

/** The colour key for the letters. */
export function SlotLegend({ letters }: { letters: readonly SlotLetter[] }) {
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
      {letters.map((letter) => (
        <li key={letter} className="flex items-center gap-1.5">
          <span className={cn('size-3 rounded-sm border', SLOT_META[letter].className)} />
          <span className="font-medium">{SLOT_META[letter].label}</span>
          <span className="text-muted-foreground">({letter})</span>
        </li>
      ))}
    </ul>
  )
}
