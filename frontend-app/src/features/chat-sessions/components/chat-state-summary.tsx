import type { ReactNode } from 'react'
import { CircleCheck } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

import { useDetailLabels } from '../hooks/use-chat-steps'
import type { ChatStateData, ChatStateItem } from '../types'

/** Order total as a "12.34" string (summed in cents, so 3 × 1.10 is 3.30). */
function orderTotal(items: ChatStateItem[]): string {
  const cents = items.reduce((sum, item) => sum + Math.round(Number(item.unit_price) * 100) * item.quantity, 0)
  return (cents / 100).toFixed(2)
}

interface ChatStateSummaryProps {
  data: ChatStateData
  className?: string
}

/** What the chat flow has collected (order, customer details), and whether the order is confirmed. */
export function ChatStateSummary({ data, className }: ChatStateSummaryProps) {
  const labels = useDetailLabels()
  const items = data.items ?? []
  const details = Object.entries(data.details ?? {})
  return (
    <dl className={cn('flex flex-wrap items-center gap-x-4 gap-y-1 text-xs', className)}>
      <Field label="Order">
        {items.length > 0
          ? `${items.map((item) => `${item.quantity} × ${item.name}`).join(', ')} · $${orderTotal(items)}`
          : '—'}
      </Field>
      {details.length === 0 ? (
        <Field label="Details">—</Field>
      ) : (
        // Labels from the current workflow; a detail whose field was since removed shows its key.
        details.map(([key, value]) => (
          <Field key={key} label={labels[key] ?? key}>
            {String(value)}
          </Field>
        ))
      )}
      {data.completed && (
        <Badge variant="outline" className="border-emerald-500/50 text-emerald-700 dark:text-emerald-400">
          <CircleCheck /> Order confirmed
        </Badge>
      )}
    </dl>
  )
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex min-w-0 items-baseline gap-1.5">
      <dt className="text-muted-foreground shrink-0">{label}</dt>
      <dd className="truncate font-medium">{children}</dd>
    </div>
  )
}
