/** A product as returned by configuration-service (`/api/products/`). */
export interface Product {
  id: number
  business: number
  name: string
  description: string
  /** Decimal string, e.g. "12.50". */
  price: string
  quantity_available: number
  quantity_on_hold: number
  /** Read-only: managed by the backend. Never send it (the API returns 400). */
  quantity_sold: number
  is_active: boolean
}

/**
 * Fields users may write. `id`, `business` (defaults to your business) and `quantity_sold`
 * are read-only and must not be sent.
 */
export type ProductInput = Pick<
  Product,
  'name' | 'description' | 'price' | 'quantity_available' | 'quantity_on_hold' | 'is_active'
>
