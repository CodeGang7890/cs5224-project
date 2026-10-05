import { MarkerType, type Edge, type Node } from '@xyflow/react'

import { DEFAULT_SEND_MESSAGE } from './blocks'
import { DEFAULT_DETAIL_FIELDS, normalizeDetailField } from './details'
import {
  DETAILS_COLLECTION_BLOCK,
  SEND_MESSAGE_BLOCK,
  START_BLOCK,
  type BlockId,
  type BlockType,
  type ChatBlock,
  type DetailField,
} from './types'

// Converts between the API's `config_json` (a list of blocks with `next_block_id`) and
// React Flow's nodes + edges. Each block has at most one outgoing arrow.

/** Block settings that some types have: a DETAILS_COLLECTION_BLOCK's `fields` (undefined: the
 * backend's defaults) and a SEND_MESSAGE_BLOCK's `message`. */
export type BlockSettings = { fields?: DetailField[]; message?: string }

export type BlockNodeData = { blockId: BlockId; blockType: BlockType } & BlockSettings
export type BlockNode = Node<BlockNodeData, 'block'>

/** React Flow IDs must be strings; include the type so block IDs 1 and "1" stay distinct. */
export function toNodeId(blockId: BlockId): string {
  return `${typeof blockId}:${blockId}`
}

export function createBlockNode(
  blockId: BlockId,
  blockType: BlockType,
  position: { x: number; y: number },
  settings: BlockSettings = {},
): BlockNode {
  const data: BlockNodeData = { blockId, blockType }
  if (settings.fields) data.fields = settings.fields
  if (settings.message !== undefined) data.message = settings.message
  return { id: toNodeId(blockId), type: 'block', position, data, deletable: blockType !== START_BLOCK }
}

/** A block added from the palette, with default settings: fields for a DETAILS_COLLECTION_BLOCK,
 * a message for a SEND_MESSAGE_BLOCK. */
export function createNewBlockNode(blockType: BlockType, position: { x: number; y: number }): BlockNode {
  const settings: BlockSettings = {}
  if (blockType === DETAILS_COLLECTION_BLOCK) settings.fields = DEFAULT_DETAIL_FIELDS.map((f) => ({ ...f }))
  if (blockType === SEND_MESSAGE_BLOCK) settings.message = DEFAULT_SEND_MESSAGE
  return createBlockNode(crypto.randomUUID(), blockType, position, settings)
}

/** The arrow from `source` to `target`. Its ID comes from the source, as each block has one next block. */
export function createEdge(source: string, target: string): Edge {
  return {
    id: `next:${source}`,
    source,
    target,
    type: 'deletable',
    markerEnd: { type: MarkerType.ArrowClosed, width: 18, height: 18 },
  }
}

export function configToFlow(config: ChatBlock[]): { nodes: BlockNode[]; edges: Edge[] } {
  const nodes = config.map((block) =>
    createBlockNode(block.id, block.block_type, { x: block.position_x, y: block.position_y }, {
      fields: block.fields,
      message: block.message,
    }),
  )
  const nodeIds = new Set(nodes.map((node) => node.id))
  const edges = config.flatMap((block) => {
    if (block.next_block_id === null) return []
    const target = toNodeId(block.next_block_id)
    return nodeIds.has(target) ? [createEdge(toNodeId(block.id), target)] : []
  })
  return { nodes, edges }
}

/** Positions are rounded, so tiny drags don't produce noisy diffs. Key order is fixed, for comparing. */
export function flowToConfig(nodes: BlockNode[], edges: Edge[]): ChatBlock[] {
  const blockIdByNodeId = new Map(nodes.map((node) => [node.id, node.data.blockId]))
  const targetBySource = new Map(edges.map((edge) => [edge.source, edge.target]))
  return nodes.map((node) => {
    const target = targetBySource.get(node.id)
    const nextBlockId = target === undefined ? undefined : blockIdByNodeId.get(target)
    const block: ChatBlock = {
      id: node.data.blockId,
      next_block_id: nextBlockId ?? null,
      block_type: node.data.blockType,
      position_x: Math.round(node.position.x),
      position_y: Math.round(node.position.y),
    }
    if (node.data.blockType === DETAILS_COLLECTION_BLOCK && node.data.fields) {
      block.fields = node.data.fields.map(normalizeDetailField)
    }
    if (node.data.blockType === SEND_MESSAGE_BLOCK && node.data.message !== undefined) {
      block.message = node.data.message
    }
    return block
  })
}

/** Number of blocks that can't be reached by following the arrows from the START_BLOCK. */
export function countUnreachableBlocks(config: ChatBlock[]): number {
  const byId = new Map(config.map((block) => [block.id, block]))
  const reached = new Set<BlockId>()
  let block = config.find((b) => b.block_type === START_BLOCK)
  while (block && !reached.has(block.id)) {
    reached.add(block.id)
    block = block.next_block_id === null ? undefined : byId.get(block.next_block_id)
  }
  return config.length - reached.size
}

/** What a business starts with before it has saved a configuration: just the START_BLOCK. */
export const DEFAULT_CONFIG: ChatBlock[] = [
  { id: 1, next_block_id: null, block_type: START_BLOCK, position_x: 100, position_y: 100 },
]
