import { CalendarClock } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

import { SCHEDULE_ORDERING_OPTIONS, toScheduleListParams, useScheduleParams } from '../hooks/use-schedule-params'
import { useSchedules } from '../hooks/use-schedules'
import { ORDER_STATUS_META } from '../status'
import { ORDER_STATUSES, type OrderSandboxFilter, type OrderStatus, type ScheduleOrdering } from '../types'
import { ErrorState, FilterSelect, PaginationBar } from './list-controls'
import { ScheduleDialog } from './schedule-dialog'
import { ScheduleTable } from './schedule-table'

/** The Orders tab's Services sub-tab: every booked time slot of your business, read only. */
export function SchedulesBrowser() {
  const { values, setFilters, setPage, clearFilters, hasFilters, openBookingId, setOpenBooking } = useScheduleParams()
  const { data, isPending, isError, error, refetch, isPlaceholderData } = useSchedules(toScheduleListParams(values))
  const openBooking = data?.results.find((booking) => booking.id === openBookingId)

  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-end gap-3 rounded-xl border p-3">
        <FilterSelect
          id="schedule-status"
          label="Status"
          value={values.status}
          onChange={(status) => setFilters({ status: status as OrderStatus | '' })}
          options={[
            { value: '', label: 'All statuses' },
            ...ORDER_STATUSES.map((status) => ({ value: status, label: ORDER_STATUS_META[status].label })),
          ]}
        />
        <FilterSelect
          id="schedule-sandbox"
          label="Bookings"
          value={values.sandbox}
          onChange={(sandbox) => setFilters({ sandbox: sandbox as OrderSandboxFilter })}
          options={[
            { value: 'include', label: 'Customer + sandbox' },
            { value: 'exclude', label: 'Customer bookings' },
            { value: 'only', label: 'Sandbox only' },
          ]}
        />
        <FilterSelect
          id="schedule-sort"
          label="Sort by"
          value={values.ordering}
          onChange={(ordering) => setFilters({ ordering: ordering as ScheduleOrdering })}
          options={SCHEDULE_ORDERING_OPTIONS}
        />
        {hasFilters && (
          <Button variant="ghost" size="sm" onClick={clearFilters}>
            Clear filters
          </Button>
        )}
      </div>

      {isPending ? (
        <div className="grid gap-2" aria-busy="true" aria-label="Loading bookings">
          {Array.from({ length: 6 }, (_, i) => (
            <Skeleton key={i} className="h-12 w-full" />
          ))}
        </div>
      ) : isError && !data ? (
        <ErrorState noun="bookings" status={error.status} message={error.message} onRetry={refetch} onFirstPage={() => setPage(1)} />
      ) : data.results.length === 0 ? (
        <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed p-10 text-center">
          <CalendarClock className="text-muted-foreground size-10" />
          <p className="font-medium">{hasFilters ? 'No bookings match these filters' : 'No bookings yet'}</p>
          <p className="text-muted-foreground text-sm">
            {hasFilters
              ? 'Try removing some filters.'
              : 'Bookings appear here when customers book a time for a service in a chat (sandbox chats included).'}
          </p>
          {hasFilters && (
            <Button variant="outline" onClick={clearFilters}>
              Clear filters
            </Button>
          )}
        </div>
      ) : (
        <div className={cn('grid gap-3', isPlaceholderData && 'opacity-60 transition-opacity')}>
          <ScheduleTable bookings={data.results} onOpen={setOpenBooking} />
          <PaginationBar
            id="schedule-page-size"
            noun="booking"
            data={data}
            disabled={isPlaceholderData}
            onPageChange={setPage}
            onPageSizeChange={(pageSize) => setFilters({ pageSize })}
          />
        </div>
      )}

      <ScheduleDialog bookingId={openBookingId} booking={openBooking} onClose={() => setOpenBooking(null)} />
    </div>
  )
}
