import { ReceiptText } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

import { ORDERING_OPTIONS, toListParams, useOrderParams } from '../hooks/use-order-params'
import { useOrders } from '../hooks/use-orders'
import { ORDER_STATUS_META } from '../status'
import { ORDER_STATUSES, type OrderOrdering, type OrderSandboxFilter, type OrderStatus } from '../types'
import { ErrorState, FilterSelect, PaginationBar } from './list-controls'
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
        <ErrorState noun="orders" status={error.status} message={error.message} onRetry={refetch} onFirstPage={() => setPage(1)} />
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
            id="order-page-size"
            noun="order"
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
