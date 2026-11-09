import type { DocumentKind } from "./api/documents-api";
import type { OrderStatus } from "./types";

/** Statuses an order / booking has a receipt in: it was paid. */
const PAID: OrderStatus[] = ["payment_received", "order_completed"];

/**
 * Which PDFs an order / booking should have: the invoice once its payment link was created (that's when
 * processing-service makes it), the receipt once it's paid.
 */
export function availableDocuments(item: {
  payment_link: string | null;
  order_status: OrderStatus;
}): DocumentKind[] {
  const kinds: DocumentKind[] = [];
  if (item.payment_link) kinds.push("invoice");
  if (PAID.includes(item.order_status)) kinds.push("receipt");
  return kinds;
}
