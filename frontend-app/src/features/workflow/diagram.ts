import { MarkerType, type Edge, type Node } from "@xyflow/react";

import { DETAILS_NODES, type FlowNodeId } from "./steps";
import type { DetailField } from "./types";

// The Workflow tab's diagram of the (fixed) chat flow, as React Flow nodes and edges. Only the
// blocks' settings can change (so far, the details steps' fields), not the flow.

export type StepNodeData = {
  nodeId: FlowNodeId;
  /** The details steps only: the details they ask for (the editor's current, maybe unsaved, ones). */
  fields?: DetailField[];
  /** The Welcome & style block only: a summary of the (maybe unsaved) settings. */
  settings?: { welcome: boolean; style: string };
  /** Set when customers can't reach the block: why (e.g. no products yet). Greys it out. */
  unavailable?: string;
};

/** The routes the router sends customers down, and their blocks. */
export type FlowRoute = "orders" | "bookings";
export const ROUTE_NODES: Record<FlowRoute, FlowNodeId[]> = {
  orders: ["product_selection", "details_collection", "confirmation"],
  bookings: [
    "service_selection",
    "slot_selection",
    "booking_details",
    "booking_confirmation",
  ],
};
/** Why a route is greyed out, on its blocks. */
export const UNAVAILABLE_REASONS: Record<FlowRoute, string> = {
  orders: "No active products yet, so customers can’t order.",
  bookings: "No bookable services yet, so customers can’t book.",
};
export type StepNode = Node<StepNodeData, "step">;

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
};

// Blocks are `w-56` (224 px) wide and at most ~200 px tall.
const NODE_WIDTH = 224;
const NODE_HEIGHT = 200;
// How far past the outermost blocks the diagram can be panned.
const PAN_MARGIN = 300;

/** The area the diagram can be panned within (React Flow's `translateExtent`), so it can't be lost off-screen. */
export const DIAGRAM_EXTENT: [[number, number], [number, number]] = (() => {
  const points = Object.values(POSITIONS);
  const xs = points.map((point) => point.x);
  const ys = points.map((point) => point.y);
  return [
    [Math.min(...xs) - PAN_MARGIN, Math.min(...ys) - PAN_MARGIN],
    [
      Math.max(...xs) + NODE_WIDTH + PAN_MARGIN,
      Math.max(...ys) + NODE_HEIGHT + PAN_MARGIN,
    ],
  ];
})();

/** The diagram's blocks; each details block gets its own fields, the Welcome & style block `settings`. */
export function flowNodes(
  orderFields: DetailField[],
  bookingFields: DetailField[],
  settings?: StepNodeData["settings"],
): StepNode[] {
  return (Object.keys(POSITIONS) as FlowNodeId[]).map((nodeId) => ({
    id: nodeId,
    type: "step",
    position: POSITIONS[nodeId],
    data: DETAILS_NODES.includes(nodeId)
      ? {
          nodeId,
          fields: nodeId === "booking_details" ? bookingFields : orderFields,
        }
      : nodeId === "settings"
        ? { nodeId, settings }
        : { nodeId },
    draggable: false,
    connectable: false,
    deletable: false,
    // React Flow's own (unlayered) CSS gives nodes `cursor: default`, which beats Tailwind classes; every
    // block opens a dialog when clicked, so the pointer is set inline.
    style: { cursor: "pointer" },
  }));
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
    type: "smoothstep",
    deletable: false,
    selectable: false,
    markerEnd: { type: MarkerType.ArrowClosed, width: 18, height: 18 },
    labelBgPadding: [6, 3],
    labelBgBorderRadius: 4,
  };
}

/** The welcome message before the router, the router's branches, and the order and booking steps in order. */
export const FLOW_EDGES: Edge[] = [
  // Up from Welcome & style (below the router) into the router's bottom.
  edge("settings", "router", "First message", {
    sourceHandle: "top",
    targetHandle: "bottom",
  }),
  edge("router", "product_selection", "Orders"),
  edge("product_selection", "details_collection"),
  edge("details_collection", "confirmation"),
  edge("router", "service_selection", "Bookings"),
  edge("service_selection", "slot_selection"),
  edge("slot_selection", "booking_details"),
  edge("booking_details", "booking_confirmation"),
  edge("router", "faqs", "Questions"),
  edge("router", "order_status", "Past orders"),
];

/** FLOW_EDGES, with the arrows into or within an unavailable route dimmed and dashed. */
export function flowEdges(unavailable: ReadonlySet<FlowNodeId>): Edge[] {
  return FLOW_EDGES.map((item) =>
    unavailable.has(item.target as FlowNodeId)
      ? {
          ...item,
          style: { opacity: 0.35, strokeDasharray: "6 4" },
          labelStyle: { opacity: 0.5 },
        }
      : item,
  );
}
