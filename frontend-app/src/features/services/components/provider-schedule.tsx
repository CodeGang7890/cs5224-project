import { useEffect, useRef, useState } from 'react'
import { CalendarPlus, ChevronLeft, ChevronRight, Copy, CopyPlus, Paintbrush, Save, Undo2 } from 'lucide-react'
import { useSearchParams } from 'react-router'

import { ConfirmDialog } from '@/components/common/confirm-dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

import {
  EDITABLE_LETTERS,
  SLOT_META,
  addDays,
  applyEdits,
  formatWeek,
  hoursOf,
  isBooked,
  isIsoDay,
  mondayOf,
  today,
  weekDayLabels,
  type EditableLetter,
} from '../availability'
import { useCopyWeek, useSaveWeek, useWeekCalendar } from '../hooks/use-services'
import type { CalendarBooking, ServiceProvider } from '../types'
import { BookingBlockDialog } from './booking-block-dialog'
import { ROW_HEIGHT, ScheduleGrid, SlotLegend } from './schedule-grid'
import { describeChange } from '../schedule'
import { AddSlotsDialog, CopyWeekDialog } from './slot-dialogs'

const PROVIDER_PARAM = 'provider'
const WEEK_PARAM = 'week'
/** The grid opens scrolled to this hour. */
const SCROLL_TO_HOUR = 8

/** `?provider=` and `?week=` (any day; read as its Monday) of Catalog → Services. */
function useScheduleParams(providers: ServiceProvider[]) {
  const [searchParams, setSearchParams] = useSearchParams()
  const requested = Number(searchParams.get(PROVIDER_PARAM))
  const provider = providers.find((p) => p.id === requested) ?? providers[0] ?? null
  const rawWeek = searchParams.get(WEEK_PARAM) ?? ''
  const week = mondayOf(isIsoDay(rawWeek) ? rawWeek : today())

  const update = (changes: { provider?: number; week?: string }) =>
    setSearchParams(
      (params) => {
        if (changes.provider !== undefined) params.set(PROVIDER_PARAM, String(changes.provider))
        if (changes.week !== undefined) {
          if (changes.week === mondayOf(today())) params.delete(WEEK_PARAM)
          else params.set(WEEK_PARAM, changes.week)
        }
        return params
      },
      { replace: true },
    )
  return { provider, week, update }
}

interface Draft {
  /** The letters when editing started, and the edited ones. */
  base: string
  letters: string
}

/** Each service provider's schedule, a week at a time: see it, edit it, add slots, copy weeks, open bookings. */
export function ProviderSchedule({ providers }: { providers: ServiceProvider[] }) {
  const { provider, week, update } = useScheduleParams(providers)
  if (!provider) return null
  return <Schedule key={provider.id} provider={provider} providers={providers} week={week} update={update} />
}

function Schedule({
  provider,
  providers,
  week,
  update,
}: {
  provider: ServiceProvider
  providers: ServiceProvider[]
  week: string
  update: (changes: { provider?: number; week?: string }) => void
}) {
  const { data, isPending, isError, error, refetch, isPlaceholderData } = useWeekCalendar(provider.id, week)
  const saveWeek = useSaveWeek()
  const copy = useCopyWeek(provider.id)
  const [draft, setDraft] = useState<Draft | null>(null)
  const [brush, setBrush] = useState<EditableLetter>('O')
  const [notice, setNotice] = useState<{ text: string; error?: boolean } | null>(null)
  const [dialog, setDialog] = useState<'slots' | 'copy' | 'copy-previous' | 'save' | null>(null)
  const [booking, setBooking] = useState<CalendarBooking | null>(null)
  const scroller = useRef<HTMLDivElement>(null)
  const loaded = data !== undefined

  useEffect(() => {
    if (loaded && scroller.current) scroller.current.scrollTop = SCROLL_TO_HOUR * 4 * ROW_HEIGHT
  }, [loaded])

  const editing = draft !== null
  const shown = data && data.week === week ? data : undefined
  const letters = editing ? draft.letters : shown?.availability
  const toSave = editing && shown ? applyEdits(draft.base, draft.letters, shown.availability) : null
  const dirty = toSave !== null && shown !== undefined && toSave !== shown.availability
  const thisWeek = mondayOf(today())
  const todayColumn = week === thisWeek ? Math.round((Date.parse(today()) - Date.parse(week)) / 86_400_000) : undefined

  const goTo = (next: string) => {
    setNotice(null)
    update({ week: mondayOf(next) })
  }

  const startEditing = () => {
    if (!shown) return
    setNotice(null)
    setDraft({ base: shown.availability, letters: shown.availability })
  }

  const paintBlock = (index: number) =>
    setDraft((current) => {
      if (!current || current.letters[index] === brush || isBooked(current.letters[index])) return current
      return { ...current, letters: current.letters.slice(0, index) + brush + current.letters.slice(index + 1) }
    })

  const fillWeek = (letter: EditableLetter) =>
    setDraft((current) => current && { ...current, letters: current.letters.replace(/[OU]/g, letter) })

  const handleSave = () => {
    if (!shown || toSave === null) return
    saveWeek.mutate(
      { week: shown, availability: toSave },
      {
        onSuccess: () => {
          setDialog(null)
          setDraft(null)
          setNotice({ text: `Saved ${provider.name}'s week of ${formatWeek(week)}.` })
        },
        onError: (saveError) => {
          setDialog(null)
          setNotice({ text: `Couldn't save: ${saveError.message}`, error: true })
        },
      },
    )
  }

  const handleCopyPrevious = () =>
    copy.mutate(
      { source_week: addDays(week, -7), target_week: week, weeks: 1 },
      {
        onSuccess: (change) => {
          setDialog(null)
          setNotice({ text: `Copied the week of ${formatWeek(addDays(week, -7))} into this week. ${describeChange(change)}` })
        },
        onError: (copyError) => {
          setDialog(null)
          setNotice({ text: `Couldn't copy: ${copyError.message}`, error: true })
        },
      },
    )

  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap gap-1" role="tablist" aria-label="Service provider">
        {providers.map((p) => (
          <button
            key={p.id}
            type="button"
            role="tab"
            aria-selected={p.id === provider.id}
            disabled={editing && p.id !== provider.id}
            onClick={() => {
              setNotice(null)
              update({ provider: p.id })
            }}
            className={cn(
              'rounded-full border px-3 py-1 text-sm font-medium disabled:opacity-50',
              p.id === provider.id ? 'bg-primary text-primary-foreground border-primary' : 'hover:bg-muted',
            )}
          >
            {p.name}
            {!p.is_active && <span className="ml-1 text-xs font-normal opacity-75">(inactive)</span>}
          </button>
        ))}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-1">
          <Button type="button" size="icon" variant="outline" aria-label="Previous week" disabled={editing} onClick={() => goTo(addDays(week, -7))}>
            <ChevronLeft />
          </Button>
          <Button type="button" size="sm" variant="outline" disabled={editing || week === thisWeek} onClick={() => goTo(thisWeek)}>
            This week
          </Button>
          <Button type="button" size="icon" variant="outline" aria-label="Next week" disabled={editing} onClick={() => goTo(addDays(week, 7))}>
            <ChevronRight />
          </Button>
          <Input
            type="date"
            aria-label="Go to the week of"
            className="h-8 w-40"
            value={week}
            disabled={editing}
            onChange={(e) => isIsoDay(e.target.value) && goTo(e.target.value)}
          />
          <span className="ml-1 text-sm font-semibold">{formatWeek(week)}</span>
        </div>
        {!editing ? (
          <div className="flex flex-wrap gap-1">
            <Button type="button" size="sm" variant="outline" disabled={!shown} onClick={startEditing}>
              <Paintbrush /> Edit hours
            </Button>
            <Button type="button" size="sm" variant="outline" onClick={() => setDialog('slots')}>
              <CalendarPlus /> Add slots
            </Button>
            <Button type="button" size="sm" variant="outline" onClick={() => setDialog('copy-previous')}>
              <Copy /> Copy previous week
            </Button>
            <Button type="button" size="sm" variant="outline" disabled={!shown} onClick={() => setDialog('copy')}>
              <CopyPlus /> Copy to next weeks
            </Button>
          </div>
        ) : (
          <div className="flex flex-wrap items-center gap-1">
            <Button type="button" size="sm" variant="ghost" onClick={() => setDraft(null)}>
              <Undo2 /> {dirty ? 'Discard' : 'Done'}
            </Button>
            <Button type="button" size="sm" disabled={!dirty} onClick={() => setDialog('save')}>
              <Save /> Save week
            </Button>
          </div>
        )}
      </div>

      {editing && (
        <div className="bg-muted/30 flex flex-wrap items-center justify-between gap-2 rounded-lg border p-2 text-xs">
          <div className="flex items-center gap-1" role="radiogroup" aria-label="Paint with">
            <span className="text-muted-foreground mr-1">Click or drag to set blocks to:</span>
            {EDITABLE_LETTERS.map((letter) => (
              <Button
                key={letter}
                type="button"
                size="sm"
                variant={brush === letter ? 'default' : 'outline'}
                role="radio"
                aria-checked={brush === letter}
                onClick={() => setBrush(letter)}
              >
                <span className={cn('size-2.5 rounded-sm border', SLOT_META[letter].className)} /> {SLOT_META[letter].label}
              </Button>
            ))}
          </div>
          <div className="flex items-center gap-1">
            <Button type="button" size="sm" variant="ghost" onClick={() => fillWeek('U')}>
              Close the whole week
            </Button>
            <span className="text-muted-foreground">Booked blocks can't be changed.</span>
          </div>
        </div>
      )}

      {notice && (
        <p role={notice.error ? 'alert' : 'status'} className={cn('text-sm', notice.error ? 'text-destructive' : 'text-emerald-700 dark:text-emerald-400')}>
          {notice.text}
        </p>
      )}

      {isPending ? (
        <Skeleton className="h-96 w-full" />
      ) : isError && !data ? (
        <div className="border-destructive/50 flex flex-col items-start gap-3 rounded-lg border p-4">
          <p className="text-destructive text-sm">Couldn't load this week: {error.message}</p>
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            Try again
          </Button>
        </div>
      ) : (
        <>
          <div className="text-muted-foreground flex flex-wrap gap-x-4 gap-y-1 text-xs tabular-nums">
            {letters && (
              <>
                <span>{hoursOf(letters, 'O')} h available</span>
                <span>{hoursOf(letters, 'H')} h on hold</span>
                <span>{hoursOf(letters, 'X')} h booked</span>
              </>
            )}
            <span>
              {shown?.bookings.length ?? 0} booking{shown?.bookings.length === 1 ? '' : 's'} this week
            </span>
            {shown?.id === null && <span>Nothing set up for this week yet</span>}
          </div>
          <div
            ref={scroller}
            className={cn('max-h-[65svh] overflow-y-auto rounded-lg border p-2', (isPlaceholderData || !shown) && 'opacity-60')}
          >
            <ScheduleGrid
              availability={letters ?? data.availability}
              bookings={shown?.bookings ?? []}
              dayLabels={weekDayLabels(week)}
              todayColumn={todayColumn}
              onPaint={editing ? paintBlock : undefined}
              onBookingClick={setBooking}
              selectedBookingId={booking?.id}
            />
          </div>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <SlotLegend />
            <p className="text-muted-foreground text-xs">
              Times in {data.time_zone}. Click a booking to see who booked it.
            </p>
          </div>
        </>
      )}

      <BookingBlockDialog
        booking={booking}
        timeZone={data?.time_zone ?? 'UTC'}
        providerName={provider.name}
        onOpenChange={(open) => !open && setBooking(null)}
      />
      <AddSlotsDialog
        open={dialog === 'slots'}
        onOpenChange={(open) => !open && setDialog(null)}
        providerId={provider.id}
        providerName={provider.name}
        defaultFrom={week > today() ? week : today()}
        onDone={(text) => setNotice({ text })}
      />
      <CopyWeekDialog
        open={dialog === 'copy'}
        onOpenChange={(open) => !open && setDialog(null)}
        providerId={provider.id}
        providerName={provider.name}
        week={week}
        onDone={(text) => setNotice({ text })}
      />
      <ConfirmDialog
        open={dialog === 'copy-previous'}
        onOpenChange={(open) => !open && setDialog(null)}
        title="Copy the previous week?"
        description={
          <>
            This week ({formatWeek(week)}) of {provider.name}'s schedule will get the same open hours as the week of{' '}
            {formatWeek(addDays(week, -7))}. Booked times are left as they are.
          </>
        }
        confirmLabel="Copy"
        pendingLabel="Copying…"
        isPending={copy.isPending}
        onConfirm={handleCopyPrevious}
      />
      <ConfirmDialog
        open={dialog === 'save'}
        onOpenChange={(open) => !open && setDialog(null)}
        title="Save this week?"
        description={
          <>
            {provider.name} will be available {toSave ? hoursOf(toSave, 'O') : 0} hours in the week of {formatWeek(week)}.
            Bookings are kept.
          </>
        }
        confirmLabel="Save week"
        pendingLabel="Saving…"
        isPending={saveWeek.isPending}
        onConfirm={handleSave}
      />
    </div>
  )
}
