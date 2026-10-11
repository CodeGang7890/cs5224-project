/** A product as returned by configuration-service (`/api/products/`). */
export interface Product {
  id: number
  business: number
  name: string
  /** Short summary the chat assistant tells customers when they ask what the product is. */
  description: string
  /** Long extra details (ingredients, options, FAQs…) the assistant looks up only when a question needs them. */
  information: string
  /** Decimal string, e.g. "12.50". */
  price: string
  /** How many the business has in total, including those on hold or sold: the only stored quantity. */
  total_quantity: number
  /** Read-only, derived from the orders: total_quantity − quantity_on_hold − quantity_sold. */
  quantity_available: number
  /** Read-only, derived: the quantity in orders pending payment or paid (not completed yet). */
  quantity_on_hold: number
  /** Read-only, derived: the quantity in completed orders. */
  quantity_sold: number
  is_active: boolean
}

/**
 * Fields users may write. `id`, `business` (defaults to your business) and the derived quantities
 * (`quantity_available`, `quantity_on_hold`, `quantity_sold`) are read-only and must not be sent
 * (the API returns 400): stock is changed through `total_quantity` only.
 */
export type ProductInput = Pick<
  Product,
  'name' | 'description' | 'information' | 'price' | 'total_quantity' | 'is_active'
>
