import { TabPage } from '@/components/common/tab-page'
import { OrdersBrowser } from '@/features/orders'

export function ProductOrdersPage() {
  return (
    <TabPage title="Products" section="Orders">
      <OrdersBrowser />
    </TabPage>
  )
}
