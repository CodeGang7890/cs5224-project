import { CircleAlert } from 'lucide-react'

import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Skeleton } from '@/components/ui/skeleton'
import { useDetailLabels } from '@/features/workflow'

import { useSchedule } from '../hooks/use-schedules'
import type { ScheduleItem } from '../types'
import { MarkCompletedButton } from './mark-completed-button'
import { OrderStatusBadge, SandboxBadge } from './order-status-badge'
import { formatBookingTime } from './schedule-format'

interface ScheduleDialogProps {
  /** The open booking's ID (from `?booking=`), or null when closed. */
  bookingId: number | null
  /** The booking, if it's on the current page (otherwise it's fetched by ID). */
  booking: ScheduleItem | undefined
  onClose: () => void
}

/** One booking: the service, when, with whom, the customer's details and status; a paid one can be marked as completed. */
export function ScheduleDialog({ bookingId, booking, onClose }: ScheduleDialogProps) {
  const fetched = useSchedule(bookingId, booking === undefined)
  const shown = booking ?? fetched.data

  return (
    <Dialog open={bookingId !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="flex max-h-[85svh] flex-col gap-4 sm:max-w-xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            Booking #{bookingId}
            {shown && <OrderStatusBadge status={shown.order_status} />}
            {shown?.is_sandbox && <SandboxBadge />}
          </DialogTitle>
          <DialogDescription>
            {shown ? `Booked ${new Date(shown.created_time).toLocaleString()}` : ' '}
          </DialogDescription>
        </DialogHeader>
        {shown ? (
          <>
            <BookingDetails booking={shown} />
            {shown.order_status === 'payment_received' && (
              <DialogFooter>
                <MarkCompletedButton kind="booking" id={shown.id} />
              </DialogFooter>
            )}
          </>
        ) : fetched.isError ? (
          <p role="alert" className="text-destructive flex items-center gap-2 text-sm">
            <CircleAlert className="size-4 shrink-0" />
            {fetched.error.status === 404
              ? "This booking doesn't exist."
              : fetched.error.status === 403
                ? "This booking belongs to another business, so you can't see it."
                : `Couldn't load the booking: ${fetched.error.message}`}
          </p>
        ) : (
          <div className="grid gap-2" aria-busy="true" aria-label="Loading booking">
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-16 w-full" />
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

function BookingDetails({ booking }: { booking: ScheduleItem }) {
  const labels = useDetailLabels('booking')
  const details = Object.entries(booking.schedule_data.details)
  const service = booking.schedule_data.service
  const rows = [
    { label: 'Service', value: service.name },
    { label: 'When', value: formatBookingTime(booking) },
    {
      label: 'Calendar blocked until',
      value: service.buffer_minutes
        ? `${new Date(booking.blocked_until).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })} (${service.buffer_minutes} min buffer)`
        : 'No buffer',
    },
    { label: 'With', value: booking.service_provider_name ?? 'Deleted service provider' },
    { label: 'Price', value: `$${booking.total}` },
  ]
  return (
    <div className="grid min-h-0 gap-4 overflow-y-auto">
      <dl className="grid gap-x-4 gap-y-2 rounded-lg border p-3 text-sm sm:grid-cols-2">
        {rows.map((row) => (
          <div key={row.label} className="grid min-w-0 gap-0.5">
            <dt className="text-muted-foreground text-xs">{row.label}</dt>
            <dd className="font-medium break-words">{row.value}</dd>
          </div>
        ))}
      </dl>

      <section className="grid gap-2">
        <h3 className="text-sm font-semibold">Customer details</h3>
        {details.length === 0 ? (
          <p className="text-muted-foreground text-sm">None collected.</p>
        ) : (
          <dl className="grid gap-x-4 gap-y-2 rounded-lg border p-3 text-sm sm:grid-cols-2">
            {details.map(([key, value]) => (
              <div key={key} className="grid min-w-0 gap-0.5">
                <dt className="text-muted-foreground text-xs">{labels[key] ?? key}</dt>
                <dd className="font-medium break-words">{String(value)}</dd>
              </div>
            ))}
          </dl>
        )}
      </section>

      <p className="text-muted-foreground text-xs">
        {booking.chat_session !== null ? `From chat #${booking.chat_session}` : 'The chat this came from was deleted.'} ·
        Last updated {new Date(booking.updated_time).toLocaleString()}
      </p>
    </div>
  )
}
