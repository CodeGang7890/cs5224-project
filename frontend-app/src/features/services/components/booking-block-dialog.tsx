import { ExternalLink } from 'lucide-react'
import { Link } from 'react-router'

import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { paths } from '@/config/navigation'
import { OrderStatusBadge, SandboxBadge } from '@/features/orders'
import { useDetailLabels } from '@/features/workflow'

import type { CalendarBooking } from '../types'

interface BookingBlockDialogProps {
  booking: CalendarBooking | null
  /** The schedule's time zone (the times are shown in it, like the grid). */
  timeZone: string
  providerName: string
  onOpenChange: (open: boolean) => void
}

/** Who booked a block of a provider's schedule, and the booking's status. */
export function BookingBlockDialog({ booking, timeZone, providerName, onOpenChange }: BookingBlockDialogProps) {
  return (
    <Dialog open={booking !== null} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        {booking && <BookingSummary booking={booking} timeZone={timeZone} providerName={providerName} />}
      </DialogContent>
    </Dialog>
  )
}

function BookingSummary({ booking, timeZone, providerName }: { booking: CalendarBooking; timeZone: string; providerName: string }) {
  const labels = useDetailLabels('booking')
  const time = (iso: string) => new Date(iso).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit', timeZone })
  const day = new Date(booking.start_time).toLocaleDateString([], {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    timeZone,
  })
  const hasBuffer = booking.blocked_until !== booking.end_time
  const details = Object.entries(booking.details)
  const chatLink =
    booking.chat_session === null
      ? null
      : booking.is_sandbox
        ? `${paths.chatSandbox}?session=${booking.chat_session}`
        : `${paths.conversations}?chat=${booking.chat_session}`

  return (
    <>
      <DialogHeader>
        <DialogTitle className="flex flex-wrap items-center gap-2">
          Booking #{booking.id}
          <OrderStatusBadge status={booking.order_status} />
          {booking.is_sandbox && <SandboxBadge />}
        </DialogTitle>
        <DialogDescription>
          {booking.order_status === 'pending_payment'
            ? 'Not paid yet: its time is on hold (H) until it is.'
            : 'Paid: its time is booked (X).'}
        </DialogDescription>
      </DialogHeader>

      <dl className="grid gap-x-4 gap-y-2 rounded-lg border p-3 text-sm sm:grid-cols-2">
        <Row label="Customer" value={booking.customer ?? 'No name given'} />
        <Row label="Service" value={booking.service} />
        <Row label="When" value={`${day}, ${time(booking.start_time)} – ${time(booking.end_time)}`} />
        <Row label="Blocked until" value={hasBuffer ? `${time(booking.blocked_until)} (buffer)` : 'No buffer'} />
        <Row label="With" value={providerName} />
        <Row label="Total" value={`$${booking.total}`} />
      </dl>

      <section className="grid gap-2">
        <h3 className="text-sm font-semibold">Customer details</h3>
        {details.length === 0 ? (
          <p className="text-muted-foreground text-sm">None collected.</p>
        ) : (
          <dl className="grid gap-x-4 gap-y-2 rounded-lg border p-3 text-sm sm:grid-cols-2">
            {details.map(([key, value]) => (
              <Row key={key} label={labels[key] ?? key} value={String(value)} />
            ))}
          </dl>
        )}
      </section>

      <DialogFooter className="gap-2 sm:justify-between">
        {chatLink ? (
          <Button asChild variant="ghost" size="sm">
            <Link to={chatLink}>Open chat #{booking.chat_session}</Link>
          </Button>
        ) : (
          <span className="text-muted-foreground self-center text-xs">The chat it came from was deleted.</span>
        )}
        <Button asChild variant="outline" size="sm">
          <Link to={`${paths.serviceOrders}?booking=${booking.id}`}>
            Open in Orders <ExternalLink />
          </Link>
        </Button>
      </DialogFooter>
    </>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid min-w-0 gap-0.5">
      <dt className="text-muted-foreground text-xs">{label}</dt>
      <dd className="font-medium break-words">{value}</dd>
    </div>
  )
}
