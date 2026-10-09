import type { ReactNode } from 'react'
import { useSearchParams } from 'react-router'

import { APP_NAME } from '@/config/app'
import { OrdersBrowser, SchedulesBrowser } from '@/features/orders'
import { cn } from '@/lib/utils'

type OrdersTab = 'products' | 'services'

export function OrdersPage() {
  // The sub-tab is in the URL (`?tab=services`), like the rest of the page's state.
  const [searchParams, setSearchParams] = useSearchParams()
  const tab: OrdersTab = searchParams.get('tab') === 'services' ? 'services' : 'products'
  // Each sub-tab has its own filters, so switching starts from a clean URL.
  const showTab = (next: OrdersTab) => setSearchParams(next === 'services' ? { tab: 'services' } : {})

  return (
    <section className="flex flex-col gap-6">
      <title>{`Orders | ${APP_NAME}`}</title>
      <div className="grid gap-1">
        <h1 className="text-2xl font-bold tracking-tight">Orders</h1>
        <p className="text-muted-foreground text-sm">
          Product orders and service bookings your customers confirmed in a chat. This page is read only.
        </p>
      </div>

      <div role="tablist" aria-label="Orders" className="flex gap-1 border-b">
        <TabButton active={tab === 'products'} onClick={() => showTab('products')}>
          Products
        </TabButton>
        <TabButton active={tab === 'services'} onClick={() => showTab('services')}>
          Services
        </TabButton>
      </div>

      {tab === 'products' ? <OrdersBrowser /> : <SchedulesBrowser />}
    </section>
  )
}

function TabButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={cn(
        '-mb-px inline-flex items-center border-b-2 px-3 py-2 text-sm font-medium transition-colors',
        active ? 'border-primary text-foreground' : 'text-muted-foreground hover:text-foreground border-transparent',
      )}
    >
      {children}
    </button>
  )
}
