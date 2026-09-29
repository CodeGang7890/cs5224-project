import { Handle, Position, useReactFlow, type NodeProps } from '@xyflow/react'
import { X } from 'lucide-react'

import { cn } from '@/lib/utils'

import { BLOCK_META } from '../blocks'
import type { BlockNode } from '../flow'
import { START_BLOCK, type BlockType } from '../types'

const handleClassName = 'size-3! border-2! border-background! bg-primary!'

/** A block's icon, name and description. Shared by the canvas node and the palette. */
export function BlockSummary({ blockType }: { blockType: BlockType }) {
  const meta = BLOCK_META[blockType]
  const Icon = meta.icon
  return (
    <div className="flex items-start gap-3">
      <div className={cn('flex size-9 shrink-0 items-center justify-center rounded-lg', meta.iconClassName)}>
        <Icon className="size-4" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-sm leading-tight font-semibold">{meta.label}</p>
        <p className="text-muted-foreground mt-0.5 text-xs leading-snug">{meta.description}</p>
      </div>
    </div>
  )
}

/** Canvas node. Arrows go out of the right dot and into the left one. START_BLOCK has no input and can't be deleted. */
export function BlockNodeView({ id, data, selected }: NodeProps<BlockNode>) {
  const { deleteElements } = useReactFlow()
  const isStart = data.blockType === START_BLOCK
  const meta = BLOCK_META[data.blockType]

  return (
    <div
      className={cn(
        'bg-card text-card-foreground relative w-56 rounded-xl border border-t-4 p-3 shadow-sm transition-shadow hover:shadow-md',
        meta.accentClassName,
        selected && 'ring-ring ring-2 ring-offset-2 ring-offset-background',
      )}
    >
      {!isStart && <Handle type="target" position={Position.Left} className={handleClassName} />}
      <div className={cn(!isStart && 'pr-5')}>
        <BlockSummary blockType={data.blockType} />
      </div>
      {!isStart && (
        <button
          type="button"
          aria-label={`Delete ${meta.label} block`}
          title="Delete block"
          className="nodrag text-muted-foreground hover:bg-destructive/10 hover:text-destructive absolute top-1.5 right-1.5 rounded-md p-1 transition-colors"
          onClick={() => deleteElements({ nodes: [{ id }] })}
        >
          <X className="size-3.5" />
        </button>
      )}
      <Handle type="source" position={Position.Right} className={handleClassName} />
    </div>
  )
}
