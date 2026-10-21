import { useSearchParams } from 'react-router'

import { ORDER_STATUSES, type OrderSandboxFilter, type OrderStatus } from '../types'
import { DEFAULT_PAGE_SIZE, PAGE_SIZES } from './use-order-params'

// The Orders section's Payment sub-tab keeps its filters, paging and the open order / booking in the
// URL (`?status=…&order=…&booking=…`), like the orders and bookings lists.

const SANDBOX_VALUES: OrderSandboxFilter[] = ['include', 'exclude', 'only']
const DEFAULT_SANDBOX: OrderSandboxFilter = 'include'

export interface PaymentFilterValues {
  status: OrderStatus | ''
  sandbox: OrderSandboxFilter
  orderPage: number
  orderPageSize: number
  bookingPage: number
  bookingPageSize: number
}

function readPage(params: URLSearchParams, name: string): number {
  const page = Number(params.get(name))
  return Number.isInteger(page) && page > 0 ? page : 1
}

function readPageSize(params: URLSearchParams, name: string): number {
  const pageSize = Number(params.get(name))
  return (PAGE_SIZES as readonly number[]).includes(pageSize) ? pageSize : DEFAULT_PAGE_SIZE
}

function readValues(params: URLSearchParams): PaymentFilterValues {
  const status = params.get('status') as OrderStatus
  const sandbox = params.get('sandbox') as OrderSandboxFilter
  return {
    status: ORDER_STATUSES.includes(status) ? status : '',
    sandbox: SANDBOX_VALUES.includes(sandbox) ? sandbox : DEFAULT_SANDBOX,
    orderPage: readPage(params, 'order_page'),
    orderPageSize: readPageSize(params, 'order_page_size'),
    bookingPage: readPage(params, 'booking_page'),
    bookingPageSize: readPageSize(params, 'booking_page_size'),
  }
}

/** Filter, paging and open-item state of the Payment sub-tab, stored in the URL. */
export function usePaymentParams() {
  const [searchParams, setSearchParams] = useSearchParams()
  const values = readValues(searchParams)

  const setFilters = (changes: Partial<Pick<PaymentFilterValues, 'status' | 'sandbox'>>) =>
    setSearchParams(
      (params) => {
        if (changes.status !== undefined) {
          if (changes.status === '') params.delete('status')
          else params.set('status', changes.status)
        }
        if (changes.sandbox !== undefined) {
          if (changes.sandbox === DEFAULT_SANDBOX) params.delete('sandbox')
          else params.set('sandbox', changes.sandbox)
        }
        params.delete('order_page')
        params.delete('booking_page')
        return params
      },
      { replace: true },
    )

  const setOrderPage = (page: number) =>
    setSearchParams(
      (params) => {
        if (page <= 1) params.delete('order_page')
        else params.set('order_page', String(page))
        return params
      },
      { replace: true },
    )

  const setOrderPageSize = (pageSize: number) =>
    setSearchParams(
      (params) => {
        if (pageSize === DEFAULT_PAGE_SIZE) params.delete('order_page_size')
        else params.set('order_page_size', String(pageSize))
        params.delete('order_page')
        return params
      },
      { replace: true },
    )

  const setBookingPage = (page: number) =>
    setSearchParams(
      (params) => {
        if (page <= 1) params.delete('booking_page')
        else params.set('booking_page', String(page))
        return params
      },
      { replace: true },
    )

  const setBookingPageSize = (pageSize: number) =>
    setSearchParams(
      (params) => {
        if (pageSize === DEFAULT_PAGE_SIZE) params.delete('booking_page_size')
        else params.set('booking_page_size', String(pageSize))
        params.delete('booking_page')
        return params
      },
      { replace: true },
    )

  const clearFilters = () => setFilters({ status: '', sandbox: DEFAULT_SANDBOX })
  const hasFilters = values.status !== '' || values.sandbox !== DEFAULT_SANDBOX

  const openOrderId = Number(searchParams.get('order')) || null
  const setOpenOrder = (id: number | null) =>
    setSearchParams(
      (params) => {
        if (id === null) params.delete('order')
        else params.set('order', String(id))
        return params
      },
      { replace: true },
    )

  const openBookingId = Number(searchParams.get('booking')) || null
  const setOpenBooking = (id: number | null) =>
    setSearchParams(
      (params) => {
        if (id === null) params.delete('booking')
        else params.set('booking', String(id))
        return params
      },
      { replace: true },
    )

  return {
    values,
    setFilters,
    setOrderPage,
    setOrderPageSize,
    setBookingPage,
    setBookingPageSize,
    clearFilters,
    hasFilters,
    openOrderId,
    setOpenOrder,
    openBookingId,
    setOpenBooking,
  }
}
