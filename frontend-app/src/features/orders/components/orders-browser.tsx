import { ChevronLeft, ChevronRight, CircleAlert, ReceiptText } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { NativeSelect } from '@/components/ui/native-select'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import type { DetailedPaginated } from '@/types/api'

import { ORDERING_OPTIONS, PAGE_SIZES, toListParams, useOrderParams } from '../hooks/use-order-params'
import { useOrders } from '../hooks/use-orders'
import { ORDER_STATUS_META } from '../status'
import { ORDER_STATUSES, type Order, type OrderOrdering, type OrderSandboxFilter, type OrderStatus } from '../types'
import { OrderDialog } from './order-dialog'
import { OrderTable } from './order-table'

/** Orders tab: every order of your business, read only, with filters, sorting and paging. */
export function OrdersBrowser() {
  const { values, setFilters, setPage, clearFilters, hasFilters, openOrderId, setOpenOrder } = useOrderParams()
  const { data, isPending, isError, error, refetch, isPlaceholderData } = useOrders(toListParams(values))
  const openOrder = data?.results.find((order) => order.id === openOrderId)

  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-end gap-3 rounded-xl border p-3">
        <FilterSelect
          id="order-status"
          label="Status"
          value={values.status}
          onChange={(status) => setFilters({ status: status as OrderStatus | '' })}
          options={[
            { value: '', label: 'All statuses' },
            ...ORDER_STATUSES.map((status) => ({ value: status, label: ORDER_STATUS_META[status].label })),
          ]}
        />
        <FilterSelect
          id="order-sandbox"
          label="Orders"
          value={values.sandbox}
          onChange={(sandbox) => setFilters({ sandbox: sandbox as OrderSandboxFilter })}
          options={[
            { value: 'include', label: 'Customer + sandbox' },
            { value: 'exclude', label: 'Customer orders' },
            { value: 'only', label: 'Sandbox only' },
          ]}
        />
        <FilterSelect
          id="order-sort"
          label="Sort by"
          value={values.ordering}
          onChange={(ordering) => setFilters({ ordering: ordering as OrderOrdering })}
          options={ORDERING_OPTIONS}
        />
        {hasFilters && (
          <Button variant="ghost" size="sm" onClick={clearFilters}>
            Clear filters
          </Button>
        )}
      </div>

      {isPending ? (
        <div className="grid gap-2" aria-busy="true" aria-label="Loading orders">
          {Array.from({ length: 6 }, (_, i) => (
            <Skeleton key={i} className="h-12 w-full" />
          ))}
        </div>
      ) : isError && !data ? (
        <ErrorState status={error.status} message={error.message} onRetry={refetch} onFirstPage={() => setPage(1)} />
      ) : data.results.length === 0 ? (
        <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed p-10 text-center">
          <ReceiptText className="text-muted-foreground size-10" />
          <p className="font-medium">{hasFilters ? 'No orders match these filters' : 'No orders yet'}</p>
          <p className="text-muted-foreground text-sm">
            {hasFilters
              ? 'Try removing some filters.'
              : 'Orders appear here when customers confirm an order in a chat (sandbox chats included).'}
          </p>
          {hasFilters && (
            <Button variant="outline" onClick={clearFilters}>
              Clear filters
            </Button>
          )}
        </div>
      ) : (
        <div className={cn('grid gap-3', isPlaceholderData && 'opacity-60 transition-opacity')}>
          <OrderTable orders={data.results} onOpen={setOpenOrder} />
          <PaginationBar
            data={data}
            disabled={isPlaceholderData}
            onPageChange={setPage}
            onPageSizeChange={(pageSize) => setFilters({ pageSize })}
          />
        </div>
      )}

      <OrderDialog orderId={openOrderId} order={openOrder} onClose={() => setOpenOrder(null)} />
    </div>
  )
}

function FilterSelect({
  id,
  label,
  value,
  onChange,
  options,
}: {
  id: string
  label: string
  value: string
  onChange: (value: string) => void
  options: { value: string; label: string }[]
}) {
  return (
    <div className="grid gap-1.5">
      <Label htmlFor={id} className="text-muted-foreground text-xs font-normal">
        {label}
      </Label>
      <NativeSelect id={id} className="w-48" value={value} onChange={(event) => onChange(event.target.value)}>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </NativeSelect>
    </div>
  )
}

function PaginationBar({
  data,
  disabled,
  onPageChange,
  onPageSizeChange,
}: {
  data: DetailedPaginated<Order>
  disabled: boolean
  onPageChange: (page: number) => void
  onPageSizeChange: (pageSize: number) => void
}) {
  const first = (data.current_page - 1) * data.page_size + 1
  const last = first + data.results.length - 1
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
      <div className="flex items-center gap-3">
        <span className="text-muted-foreground tabular-nums">
          {first}–{last} of {data.count} order{data.count === 1 ? '' : 's'}
        </span>
        <div className="flex items-center gap-2">
          <Label htmlFor="order-page-size" className="text-muted-foreground text-xs font-normal">
            Per page
          </Label>
          <NativeSelect
            id="order-page-size"
            className="w-20"
            value={data.page_size}
            onChange={(event) => onPageSizeChange(Number(event.target.value))}
          >
            {PAGE_SIZES.map((size) => (
              <option key={size} value={size}>
                {size}
              </option>
            ))}
          </NativeSelect>
        </div>
      </div>
      <div className="flex items-center gap-2">
        <Button variant="outline" size="sm" disabled={disabled || !data.has_previous} onClick={() => onPageChange(data.current_page - 1)}>
          <ChevronLeft /> Previous
        </Button>
        <span className="tabular-nums">
          Page {data.current_page} of {data.total_pages}
        </span>
        <Button variant="outline" size="sm" disabled={disabled || !data.has_next} onClick={() => onPageChange(data.current_page + 1)}>
          Next <ChevronRight />
        </Button>
      </div>
    </div>
  )
}

function ErrorState({
  status,
  message,
  onRetry,
  onFirstPage,
}: {
  status?: number
  message: string
  onRetry: () => void
  onFirstPage: () => void
}) {
  // 403: no business; 404: a page past the end (e.g. an old link).
  const text =
    status === 403
      ? "Your account isn't linked to a business, so there are no orders to show."
      : status === 404
        ? "That page doesn't exist any more."
        : `Couldn't load orders: ${message}`
  return (
    <div className="border-destructive/50 flex flex-col items-start gap-3 rounded-xl border p-4">
      <p className="text-destructive flex items-center gap-2 text-sm">
        <CircleAlert className="size-4" /> {text}
      </p>
      {status === 404 ? (
        <Button variant="outline" size="sm" onClick={onFirstPage}>
          Go to the first page
        </Button>
      ) : (
        status !== 403 && (
          <Button variant="outline" size="sm" onClick={() => onRetry()}>
            Try again
          </Button>
        )
      )}
    </div>
  )
}
