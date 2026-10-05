import { configurationApiClient } from '@/lib/api-client'
import type { DetailedPaginated } from '@/types/api'

import type { Order, OrderListParams } from '../types'

/** The logged-in business's orders, filtered, sorted and paginated by the backend. */
export async function listOrders(params: OrderListParams): Promise<DetailedPaginated<Order>> {
  const { data } = await configurationApiClient.get<DetailedPaginated<Order>>('/orders/', { params })
  return data
}

/** One order (403 if it's another business's, 404 if it doesn't exist). */
export async function getOrder(id: number): Promise<Order> {
  const { data } = await configurationApiClient.get<Order>(`/orders/${id}/`)
  return data
}
