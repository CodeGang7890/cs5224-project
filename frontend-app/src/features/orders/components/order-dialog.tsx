import { CircleAlert } from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableFooter,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useDetailLabels } from "@/features/workflow";

import { useOrder } from "../hooks/use-orders";
import type { Order } from "../types";
import { MarkCompletedButton } from "./mark-completed-button";
import { OrderStatusBadge, SandboxBadge } from "./order-status-badge";
import { PaymentDetails } from "./payment-details";

interface OrderDialogProps {
  /** The open order's ID (from `?order=`), or null when closed. */
  orderId: number | null;
  /** The order, if it's on the current page (otherwise it's fetched by ID). */
  order: Order | undefined;
  onClose: () => void;
}

/** One order: items, total, customer details and status; a paid one can be marked as completed. */
export function OrderDialog({ orderId, order, onClose }: OrderDialogProps) {
  const fetched = useOrder(orderId, order === undefined);
  const shown = order ?? fetched.data;

  return (
    <Dialog open={orderId !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="flex max-h-[85svh] flex-col gap-4 sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            Order #{orderId}
            {shown && <OrderStatusBadge status={shown.order_status} />}
            {shown?.is_sandbox && <SandboxBadge />}
          </DialogTitle>
          <DialogDescription>
            {shown
              ? `Placed ${new Date(shown.created_time).toLocaleString()}`
              : " "}
          </DialogDescription>
        </DialogHeader>
        {shown ? (
          <>
            <OrderDetails order={shown} />
            {shown.order_status === "payment_received" && (
              <DialogFooter>
                <MarkCompletedButton kind="order" id={shown.id} />
              </DialogFooter>
            )}
          </>
        ) : fetched.isError ? (
          <p
            role="alert"
            className="text-destructive flex items-center gap-2 text-sm"
          >
            <CircleAlert className="size-4 shrink-0" />
            {fetched.error.status === 404
              ? "This order doesn't exist."
              : fetched.error.status === 403
                ? "This order belongs to another business, so you can't see it."
                : `Couldn't load the order: ${fetched.error.message}`}
          </p>
        ) : (
          <div
            className="grid gap-2"
            aria-busy="true"
            aria-label="Loading order"
          >
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-16 w-full" />
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

function OrderDetails({ order }: { order: Order }) {
  const labels = useDetailLabels("order");
  const details = Object.entries(order.order_data.details);
  return (
    <div className="grid min-h-0 gap-4 overflow-y-auto">
      <PaymentDetails
        reference={order.payment_reference}
        xenditPaymentId={order.xendit_payment_id}
        paymentLink={order.payment_link}
        owner="order"
        id={order.id}
        status={order.order_status}
      />
      <div className="rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="pl-3">Item</TableHead>
              <TableHead className="text-right">Unit price</TableHead>
              <TableHead className="text-right">Qty</TableHead>
              <TableHead className="pr-3 text-right">Subtotal</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {order.order_data.items.map((item) => (
              <TableRow key={item.product_id}>
                <TableCell className="pl-3 font-medium">{item.name}</TableCell>
                <TableCell className="text-right tabular-nums">
                  ${item.unit_price}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {item.quantity}
                </TableCell>
                <TableCell className="pr-3 text-right tabular-nums">
                  $
                  {(
                    (Math.round(Number(item.unit_price) * 100) *
                      item.quantity) /
                    100
                  ).toFixed(2)}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
          <TableFooter>
            <TableRow>
              <TableCell colSpan={3} className="pl-3">
                Total
              </TableCell>
              <TableCell className="pr-3 text-right tabular-nums">
                ${order.total}
              </TableCell>
            </TableRow>
          </TableFooter>
        </Table>
      </div>

      <section className="grid gap-2">
        <h3 className="text-sm font-semibold">Customer details</h3>
        {details.length === 0 ? (
          <p className="text-muted-foreground text-sm">None collected.</p>
        ) : (
          <dl className="grid gap-x-4 gap-y-2 rounded-lg border p-3 text-sm sm:grid-cols-2">
            {details.map(([key, value]) => (
              <div key={key} className="grid min-w-0 gap-0.5">
                {/* Labels from the current workflow; a field since removed shows its key. */}
                <dt className="text-muted-foreground text-xs">
                  {labels[key] ?? key}
                </dt>
                <dd className="font-medium break-words">{String(value)}</dd>
              </div>
            ))}
          </dl>
        )}
      </section>

      <p className="text-muted-foreground text-xs">
        {order.chat_session !== null
          ? `From chat #${order.chat_session}`
          : "The chat this came from was deleted."}{" "}
        · Last updated {new Date(order.updated_time).toLocaleString()}
      </p>
    </div>
  );
}
