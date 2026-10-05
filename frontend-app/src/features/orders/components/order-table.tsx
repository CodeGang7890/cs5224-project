import { Eye } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'

import type { Order } from '../types'
import { OrderStatusBadge, SandboxBadge } from './order-status-badge'

const formatDateTime = (iso: string) =>
  new Date(iso).toLocaleString([], { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })

/** The customer's name (a detail with the key `name`), else their email, else nothing. */
function orderCustomer(order: Order): string | null {
  const { name, email } = order.order_data.details
  return (typeof name === 'string' && name) || (typeof email === 'string' && email) || null
}

interface OrderTableProps {
  orders: Order[]
  onOpen: (id: number) => void
}

/** Read-only list of orders. Clicking a row (or View) opens the order. */
export function OrderTable({ orders, onOpen }: OrderTableProps) {
  return (
    <div className="rounded-xl border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="pl-4">Order</TableHead>
            <TableHead>Customer</TableHead>
            <TableHead className="w-[34%]">Items</TableHead>
            <TableHead className="text-right">Total</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Placed</TableHead>
            <TableHead className="w-12">
              <span className="sr-only">Actions</span>
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {orders.map((order) => {
            const items = order.order_data.items.map((item) => `${item.quantity} × ${item.name}`).join(', ')
            const customer = orderCustomer(order)
            return (
              <TableRow key={order.id} className="cursor-pointer" onClick={() => onOpen(order.id)}>
                <TableCell className="pl-4">
                  <div className="flex items-center gap-2">
                    <span className="font-medium tabular-nums">#{order.id}</span>
                    {order.is_sandbox && <SandboxBadge />}
                  </div>
                </TableCell>
                <TableCell>{customer ?? <span className="text-muted-foreground">—</span>}</TableCell>
                <TableCell className="max-w-0">
                  <p className="text-muted-foreground truncate" title={items}>
                    {items}
                  </p>
                </TableCell>
                <TableCell className="text-right font-medium tabular-nums">${order.total}</TableCell>
                <TableCell>
                  <OrderStatusBadge status={order.order_status} />
                </TableCell>
                <TableCell className="whitespace-nowrap tabular-nums">{formatDateTime(order.created_time)}</TableCell>
                <TableCell>
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label={`View order #${order.id}`}
                    onClick={(event) => {
                      event.stopPropagation()
                      onOpen(order.id)
                    }}
                  >
                    <Eye />
                  </Button>
                </TableCell>
              </TableRow>
            )
          })}
        </TableBody>
      </Table>
    </div>
  )
}
