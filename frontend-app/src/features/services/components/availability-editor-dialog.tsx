import { type FormEvent, useState } from 'react'
import { ChevronLeft, ChevronRight, CircleAlert } from 'lucide-react'

import { ConfirmDialog } from '@/components/common/confirm-dialog'
import { FormField } from '@/components/common/form-field'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { NativeSelect } from '@/components/ui/native-select'
import { Skeleton } from '@/components/ui/skeleton'
import { type FormErrors, getFormErrors } from '@/lib/form-errors'
import { cn } from '@/lib/utils'

import {
  DAYS,
  EMPTY_WEEK,
  SLOT_LETTERS,
  SLOT_META,
  SLOTS_PER_DAY,
  blockIndex,
  openHours,
  paint,
  slotTime,
  type SlotLetter,
} from '../availability'
import { useSaveAvailability, useWeekCalendar } from '../hooks/use-services'
import type { WeeklyAvailability } from '../types'
import { SERVICE_LIMITS, changedAvailabilityFields, validateAvailability } from '../validation'
import { SlotLegend, WeekGrid } from './week-grid'

interface AvailabilityEditorDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** The calendar to edit; omit to create one. */
  availability?: WeeklyAvailability
}

/** Edits a weekly availability's name and template; for a saved one, also shows its bookings by week. */
export function AvailabilityEditorDialog({ open, onOpenChange, availability }: AvailabilityEditorDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[92svh] flex-col gap-4 sm:max-w-3xl">
        {open && <Editor availability={availability} onDone={() => onOpenChange(false)} />}
      </DialogContent>
    </Dialog>
  )
}

type Tab = 'template' | 'bookings'

function Editor({ availability, onDone }: { availability?: WeeklyAvailability; onDone: () => void }) {
  const isEdit = availability !== undefined
  const save = useSaveAvailability()
  const [tab, setTab] = useState<Tab>('template')
  const [name, setName] = useState(availability?.name ?? '')
  const [week, setWeek] = useState(availability?.availability ?? EMPTY_WEEK)
  const [brush, setBrush] = useState<SlotLetter>('O')
  const [errors, setErrors] = useState<FormErrors>({ fields: {} })
  const [confirmOpen, setConfirmOpen] = useState(false)

  const input = { name: name.trim(), availability: week }
  const changes = isEdit ? changedAvailabilityFields(availability, input) : input
  const hasChanges = Object.keys(changes).length > 0

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const fieldErrors = validateAvailability(input)
    setErrors({ fields: fieldErrors as Record<string, string> })
    if (Object.keys(fieldErrors).length === 0 && hasChanges) setConfirmOpen(true)
  }

  const handleConfirm = () => {
    save.mutate(isEdit ? { id: availability.id, input: changes } : { input }, {
      onSuccess: () => {
        setConfirmOpen(false)
        onDone()
      },
      onError: (error) => {
        setConfirmOpen(false)
        setErrors(getFormErrors(error))
      },
    })
  }

  return (
    <>
      <form onSubmit={handleSubmit} noValidate className="flex min-h-0 flex-col gap-4">
        <DialogHeader>
          <DialogTitle>{isEdit ? `Edit “${availability.name}”` : 'Add weekly availability'}</DialogTitle>
          <DialogDescription>
            When this calendar (e.g. one photographer) can take bookings, every week. Customers can only book the
            available blocks, and never over another booking.
          </DialogDescription>
        </DialogHeader>

        <FormField
          id="availability-name"
          label="Name"
          required
          error={errors.fields.name || undefined}
          length={{ current: name.trim().length, max: SERVICE_LIMITS.availabilityNameMaxLength }}
        >
          <Input id="availability-name" value={name} onChange={(e) => setName(e.target.value)} autoFocus />
        </FormField>

        {isEdit && (
          <div role="tablist" aria-label="Calendar" className="flex gap-1 border-b">
            {(['template', 'bookings'] as const).map((value) => (
              <button
                key={value}
                type="button"
                role="tab"
                aria-selected={tab === value}
                onClick={() => setTab(value)}
                className={cn(
                  '-mb-px border-b-2 px-3 py-1.5 text-sm font-medium',
                  tab === value ? 'border-primary' : 'text-muted-foreground border-transparent',
                )}
              >
                {value === 'template' ? 'Weekly hours' : 'Bookings by week'}
              </button>
            ))}
          </div>
        )}

        {tab === 'template' ? (
          <TemplateEditor week={week} setWeek={setWeek} brush={brush} setBrush={setBrush} />
        ) : (
          <BookingsView availabilityId={availability!.id} />
        )}

        {(errors.form || errors.fields.availability) && (
          <p role="alert" className="text-destructive flex items-center gap-2 text-sm">
            <CircleAlert className="size-4 shrink-0" /> {errors.form ?? errors.fields.availability}
          </p>
        )}

        <DialogFooter>
          <Button type="button" variant="outline" onClick={onDone}>
            Cancel
          </Button>
          <Button type="submit" disabled={!hasChanges}>
            {isEdit ? 'Save changes' : 'Add availability'}
          </Button>
        </DialogFooter>
      </form>

      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title={isEdit ? 'Save this calendar?' : 'Add this calendar?'}
        description={
          <>
            “{input.name}” will be bookable {openHours(week)} hours a week. Existing bookings are kept, even where
            the new hours no longer cover them.
          </>
        }
        confirmLabel={isEdit ? 'Save changes' : 'Add availability'}
        pendingLabel="Saving…"
        isPending={save.isPending}
        onConfirm={handleConfirm}
      />
    </>
  )
}

const PRESETS: { label: string; apply: (week: string) => string }[] = [
  { label: 'Weekdays 9am–6pm', apply: (week) => paint(paint(week, [0, 1, 2, 3, 4, 5, 6], 0, SLOTS_PER_DAY, 'X'), [0, 1, 2, 3, 4], 36, 72, 'O') },
  { label: 'Every day 10am–8pm', apply: (week) => paint(paint(week, [0, 1, 2, 3, 4, 5, 6], 0, SLOTS_PER_DAY, 'X'), [0, 1, 2, 3, 4, 5, 6], 40, 80, 'O') },
  { label: 'Clear all', apply: () => EMPTY_WEEK },
]

function TemplateEditor({
  week,
  setWeek,
  brush,
  setBrush,
}: {
  week: string
  setWeek: (update: (week: string) => string) => void
  brush: SlotLetter
  setBrush: (letter: SlotLetter) => void
}) {
  // Quick fill: a range of time on some days.
  const [days, setDays] = useState<number[]>([0, 1, 2, 3, 4])
  const [from, setFrom] = useState(36)
  const [to, setTo] = useState(72)

  return (
    <div className="flex min-h-0 flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-1" role="radiogroup" aria-label="Paint with">
          <span className="text-muted-foreground mr-1 text-xs">Paint:</span>
          {SLOT_LETTERS.map((letter) => (
            <Button
              key={letter}
              type="button"
              size="sm"
              variant={brush === letter ? 'default' : 'outline'}
              role="radio"
              aria-checked={brush === letter}
              title={SLOT_META[letter].description}
              onClick={() => setBrush(letter)}
            >
              <span className={cn('size-2.5 rounded-sm border', SLOT_META[letter].className)} /> {SLOT_META[letter].label}
            </Button>
          ))}
        </div>
        <div className="flex flex-wrap gap-1">
          {PRESETS.map((preset) => (
            <Button key={preset.label} type="button" size="sm" variant="ghost" onClick={() => setWeek(preset.apply)}>
              {preset.label}
            </Button>
          ))}
        </div>
      </div>

      <div className="bg-muted/30 flex flex-wrap items-end gap-2 rounded-lg border p-2 text-xs">
        <div className="flex gap-1" aria-label="Days">
          {DAYS.map((label, day) => (
            <label key={label} className="flex flex-col items-center gap-0.5">
              <span>{label}</span>
              <input
                type="checkbox"
                checked={days.includes(day)}
                onChange={(e) => setDays((current) => (e.target.checked ? [...current, day] : current.filter((d) => d !== day)))}
              />
            </label>
          ))}
        </div>
        <TimeSelect id="fill-from" label="From" value={from} onChange={setFrom} max={SLOTS_PER_DAY - 1} />
        <TimeSelect id="fill-to" label="To" value={to} onChange={setTo} min={1} max={SLOTS_PER_DAY} />
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={days.length === 0 || to <= from}
          onClick={() => setWeek((current) => paint(current, days, from, to, brush))}
        >
          Set to {SLOT_META[brush].label.toLowerCase()}
        </Button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto rounded-lg border p-2">
        <WeekGrid
          availability={week}
          onPaint={(day, slot) =>
            setWeek((current) =>
              current[blockIndex(day, slot)] === brush ? current : paint(current, [day], slot, slot + 1, brush),
            )
          }
        />
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <SlotLegend letters={SLOT_LETTERS} />
        <p className="text-muted-foreground text-xs tabular-nums">{openHours(week)} hours a week available</p>
      </div>
    </div>
  )
}

function TimeSelect({
  id,
  label,
  value,
  onChange,
  min = 0,
  max,
}: {
  id: string
  label: string
  value: number
  onChange: (slot: number) => void
  min?: number
  max: number
}) {
  return (
    <div className="grid gap-0.5">
      <Label htmlFor={id} className="text-xs font-normal">
        {label}
      </Label>
      <NativeSelect id={id} className="h-8 w-24" value={value} onChange={(e) => onChange(Number(e.target.value))}>
        {Array.from({ length: max - min + 1 }, (_, i) => min + i).map((slot) => (
          <option key={slot} value={slot}>
            {slotTime(slot)}
          </option>
        ))}
      </NativeSelect>
    </div>
  )
}

/** YYYY-MM-DD of a local date. */
function isoDay(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

function BookingsView({ availabilityId }: { availabilityId: number }) {
  const [day, setDay] = useState(() => isoDay(new Date()))
  const { data, isPending, isError, error, isPlaceholderData } = useWeekCalendar(availabilityId, day)
  const shift = (weeks: number) => {
    const next = new Date(`${day}T00:00:00`)
    next.setDate(next.getDate() + 7 * weeks)
    setDay(isoDay(next))
  }
  const monday = data ? new Date(`${data.week_start}T00:00:00`) : null
  const labels = DAYS.map((label, index) => {
    if (!monday) return label
    const date = new Date(monday)
    date.setDate(date.getDate() + index)
    return `${label} ${date.getDate()}`
  })

  return (
    <div className="flex min-h-0 flex-col gap-3">
      <div className="flex items-center justify-between gap-2">
        <Button type="button" size="sm" variant="outline" onClick={() => shift(-1)}>
          <ChevronLeft /> Previous week
        </Button>
        <span className="text-sm font-medium">
          {monday ? `Week of ${monday.toLocaleDateString([], { day: 'numeric', month: 'long', year: 'numeric' })}` : ' '}
        </span>
        <Button type="button" size="sm" variant="outline" onClick={() => shift(1)}>
          Next week <ChevronRight />
        </Button>
      </div>
      {isPending ? (
        <Skeleton className="h-72 w-full" />
      ) : isError ? (
        <p role="alert" className="text-destructive text-sm">
          Couldn't load this week: {error.message}
        </p>
      ) : (
        <>
          <div className={cn('min-h-0 flex-1 overflow-y-auto rounded-lg border p-2', isPlaceholderData && 'opacity-60')}>
            <WeekGrid availability={data.availability} dayLabels={labels} />
          </div>
          <SlotLegend letters={SLOT_LETTERS} />
          <p className="text-muted-foreground text-xs">
            Read only: the saved weekly hours, with this week's bookings drawn over them (on hold while pending
            payment, taken once paid), including the buffer after each.{' '}
            {data.bookings.length === 0
              ? 'No bookings this week.'
              : `${data.bookings.length} booking${data.bookings.length === 1 ? '' : 's'}: ` +
                data.bookings
                  .map((b) => `${b.service} ${new Date(b.start_time).toLocaleString([], { weekday: 'short', hour: 'numeric', minute: '2-digit' })}`)
                  .join(', ')}
          </p>
        </>
      )}
    </div>
  )
}
