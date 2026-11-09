/** Order statuses, mirrored from configuration-service `checkout_app/models.py` (`OrderStatus`). */
export const ORDER_STATUSES = [
  "pending_payment",
  "payment_received",
  "order_completed",
  "payment_failed",
] as const;

export type OrderStatus = (typeof ORDER_STATUSES)[number];

/** One product in an order; `name` and `unit_price` are what the customer was shown. */
export interface OrderLine {
  product_id: number;
  name: string;
  /** Decimal string, e.g. "5.50". */
  unit_price: string;
  quantity: number;
}

/** `OrderItem.order_data`: what was ordered and the customer details collected in the chat. */
export interface OrderData {
  items: OrderLine[];
  /** By detail field key (the workflow's Details collection fields), e.g. `postal_code`. */
  details: Record<string, string | number>;
}

/** An order (`/api/orders/`), created when a customer confirms in a chat. Read only. */
export interface Order {
  id: number;
  business: number;
  /** The chat it was placed in; null if that chat was deleted. */
  chat_session: number | null;
  /** Placed in a Chat Sandbox test chat. */
  is_sandbox: boolean;
  order_status: OrderStatus;
  /** Random 128-bit reference (32 hex characters) the payment is made under; payment events come back with it. */
  payment_reference: string;
  /** Xendit's session / payment ID; null until the payment link is created. */
  xendit_payment_id: string | null;
  /** The Xendit hosted payment link; null until it is created. */
  payment_link: string | null;
  order_data: OrderData;
  /** Decimal string, e.g. "9.10". */
  total: string;
  created_time: string;
  updated_time: string;
}

export type OrderOrdering = "-created_time" | "created_time" | "order_status";

/** Sandbox (test) orders: included by default (they reserve real stock). */
export type OrderSandboxFilter = "include" | "exclude" | "only";

/** Query parameters of GET /api/orders/. */
export interface OrderListParams {
  page: number;
  page_size: number;
  ordering: OrderOrdering;
  sandbox: OrderSandboxFilter;
  order_status?: OrderStatus;
}

/** `ScheduleItem.schedule_data`: the service booked (a snapshot) and the customer details collected in the chat. */
export interface ScheduleData {
  service: {
    service_id: number;
    name: string;
    /** Decimal string, e.g. "180.00". */
    price: string;
    duration_minutes: number;
    buffer_minutes: number;
  };
  details: Record<string, string | number>;
}

/** A booked time slot (`/api/schedules/`), created when a customer confirms a booking in a chat. Read only. */
export interface ScheduleItem {
  id: number;
  business: number;
  chat_session: number | null;
  is_sandbox: boolean;
  /** Null if the service was deleted since (the snapshot is in `schedule_data`). */
  service: number | null;
  /** The service provider it's booked with (e.g. a photographer); null if deleted. */
  service_provider: number | null;
  service_provider_name: string | null;
  start_time: string;
  /** start_time + the service duration. */
  end_time: string;
  /** end_time + the service buffer: when the calendar is free again. */
  blocked_until: string;
  order_status: OrderStatus;
  /** Random 128-bit reference (32 hex characters) the payment is made under; payment events come back with it. */
  payment_reference: string;
  /** Xendit's session / payment ID; null until the payment link is created. */
  xendit_payment_id: string | null;
  /** The Xendit hosted payment link; null until it is created. */
  payment_link: string | null;
  schedule_data: ScheduleData;
  /** The service's price, e.g. "180.00". */
  total: string;
  created_time: string;
  updated_time: string;
}

export type ScheduleOrdering =
  | "-start_time"
  | "start_time"
  | "-created_time"
  | "created_time"
  | "order_status";

/** Query parameters of GET /api/schedules/. */
export interface ScheduleListParams {
  page: number;
  page_size: number;
  ordering: ScheduleOrdering;
  sandbox: OrderSandboxFilter;
  order_status?: OrderStatus;
}
