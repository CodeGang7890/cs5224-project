import { BaseEdge, EdgeLabelRenderer, getBezierPath, useReactFlow, type EdgeProps } from '@xyflow/react'
import { X } from 'lucide-react'

/** Arrow between two blocks. When selected, shows a button to remove it. */
export function DeletableEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  markerEnd,
  selected,
}: EdgeProps) {
  const { deleteElements } = useReactFlow()
  const [path, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
  })

  return (
    <>
      <BaseEdge path={path} markerEnd={markerEnd} style={{ strokeWidth: selected ? 2.5 : 1.75 }} />
      {selected && (
        <EdgeLabelRenderer>
          <button
            type="button"
            aria-label="Remove connection"
            title="Remove connection"
            className="nodrag nopan bg-background text-muted-foreground hover:border-destructive hover:text-destructive absolute flex size-6 items-center justify-center rounded-full border shadow-sm transition-colors"
            style={{ transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`, pointerEvents: 'all' }}
            onClick={() => deleteElements({ edges: [{ id }] })}
          >
            <X className="size-3.5" />
          </button>
        </EdgeLabelRenderer>
      )}
    </>
  )
}
