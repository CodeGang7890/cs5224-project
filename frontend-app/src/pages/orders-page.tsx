import { SectionLayout } from '@/components/layout/section-layout'
import { ordersTabs } from '@/config/navigation'

/** The Orders section: product orders, service bookings and payment. */
export function OrdersPage() {
  return (
    <SectionLayout
      title="Orders"
      description="Product orders and service bookings your customers confirmed in a chat (read only), and payment."
      tabs={ordersTabs}
    />
  )
}
