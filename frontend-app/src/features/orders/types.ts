/** Order statuses, mirrored from configuration-service `checkout_app/models.py` (`OrderStatus`). */
export const ORDER_STATUSES = ['pending_payment', 'payment_received', 'order_completed'] as const

export type OrderStatus = (typeof ORDER_STATUSES)[number]

/** One product in an order; `name` and `unit_price` are what the customer was shown. */
export interface OrderLine {
  product_id: number
  name: string
  /** Decimal string, e.g. "5.50". */
  unit_price: string
  quantity: number
}

/** `OrderItem.order_data`: what was ordered and the customer details collected in the chat. */
export interface OrderData {
  items: OrderLine[]
  /** By detail field key (the workflow's Details collection fields), e.g. `postal_code`. */
  details: Record<string, string | number>
}

/** An order (`/api/orders/`), created when a customer confirms in a chat. Read only. */
export interface Order {
  id: number
  business: number
  /** The chat it was placed in; null if that chat was deleted. */
  chat_session: number | null
  /** Placed in a Chat Sandbox test chat. */
  is_sandbox: boolean
  order_status: OrderStatus
  order_data: OrderData
  /** Decimal string, e.g. "9.10". */
  total: string
  created_time: string
  updated_time: string
}

export type OrderOrdering = '-created_time' | 'created_time' | 'order_status'

/** Sandbox (test) orders: included by default (they reserve real stock). */
export type OrderSandboxFilter = 'include' | 'exclude' | 'only'

/** Query parameters of GET /api/orders/. */
export interface OrderListParams {
  page: number
  page_size: number
  ordering: OrderOrdering
  sandbox: OrderSandboxFilter
  order_status?: OrderStatus
}
