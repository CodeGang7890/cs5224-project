import type { OrderStatus } from "./types";

export const ORDER_STATUS_META: Record<
  OrderStatus,
  { label: string; className: string }
> = {
  pending_payment: {
    label: "Pending payment",
    className: "border-amber-500/50 text-amber-700 dark:text-amber-400",
  },
  payment_received: {
    label: "Payment received",
    className: "border-sky-500/50 text-sky-700 dark:text-sky-400",
  },
  order_completed: {
    label: "Completed",
    className: "border-emerald-500/50 text-emerald-700 dark:text-emerald-400",
  },
  payment_failed: {
    label: "Payment failed",
    className: "border-red-500/50 text-red-700 dark:text-red-400",
  },
};
