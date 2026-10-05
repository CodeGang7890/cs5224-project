import { APP_NAME } from '@/config/app'
import { OrdersBrowser } from '@/features/orders'

export function OrdersPage() {
  return (
    <section className="flex flex-col gap-6">
      <title>{`Orders | ${APP_NAME}`}</title>
      <div className="grid gap-1">
        <h1 className="text-2xl font-bold tracking-tight">Orders</h1>
        <p className="text-muted-foreground text-sm">
          Orders your customers confirmed in a chat. This page is read only.
        </p>
      </div>
      <OrdersBrowser />
    </section>
  )
}
