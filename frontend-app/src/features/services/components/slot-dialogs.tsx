import { type FormEvent, useState } from 'react'

import { ConfirmDialog } from '@/components/common/confirm-dialog'
import { FormField } from '@/components/common/form-field'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { NativeSelect } from '@/components/ui/native-select'
import { type FormErrors, getFormErrors } from '@/lib/form-errors'
import { cn } from '@/lib/utils'

import { DAYS, SLOTS_PER_DAY, WEEKS_CHANGED_MAX, addDays, formatDay, formatWeek, slotTime } from '../availability'
import { useCopyWeek, useSetSlots } from '../hooks/use-services'
import { describeChange, describeWeekdays } from '../schedule'
import type { SetSlotsInput } from '../types'
import { validateSlots } from '../validation'

const WEEKDAY_PRESETS = [
  { label: 'Mon–Fri', days: [0, 1, 2, 3, 4] },
  { label: 'Weekends', days: [5, 6] },
  { label: 'Every day', days: [0, 1, 2, 3, 4, 5, 6] },
]

const RANGE_PRESETS = [1, 2, 4, 8]

interface AddSlotsDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  providerId: number
  providerName: string
  /** The first day the form starts from. */
  defaultFrom: string
  onDone: (message: string) => void
}

/** Opens (or closes) the same times on some days over a range of dates, e.g. the next 2 weeks Mon–Fri 9–5. */
export function AddSlotsDialog({ open, onOpenChange, ...props }: AddSlotsDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">{open && <AddSlotsForm {...props} onClose={() => onOpenChange(false)} />}</DialogContent>
    </Dialog>
  )
}

function AddSlotsForm({
  providerId,
  providerName,
  defaultFrom,
  onDone,
  onClose,
}: Omit<AddSlotsDialogProps, 'open' | 'onOpenChange'> & { onClose: () => void }) {
  const setSlots = useSetSlots(providerId)
  const [values, setValues] = useState<SetSlotsInput>({
    date_from: defaultFrom,
    date_to: addDays(defaultFrom, 13),
    weekdays: [0, 1, 2, 3, 4],
    time_from: '09:00',
    time_to: '17:00',
    available: true,
  })
  const [errors, setErrors] = useState<FormErrors>({ fields: {} })
  const [confirmOpen, setConfirmOpen] = useState(false)

  const set = <K extends keyof SetSlotsInput>(key: K, value: SetSlotsInput[K]) => {
    setValues((current) => ({ ...current, [key]: value }))
    setErrors((current) => ({ ...current, fields: { ...current.fields, [key]: '' } }))
  }
  const toggleDay = (day: number) =>
    set('weekdays', values.weekdays.includes(day) ? values.weekdays.filter((d) => d !== day) : [...values.weekdays, day])
  const field = (key: keyof SetSlotsInput) => errors.fields[key] || undefined
  const verb = values.available ? 'Open' : 'Close'
  const summary = `${values.time_from}–${values.time_to}, ${describeWeekdays(values.weekdays)}, from ${formatDay(values.date_from)} to ${formatDay(values.date_to, true)}`

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const fieldErrors = validateSlots(values)
    setErrors({ fields: fieldErrors as Record<string, string> })
    if (Object.keys(fieldErrors).length === 0) setConfirmOpen(true)
  }

  const handleConfirm = () => {
    setSlots.mutate(values, {
      onSuccess: (change) => {
        setConfirmOpen(false)
        onClose()
        onDone(`${verb === 'Open' ? 'Opened' : 'Closed'} ${summary} for ${providerName}. ${describeChange(change)}`)
      },
      onError: (error) => {
        setConfirmOpen(false)
        setErrors(getFormErrors(error))
      },
    })
  }

  return (
    <>
      <form onSubmit={handleSubmit} noValidate className="grid gap-4">
        <DialogHeader>
          <DialogTitle>Add slots for {providerName}</DialogTitle>
          <DialogDescription>
            Open the same hours on some days of the week, over a range of dates (or close them, e.g. for a holiday).
            Booked times are never changed.
          </DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-2 gap-1 rounded-lg border p-1" role="radiogroup" aria-label="Open or close">
          {[true, false].map((available) => (
            <button
              key={String(available)}
              type="button"
              role="radio"
              aria-checked={values.available === available}
              onClick={() => set('available', available)}
              className={cn(
                'rounded-md px-3 py-1.5 text-sm font-medium',
                values.available === available ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-muted',
              )}
            >
              {available ? 'Open (available)' : 'Close (unavailable)'}
            </button>
          ))}
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <FormField id="slots-from" label="From" error={field('date_from')}>
            <Input id="slots-from" type="date" value={values.date_from} onChange={(e) => set('date_from', e.target.value)} />
          </FormField>
          <FormField id="slots-to" label="To (inclusive)" error={field('date_to')}>
            <Input id="slots-to" type="date" value={values.date_to} min={values.date_from} onChange={(e) => set('date_to', e.target.value)} />
          </FormField>
        </div>
        <div className="-mt-2 flex flex-wrap items-center gap-1 text-xs">
          <span className="text-muted-foreground mr-1">For:</span>
          {RANGE_PRESETS.map((weeks) => (
            <Button key={weeks} type="button" size="sm" variant="ghost" className="h-7" onClick={() => set('date_to', addDays(values.date_from, 7 * weeks - 1))}>
              {weeks} week{weeks === 1 ? '' : 's'}
            </Button>
          ))}
        </div>

        <fieldset className="grid gap-2">
          <legend className="text-sm font-medium">Days</legend>
          <div className="flex flex-wrap gap-1">
            {DAYS.map((label, day) => (
              <button
                key={label}
                type="button"
                aria-pressed={values.weekdays.includes(day)}
                onClick={() => toggleDay(day)}
                className={cn(
                  'w-12 rounded-md border py-1 text-sm',
                  values.weekdays.includes(day) ? 'bg-primary text-primary-foreground border-primary' : 'hover:bg-muted',
                )}
              >
                {label}
              </button>
            ))}
          </div>
          <div className="flex flex-wrap gap-1">
            {WEEKDAY_PRESETS.map((preset) => (
              <Button key={preset.label} type="button" size="sm" variant="ghost" className="h-7 text-xs" onClick={() => set('weekdays', preset.days)}>
                {preset.label}
              </Button>
            ))}
          </div>
          {field('weekdays') && <p className="text-destructive text-xs">{field('weekdays')}</p>}
        </fieldset>

        <div className="grid gap-3 sm:grid-cols-2">
          <FormField id="slots-time-from" label="From time" error={field('time_from')}>
            <TimeSelect id="slots-time-from" value={values.time_from} onChange={(v) => set('time_from', v)} from={0} to={SLOTS_PER_DAY - 1} />
          </FormField>
          <FormField id="slots-time-to" label="Until" error={field('time_to')}>
            <TimeSelect id="slots-time-to" value={values.time_to} onChange={(v) => set('time_to', v)} from={1} to={SLOTS_PER_DAY} />
          </FormField>
        </div>

        {errors.form && (
          <p role="alert" className="text-destructive text-sm">
            {errors.form}
          </p>
        )}

        <DialogFooter>
          <Button type="button" variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit">{verb} these times</Button>
        </DialogFooter>
      </form>

      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title={`${verb} these times?`}
        description={
          <>
            {verb} <strong>{summary}</strong> for {providerName}. Booked times are left as they are.
          </>
        }
        confirmLabel={`${verb} times`}
        pendingLabel="Saving…"
        isPending={setSlots.isPending}
        onConfirm={handleConfirm}
      />
    </>
  )
}

function TimeSelect({ id, value, onChange, from, to }: { id: string; value: string; onChange: (value: string) => void; from: number; to: number }) {
  return (
    <NativeSelect id={id} value={value} onChange={(e) => onChange(e.target.value)}>
      {Array.from({ length: to - from + 1 }, (_, i) => slotTime(from + i)).map((time) => (
        <option key={time} value={time}>
          {time}
        </option>
      ))}
    </NativeSelect>
  )
}

interface CopyWeekDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  providerId: number
  providerName: string
  /** The Monday of the week to copy. */
  week: string
  onDone: (message: string) => void
}

/** Copies a week's open / closed hours to the next N weeks. */
export function CopyWeekDialog({ open, onOpenChange, ...props }: CopyWeekDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">{open && <CopyWeekForm {...props} onClose={() => onOpenChange(false)} />}</DialogContent>
    </Dialog>
  )
}

function CopyWeekForm({
  providerId,
  providerName,
  week,
  onDone,
  onClose,
}: Omit<CopyWeekDialogProps, 'open' | 'onOpenChange'> & { onClose: () => void }) {
  const copy = useCopyWeek(providerId)
  const [weeks, setWeeks] = useState('4')
  const [errors, setErrors] = useState<FormErrors>({ fields: {} })
  const [confirmOpen, setConfirmOpen] = useState(false)
  const count = Number(weeks)
  const last = addDays(week, 7 * count)

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const valid = Number.isInteger(count) && count >= 1 && count <= WEEKS_CHANGED_MAX
    setErrors({ fields: valid ? {} : { weeks: `Enter 1 to ${WEEKS_CHANGED_MAX} weeks.` } })
    if (valid) setConfirmOpen(true)
  }

  const handleConfirm = () => {
    copy.mutate(
      { source_week: week, weeks: count },
      {
        onSuccess: (change) => {
          setConfirmOpen(false)
          onClose()
          onDone(`Copied the week of ${formatWeek(week)} to the next ${count} week${count === 1 ? '' : 's'}. ${describeChange(change)}`)
        },
        onError: (error) => {
          setConfirmOpen(false)
          setErrors(getFormErrors(error))
        },
      },
    )
  }

  return (
    <>
      <form onSubmit={handleSubmit} noValidate className="grid gap-4">
        <DialogHeader>
          <DialogTitle>Copy this week to the next weeks</DialogTitle>
          <DialogDescription>
            {providerName}'s open and closed hours of {formatWeek(week)} replace those of the following weeks (booked
            times count as open). Bookings in those weeks are kept.
          </DialogDescription>
        </DialogHeader>
        <FormField
          id="copy-weeks"
          label="Number of weeks"
          error={errors.fields.weeks || undefined}
          hint={Number.isInteger(count) && count >= 1 ? `Up to the week of ${formatWeek(last)}.` : undefined}
        >
          <Input id="copy-weeks" type="number" min={1} max={WEEKS_CHANGED_MAX} value={weeks} onChange={(e) => setWeeks(e.target.value)} autoFocus />
        </FormField>
        {errors.form && (
          <p role="alert" className="text-destructive text-sm">
            {errors.form}
          </p>
        )}
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit">Copy</Button>
        </DialogFooter>
      </form>
      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title="Copy this week?"
        description={
          <>
            The next <strong>{count} week{count === 1 ? '' : 's'}</strong> of {providerName}'s schedule (to{' '}
            {formatWeek(last)}) will get the same open hours as {formatWeek(week)}. Booked times are left as they are.
          </>
        }
        confirmLabel="Copy"
        pendingLabel="Copying…"
        isPending={copy.isPending}
        onConfirm={handleConfirm}
      />
    </>
  )
}
