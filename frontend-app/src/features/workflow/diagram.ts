import { MarkerType, type Edge, type Node } from '@xyflow/react'

import { DETAILS_NODES, type FlowNodeId } from './steps'
import type { DetailField } from './types'

// The Workflow tab's diagram of the (fixed) chat flow, as React Flow nodes and edges. Only the
// blocks' settings can change (so far, the details steps' fields), not the flow.

export type StepNodeData = {
  nodeId: FlowNodeId
  /** The details steps only: the details they ask for (the editor's current, maybe unsaved, ones). */
  fields?: DetailField[]
  /** The Welcome & style block only: a summary of the (maybe unsaved) settings. */
  settings?: { welcome: boolean; style: string }
}
export type StepNode = Node<StepNodeData, 'step'>

const POSITIONS: Record<FlowNodeId, { x: number; y: number }> = {
  router: { x: -90, y: 300 },
  settings: { x: -90, y: 520 }, // below the router: the welcome message comes before it
  product_selection: { x: 330, y: 20 },
  details_collection: { x: 630, y: 20 },
  confirmation: { x: 930, y: 20 },
  service_selection: { x: 330, y: 250 },
  slot_selection: { x: 630, y: 250 },
  booking_details: { x: 930, y: 250 },
  booking_confirmation: { x: 1230, y: 250 },
  faqs: { x: 330, y: 470 },
  order_status: { x: 330, y: 620 },
}

/** The diagram's blocks; each details block gets its own fields, the Welcome & style block `settings`. */
export function flowNodes(
  orderFields: DetailField[],
  bookingFields: DetailField[],
  settings?: StepNodeData['settings'],
): StepNode[] {
  return (Object.keys(POSITIONS) as FlowNodeId[]).map((nodeId) => ({
    id: nodeId,
    type: 'step',
    position: POSITIONS[nodeId],
    data: DETAILS_NODES.includes(nodeId)
      ? { nodeId, fields: nodeId === 'booking_details' ? bookingFields : orderFields }
      : nodeId === 'settings'
        ? { nodeId, settings }
        : { nodeId },
    draggable: false,
    connectable: false,
    deletable: false,
  }))
}

function edge(
  source: FlowNodeId,
  target: FlowNodeId,
  label?: string,
  handles?: { sourceHandle: string; targetHandle: string },
): Edge {
  return {
    id: `${source}->${target}`,
    source,
    target,
    label,
    ...handles,
    type: 'smoothstep',
    deletable: false,
    selectable: false,
    markerEnd: { type: MarkerType.ArrowClosed, width: 18, height: 18 },
    labelBgPadding: [6, 3],
    labelBgBorderRadius: 4,
  }
}

/** The welcome message before the router, the router's branches, and the order and booking steps in order. */
export const FLOW_EDGES: Edge[] = [
  // Up from Welcome & style (below the router) into the router's bottom.
  edge('settings', 'router', 'First message', { sourceHandle: 'top', targetHandle: 'bottom' }),
  edge('router', 'product_selection', 'Orders'),
  edge('product_selection', 'details_collection'),
  edge('details_collection', 'confirmation'),
  edge('router', 'service_selection', 'Bookings'),
  edge('service_selection', 'slot_selection'),
  edge('slot_selection', 'booking_details'),
  edge('booking_details', 'booking_confirmation'),
  edge('router', 'faqs', 'Questions'),
  edge('router', 'order_status', 'Past orders'),
]
