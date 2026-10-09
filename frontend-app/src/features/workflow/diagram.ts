import { MarkerType, type Edge, type Node } from '@xyflow/react'

import type { FlowNodeId } from './steps'
import type { DetailField } from './types'

// The Workflow tab's diagram of the (fixed) chat flow, as React Flow nodes and edges. Only the
// blocks' settings can change (so far, the Details collection step's fields), not the flow.

export type StepNodeData = {
  nodeId: FlowNodeId
  /** details_collection only: the details it asks for (the editor's current, maybe unsaved, ones). */
  fields?: DetailField[]
}
export type StepNode = Node<StepNodeData, 'step'>

const POSITIONS: Record<FlowNodeId, { x: number; y: number }> = {
  router: { x: 0, y: 190 },
  product_selection: { x: 330, y: 20 },
  details_collection: { x: 630, y: 20 },
  confirmation: { x: 930, y: 20 },
  faqs: { x: 330, y: 230 },
  order_status: { x: 330, y: 390 },
}

/** The diagram's blocks; `fields` go on the Details collection block. */
export function flowNodes(fields: DetailField[]): StepNode[] {
  return (Object.keys(POSITIONS) as FlowNodeId[]).map((nodeId) => ({
    id: nodeId,
    type: 'step',
    position: POSITIONS[nodeId],
    data: nodeId === 'details_collection' ? { nodeId, fields } : { nodeId },
    draggable: false,
    connectable: false,
    deletable: false,
  }))
}

function edge(source: FlowNodeId, target: FlowNodeId, label?: string): Edge {
  return {
    id: `${source}->${target}`,
    source,
    target,
    label,
    type: 'smoothstep',
    deletable: false,
    selectable: false,
    markerEnd: { type: MarkerType.ArrowClosed, width: 18, height: 18 },
    labelBgPadding: [6, 3],
    labelBgBorderRadius: 4,
  }
}

/** The router's three branches, and the order steps in order. */
export const FLOW_EDGES: Edge[] = [
  edge('router', 'product_selection', 'Orders'),
  edge('product_selection', 'details_collection'),
  edge('details_collection', 'confirmation'),
  edge('router', 'faqs', 'Questions'),
  edge('router', 'order_status', 'Past orders'),
]
