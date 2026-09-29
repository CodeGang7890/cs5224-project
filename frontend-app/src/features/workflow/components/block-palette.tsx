import type { DragEvent } from 'react'
import { GripVertical, Plus } from 'lucide-react'

import { BLOCK_META } from '../blocks'
import { ADDABLE_BLOCK_TYPES, type BlockType } from '../types'
import { BlockSummary } from './block-node'

/** Drag-and-drop data type, so the canvas ignores unrelated drops (files, text…). */
export const BLOCK_DRAG_TYPE = 'application/x-ansera-block-type'

/** Left panel: the block types users can drag onto the canvas (or click to add). */
export function BlockPalette({ onAdd }: { onAdd: (blockType: BlockType) => void }) {
  const onDragStart = (event: DragEvent, blockType: BlockType) => {
    event.dataTransfer.setData(BLOCK_DRAG_TYPE, blockType)
    event.dataTransfer.effectAllowed = 'move'
  }

  return (
    <aside className="bg-muted/30 flex w-64 shrink-0 flex-col gap-3 border-r p-3">
      <div className="grid gap-0.5 px-1">
        <h2 className="text-sm font-semibold">Blocks</h2>
        <p className="text-muted-foreground text-xs">Drag a block onto the canvas, or click + to add it.</p>
      </div>
      <ul className="grid gap-2">
        {ADDABLE_BLOCK_TYPES.map((blockType) => (
          <li
            key={blockType}
            draggable
            onDragStart={(event) => onDragStart(event, blockType)}
            className={`bg-card group relative flex cursor-grab items-center gap-1 rounded-xl border border-t-4 py-3 pr-2 pl-1 shadow-sm transition hover:shadow-md active:cursor-grabbing ${BLOCK_META[blockType].accentClassName}`}
          >
            <GripVertical className="text-muted-foreground/60 size-4 shrink-0" />
            <div className="min-w-0 flex-1">
              <BlockSummary blockType={blockType} />
            </div>
            <button
              type="button"
              aria-label={`Add ${BLOCK_META[blockType].label} block`}
              title="Add to canvas"
              className="text-muted-foreground hover:bg-accent hover:text-foreground shrink-0 self-start rounded-md p-1 transition-colors"
              onClick={() => onAdd(blockType)}
            >
              <Plus className="size-4" />
            </button>
          </li>
        ))}
      </ul>
      <p className="text-muted-foreground mt-auto px-1 text-xs leading-relaxed">
        Connect blocks by dragging from a block's right dot to another block. Click an arrow to remove it.
        The Start block is always there and can't be removed.
      </p>
    </aside>
  )
}
