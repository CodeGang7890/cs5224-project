import { Handle, Position, type NodeProps } from '@xyflow/react'
import { Info, Pencil } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

import { detailFieldsOrDefault, isRequiredDetail } from '../details'
import type { StepNode } from '../diagram'
import { DETAILS_NODES, FLOW_NODE_META } from '../steps'

// Arrows still need handles, but nothing can be connected, so they're hidden.
const handleClassName = 'opacity-0! pointer-events-none!'

/** A block of the flow diagram. The whole block is clickable (WorkflowEditor's onNodeClick). */
export function StepNodeView({ data, selected }: NodeProps<StepNode>) {
  const meta = FLOW_NODE_META[data.nodeId]
  const Icon = meta.icon
  const isDetails = DETAILS_NODES.includes(data.nodeId)
  // Blocks with a next step in their branch.
  const hasNext = ['router', 'product_selection', 'details_collection', 'service_selection', 'slot_selection', 'booking_details'].includes(data.nodeId)

  return (
    <div
      className={cn(
        'bg-card text-card-foreground relative w-56 cursor-pointer rounded-xl border border-t-4 p-3 shadow-sm transition-shadow hover:shadow-md',
        meta.accentClassName,
        selected && 'ring-ring ring-2 ring-offset-2 ring-offset-background',
      )}
    >
      {data.nodeId !== 'router' && <Handle type="target" position={Position.Left} className={handleClassName} />}
      <div className="flex items-start gap-3">
        <div className={cn('flex size-9 shrink-0 items-center justify-center rounded-lg', meta.iconClassName)}>
          <Icon className="size-4" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="flex flex-wrap items-center gap-1.5 text-sm leading-tight font-semibold">
            {meta.label}
            {meta.badge && (
              <Badge variant="outline" className="px-1.5 py-0 text-[10px] font-medium">
                {meta.badge}
              </Badge>
            )}
          </p>
          <p className="text-muted-foreground mt-0.5 text-xs leading-snug">{meta.description}</p>
        </div>
      </div>
      {isDetails ? (
        <div className="mt-2.5 grid gap-1.5 border-t pt-2">
          <ul className="flex flex-wrap gap-1" aria-label="Details collected">
            {detailFieldsOrDefault(data.fields).map((field) => (
              <li key={field.key} className="bg-muted max-w-full truncate rounded px-1.5 py-0.5 text-[11px]">
                {field.label}
                {!isRequiredDetail(field) && <span className="text-muted-foreground"> (optional)</span>}
              </li>
            ))}
          </ul>
          <p className="text-muted-foreground flex items-center gap-1 text-[11px]">
            <Pencil className="size-3" /> Click to edit the details
          </p>
        </div>
      ) : (
        <p className="text-muted-foreground mt-2 flex items-center gap-1 text-[11px]">
          <Info className="size-3" /> Click for more
        </p>
      )}
      {hasNext && (
        <Handle type="source" position={Position.Right} className={handleClassName} />
      )}
    </div>
  )
}
