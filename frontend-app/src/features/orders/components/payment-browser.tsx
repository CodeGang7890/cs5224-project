import { CalendarClock, ExternalLink, Eye, ReceiptText } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { cn } from '@/lib/utils'

import { shortPaymentReference } from '../payment-reference'
import { usePaymentParams } from '../hooks/use-payment-params'
import { useOrders } from '../hooks/use-orders'
import { useSchedules } from '../hooks/use-schedules'
import { ORDER_STATUS_META } from '../status'
import { ORDER_STATUSES, type Order, type OrderSandboxFilter, type OrderStatus } from '../types'
import { ErrorState, FilterSelect, PaginationBar } from './list-controls'
import { OrderDialog } from './order-dialog'
import { OrderStatusBadge, SandboxBadge } from './order-status-badge'
import { bookingCustomer, formatBookingTime } from './schedule-format'
import { ScheduleDialog } from './schedule-dialog'

const formatDateTime = (iso: string) =>
  new Date(iso).toLocaleString([], { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })

function orderCustomer(order: Order): string | null {
  const { name, email } = order.order_data.details
  return (typeof name === 'string' && name) || (typeof email === 'string' && email) || null
}

function PaymentLinkCell({ link }: { link: string | null }) {
  if (!link) {
    return <span className="text-muted-foreground text-sm">No link yet</span>
  }
  return (
    <Button type="button" variant="ghost" size="sm" className="gap-1.5" asChild>
      <a href={link} target="_blank" rel="noreferrer">
        Open link <ExternalLink className="size-3.5" />
      </a>
    </Button>
  )
}

function OrdersSection({
  status,
  sandbox,
  page,
  pageSize,
  onPageChange,
  onPageSizeChange,
  openOrderId,
  onOpenOrder,
}: {
  status: OrderStatus | ''
  sandbox: OrderSandboxFilter
  page: number
  pageSize: number
  onPageChange: (page: number) => void
  onPageSizeChange: (pageSize: number) => void
  openOrderId: number | null
  onOpenOrder: (id: number | null) => void
}) {
  const params = { page, page_size: pageSize, ordering: '-created_time' as const, sandbox, order_status: status || undefined }
  const { data, isPending, isError, error, refetch, isPlaceholderData } = useOrders(params)
  const openOrder = data?.results.find((order) => order.id === openOrderId)

  return (
    <section className="grid gap-3">
      <h2 className="flex items-center gap-2 text-sm font-semibold">
        <ReceiptText className="size-4" /> Product orders
      </h2>
      {isPending ? (
        <div className="grid gap-2" aria-busy="true" aria-label="Loading product orders">
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="h-12 w-full" />
          ))}
        </div>
      ) : isError && !data ? (
        <ErrorState noun="orders" status={error.status} message={error.message} onRetry={refetch} onFirstPage={() => onPageChange(1)} />
      ) : data.results.length === 0 ? (
        <div className="rounded-xl border border-dashed p-6 text-center">
          <p className="text-muted-foreground text-sm">No product orders match these filters.</p>
        </div>
      ) : (
        <div className={cn('grid gap-3', isPlaceholderData && 'opacity-60 transition-opacity')}>
          <div className="rounded-xl border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="pl-4">Order</TableHead>
                  <TableHead>Customer</TableHead>
                  <TableHead className="text-right">Total</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Payment link</TableHead>
                  <TableHead>Updated</TableHead>
                  <TableHead className="w-12">
                    <span className="sr-only">Actions</span>
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.results.map((order) => (
                  <TableRow key={order.id} className="cursor-pointer" onClick={() => onOpenOrder(order.id)}>
                    <TableCell className="pl-4">
                      <div className="flex items-center gap-2">
                        <span className="font-medium tabular-nums">#{order.id}</span>
                        {order.is_sandbox && <SandboxBadge />}
                      </div>
                      <p className="text-muted-foreground font-mono text-xs" title={`Payment reference ${order.payment_reference}`}>
                        {shortPaymentReference(order.payment_reference)}
                      </p>
                    </TableCell>
                    <TableCell>{orderCustomer(order) ?? <span className="text-muted-foreground">—</span>}</TableCell>
                    <TableCell className="text-right font-medium tabular-nums">${order.total}</TableCell>
                    <TableCell>
                      <OrderStatusBadge status={order.order_status} />
                    </TableCell>
                    <TableCell>
                      <PaymentLinkCell link={order.payment_link} />
                    </TableCell>
                    <TableCell className="whitespace-nowrap tabular-nums">{formatDateTime(order.updated_time)}</TableCell>
                    <TableCell>
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        aria-label={`View order #${order.id}`}
                        onClick={(event) => {
                          event.stopPropagation()
                          onOpenOrder(order.id)
                        }}
                      >
                        <Eye />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          <PaginationBar
            id="payment-order-page-size"
            noun="order"
            data={data}
            disabled={isPlaceholderData}
            onPageChange={onPageChange}
            onPageSizeChange={onPageSizeChange}
          />
        </div>
      )}
      <OrderDialog orderId={openOrderId} order={openOrder} onClose={() => onOpenOrder(null)} />
    </section>
  )
}

function BookingsSection({
  status,
  sandbox,
  page,
  pageSize,
  onPageChange,
  onPageSizeChange,
  openBookingId,
  onOpenBooking,
}: {
  status: OrderStatus | ''
  sandbox: OrderSandboxFilter
  page: number
  pageSize: number
  onPageChange: (page: number) => void
  onPageSizeChange: (pageSize: number) => void
  openBookingId: number | null
  onOpenBooking: (id: number | null) => void
}) {
  const params = { page, page_size: pageSize, ordering: '-start_time' as const, sandbox, order_status: status || undefined }
  const { data, isPending, isError, error, refetch, isPlaceholderData } = useSchedules(params)
  const openBooking = data?.results.find((booking) => booking.id === openBookingId)

  return (
    <section className="grid gap-3">
      <h2 className="flex items-center gap-2 text-sm font-semibold">
        <CalendarClock className="size-4" /> Service bookings
      </h2>
      {isPending ? (
        <div className="grid gap-2" aria-busy="true" aria-label="Loading service bookings">
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="h-12 w-full" />
          ))}
        </div>
      ) : isError && !data ? (
        <ErrorState noun="bookings" status={error.status} message={error.message} onRetry={refetch} onFirstPage={() => onPageChange(1)} />
      ) : data.results.length === 0 ? (
        <div className="rounded-xl border border-dashed p-6 text-center">
          <p className="text-muted-foreground text-sm">No service bookings match these filters.</p>
        </div>
      ) : (
        <div className={cn('grid gap-3', isPlaceholderData && 'opacity-60 transition-opacity')}>
          <div className="rounded-xl border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="pl-4">Booking</TableHead>
                  <TableHead>Customer</TableHead>
                  <TableHead>Service</TableHead>
                  <TableHead className="text-right">Total</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Payment link</TableHead>
                  <TableHead>Updated</TableHead>
                  <TableHead className="w-12">
                    <span className="sr-only">Actions</span>
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.results.map((booking) => (
                  <TableRow key={booking.id} className="cursor-pointer" onClick={() => onOpenBooking(booking.id)}>
                    <TableCell className="pl-4">
                      <div className="flex items-center gap-2">
                        <span className="font-medium tabular-nums">#{booking.id}</span>
                        {booking.is_sandbox && <SandboxBadge />}
                      </div>
                      <p className="text-muted-foreground font-mono text-xs" title={`Payment reference ${booking.payment_reference}`}>
                        {shortPaymentReference(booking.payment_reference)}
                      </p>
                    </TableCell>
                    <TableCell>{bookingCustomer(booking) ?? <span className="text-muted-foreground">—</span>}</TableCell>
                    <TableCell className="max-w-0">
                      <p className="truncate" title={booking.schedule_data.service.name}>
                        {booking.schedule_data.service.name}
                      </p>
                      <p className="text-muted-foreground text-xs">{formatBookingTime(booking)}</p>
                    </TableCell>
                    <TableCell className="text-right font-medium tabular-nums">${booking.total}</TableCell>
                    <TableCell>
                      <OrderStatusBadge status={booking.order_status} />
                    </TableCell>
                    <TableCell>
                      <PaymentLinkCell link={booking.payment_link} />
                    </TableCell>
                    <TableCell className="whitespace-nowrap tabular-nums">{formatDateTime(booking.updated_time)}</TableCell>
                    <TableCell>
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        aria-label={`View booking #${booking.id}`}
                        onClick={(event) => {
                          event.stopPropagation()
                          onOpenBooking(booking.id)
                        }}
                      >
                        <Eye />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          <PaginationBar
            id="payment-booking-page-size"
            noun="booking"
            data={data}
            disabled={isPlaceholderData}
            onPageChange={onPageChange}
            onPageSizeChange={onPageSizeChange}
          />
        </div>
      )}
      <ScheduleDialog bookingId={openBookingId} booking={openBooking} onClose={() => onOpenBooking(null)} />
    </section>
  )
}

/** Orders → Payment: the business's orders and bookings, with their payment status and Xendit links. */
export function PaymentBrowser() {
  const {
    values,
    setFilters,
    setOrderPage,
    setOrderPageSize,
    setBookingPage,
    setBookingPageSize,
    clearFilters,
    hasFilters,
    openOrderId,
    setOpenOrder,
    openBookingId,
    setOpenBooking,
  } = usePaymentParams()

  return (
    <div className="grid gap-6">
      <div className="flex flex-wrap items-end gap-3 rounded-xl border p-3">
        <FilterSelect
          id="payment-status"
          label="Status"
          value={values.status}
          onChange={(status) => setFilters({ status: status as OrderStatus | '' })}
          options={[
            { value: '', label: 'All statuses' },
            ...ORDER_STATUSES.map((status) => ({ value: status, label: ORDER_STATUS_META[status].label })),
          ]}
        />
        <FilterSelect
          id="payment-sandbox"
          label="Payments"
          value={values.sandbox}
          onChange={(sandbox) => setFilters({ sandbox: sandbox as OrderSandboxFilter })}
          options={[
            { value: 'include', label: 'Customer + sandbox' },
            { value: 'exclude', label: 'Customer payments' },
            { value: 'only', label: 'Sandbox only' },
          ]}
        />
        {hasFilters && (
          <Button variant="ghost" size="sm" onClick={clearFilters}>
            Clear filters
          </Button>
        )}
      </div>

      <OrdersSection
        status={values.status}
        sandbox={values.sandbox}
        page={values.orderPage}
        pageSize={values.orderPageSize}
        onPageChange={setOrderPage}
        onPageSizeChange={setOrderPageSize}
        openOrderId={openOrderId}
        onOpenOrder={setOpenOrder}
      />
      <BookingsSection
        status={values.status}
        sandbox={values.sandbox}
        page={values.bookingPage}
        pageSize={values.bookingPageSize}
        onPageChange={setBookingPage}
        onPageSizeChange={setBookingPageSize}
        openBookingId={openBookingId}
        onOpenBooking={setOpenBooking}
      />
    </div>
  )
}
